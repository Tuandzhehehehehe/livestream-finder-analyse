import re
import time
import hashlib
import json
import os
import sqlite3
import concurrent.futures
from typing import List, Dict, Any

from crawler.youtube import crawl_youtube_live
from crawler.meetup import crawl_meetup
from crawler.x import crawl_x_live
from crawler.tiktok import crawl_tiktok_live
from services.goal_analyzer import analyze_goal, build_fallback
from services.relevance_filter import calculate_relevance
from services.topic_expander import expand_topic

try:
    from crawler.eventbrite import crawl_eventbrite
except Exception:
    crawl_eventbrite = None


def build_fallback_queries(goal: str, max_queries: int = 20) -> List[str]:
    text = goal.strip().lower()
    if not text:
        return []

    tokens = re.split(r"[\s,\/\\-]+", text)
    tokens = [t for t in tokens if t]

    suffixes = [
        "",
        " live",
        " livestream",
        " live stream",
        " stream",
        " webinar",
        " workshop",
        " online event",
        " live session",
        " talk",
        " panel",
        " ama",
        " networking",
    ]

    queries = []
    for token in tokens or [text]:
        for suffix in suffixes:
            query = f"{token}{suffix}".strip()
            if query not in queries:
                queries.append(query)
                if len(queries) >= max_queries:
                    return queries

    if text not in queries:
        queries.insert(0, text)

    return queries[:max_queries]


def build_search_queries(goal: str, max_queries: int = 20, use_ai: bool = True) -> List[str]:
    if use_ai:
        analysis = analyze_goal(goal)
    else:
        analysis = build_fallback(goal)

    industries = analysis.get("industries", []) or [goal]
    topics = analysis.get("topics", []) or [goal]

    base_keywords = [goal] + industries + topics

    suffixes = [
        "",
        " live",
        " livestream",
        " live stream",
        " stream",
        " webinar",
        " workshop",
        " online event",
        " live session",
        " talk",
        " panel",
        " ama",
        " networking",
    ]

    queries = []
    for keyword in base_keywords:
        keyword = str(keyword).strip()
        if not keyword:
            continue

        if keyword not in queries:
            queries.append(keyword)

        if use_ai:
            expanded = expand_topic(keyword)
            if isinstance(expanded, list) and expanded:
                for q in expanded:
                    q = str(q).strip()
                    if q and q not in queries:
                        queries.append(q)

        if len(queries) >= max_queries:
            break

    if len(queries) < max_queries:
        for keyword in base_keywords:
            for suffix in suffixes:
                query = f"{keyword}{suffix}".strip()
                if query and query not in queries:
                    queries.append(query)
                if len(queries) >= max_queries:
                    break
            if len(queries) >= max_queries:
                break

    if len(queries) < max_queries:
        for fallback in build_fallback_queries(goal, max_queries):
            if fallback not in queries:
                queries.append(fallback)
                if len(queries) >= max_queries:
                    break

    return queries[:max_queries]


def deduplicate_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    results = []
    for event in events:
        url = event.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        results.append(event)
    return results


def classify_priority(score: int) -> str:
    if score >= 40:
        return "High"
    if score >= 20:
        return "Medium"
    return "Low"


def filter_and_score_events(
    events: List[Dict[str, Any]],
    analysis: Dict[str, Any],
    goal: str = "",
) -> List[Dict[str, Any]]:
    for event in events:
        score = calculate_relevance(
            event,
            analysis,
            goal=goal,
        )
        event["_match_score"] = score
        event["priority"] = event.get(
            "priority",
            classify_priority(score),
        )
        event["interaction_tip"] = event.get(
            "interaction_tip",
            "Join with a relevant question or comment.",
        )

    filtered = [
        event
        for event in events
        if event.get("_match_score", 0) >= 0
    ]

    filtered.sort(
        key=lambda x: (
            {"LIVE": 0, "UPCOMING": 1, "COMPLETED": 2}.get(
                x.get("status", ""),
                99,
            ),
            -x.get("_match_score", 0),
        )
    )

    return filtered


def crawl_livestreams_with_ai(
    goal: str,
    limit: int = 20,
    platforms: List[str] = None,
    mode: str = "ai_then_fallback",
    **kwargs,
) -> Dict[str, Any]:
    # accept extra kwargs for compatibility with older callers
    use_ai = mode != "fallback_only"
    analysis = analyze_goal(goal) if use_ai else build_fallback(goal)

    if not analysis.get("industries") and not analysis.get("topics"):
        analysis = {
            "industries": [goal],
            "personas": [],
            "topics": [goal],
        }

    queries = build_search_queries(goal, max_queries=20, use_ai=use_ai)

    events = []
    platform_calls = {
        "youtube": crawl_youtube_live,
        "meetup": crawl_meetup,
        "x": crawl_x_live,
        "tiktok": crawl_tiktok_live,
    }

    if crawl_eventbrite:
        platform_calls["eventbrite"] = crawl_eventbrite

    if platforms:
        keys = [p.lower() for p in platforms]
    else:
        keys = list(platform_calls.keys())

    # persistent cache using sqlite
    cache_enabled = bool(kwargs.get("cache", True))
    cache_ttl = int(kwargs.get("cache_ttl", 300))
    cache_db = os.path.join(os.path.dirname(__file__), "..", "data", "platform_cache.sqlite")
    os.makedirs(os.path.dirname(cache_db), exist_ok=True)

    def _ensure_cache_db(conn):
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, ts REAL, v TEXT)"
        )

    def get_cache(key):
        try:
            conn = sqlite3.connect(cache_db)
            _ensure_cache_db(conn)
            cur = conn.execute("SELECT ts, v FROM cache WHERE k=?", (key,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            ts, v = row
            if time.time() - ts > cache_ttl:
                return None
            return json.loads(v)
        except Exception:
            return None

    def set_cache(key, value):
        try:
            conn = sqlite3.connect(cache_db)
            _ensure_cache_db(conn)
            conn.execute(
                "REPLACE INTO cache (k, ts, v) VALUES (?, ?, ?)",
                (key, time.time(), json.dumps(value, default=str)),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    # concurrency settings
    max_workers = min(max(1, len(keys)), 8)
    per_platform_timeout = int(kwargs.get("per_platform_timeout", 30))

    def run_crawler(platform_name, crawler_fn):
        try:
            # build cache key from platform + queries
            qhash = hashlib.sha256(json.dumps(queries, sort_keys=True).encode()).hexdigest()
            cache_key = f"{platform_name}:{qhash}:{limit}"

            if cache_enabled:
                cached = get_cache(cache_key)
                if cached is not None:
                    print(f"[AI Crawl Tool] Cache hit {platform_name} ({len(cached)} items)")
                    return platform_name, cached, None

            print(f"[AI Crawl Tool] Searching {platform_name}...")
            # try to pass optional headless kwarg to crawler if supported.
            # X and TikTok block anonymous scraping, so they always need a
            # real (logged-in) browser regardless of the global flag.
            crawler_opts = {}
            if platform_name in ("x", "tiktok") or kwargs.get("use_headless", False):
                crawler_opts["use_headless"] = True

            try:
                res = crawler_fn(queries, limit, **crawler_opts)
            except TypeError:
                res = crawler_fn(queries, limit)

            print(f"[AI Crawl Tool] {platform_name} found {len(res)} items")

            if cache_enabled:
                set_cache(cache_key, res)

            return platform_name, res, None
        except Exception as e:
            print(f"[AI Crawl Tool] {platform_name} error: {e}")
            return platform_name, [], e

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for platform in keys:
            crawler = platform_calls.get(platform)
            if not crawler:
                continue
            fut = executor.submit(run_crawler, platform, crawler)
            future_map[fut] = platform

        for fut in concurrent.futures.as_completed(future_map):
            platform = future_map.get(fut)
            try:
                plat, res, err = fut.result(timeout=per_platform_timeout)
                if res:
                    events.extend(res)
            except concurrent.futures.TimeoutError:
                print(f"[AI Crawl Tool] {platform} timed out after {per_platform_timeout}s")
            except Exception as e:
                print(f"[AI Crawl Tool] future error for {platform}: {e}")

    events = deduplicate_events(events)

    # First pass filtering/scoring
    events = filter_and_score_events(events, analysis, goal=goal)

    used_fallback = mode == "fallback_only"
    # If AI-first mode produced candidates but filtering removed them,
    # run fallback queries to try again.
    if mode == "ai_then_fallback" and not events:
        used_fallback = True
        fallback_analysis = build_fallback(goal)
        fallback_queries = build_search_queries(goal, max_queries=20, use_ai=False)
        fallback_events = []

        for platform in keys:
            crawler = platform_calls.get(platform)
            if not crawler:
                continue

            try:
                print(f"[AI Crawl Tool] Fallback searching {platform}...")
                results = crawler(fallback_queries, limit)
                print(f"[AI Crawl Tool] fallback {platform} found {len(results)} items")
                fallback_events.extend(results)
            except Exception as e:
                print(f"[AI Crawl Tool] fallback {platform} error: {e}")

            time.sleep(1)

        events = deduplicate_events(fallback_events)
        analysis = fallback_analysis
        queries = fallback_queries

        events = filter_and_score_events(events, analysis, goal=goal)

    return {
        "goal": goal,
        "analysis": analysis,
        "queries": queries,
        "platforms": keys,
        "events": events[:limit],
        "mode": mode,
        "used_fallback": used_fallback,
    }
