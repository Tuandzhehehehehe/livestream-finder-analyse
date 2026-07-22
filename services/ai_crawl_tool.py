import re
import time
import hashlib
import json
import os
import sqlite3
import concurrent.futures
from functools import lru_cache
from typing import List, Dict, Any

from crawler.youtube import crawl_youtube_live
from crawler.meetup import crawl_meetup
from crawler.x import crawl_x_live
from crawler.tiktok import crawl_tiktok_live
from crawler.linkedin import crawl_linkedin
from crawler.web_search import crawl_web
from services.goal_analyzer import build_fallback
from services.relevance_filter import calculate_relevance
from services.goal_profile_compiler import get_or_compile

try:
    from crawler.eventbrite import crawl_eventbrite
except Exception:
    crawl_eventbrite = None


@lru_cache(maxsize=1024)
def normalize_event_url(url: str) -> str:
    if not url:
        return ""
    if "youtube.com/watch" in url:
        import urllib.parse as urlparse
        parsed = urlparse.urlparse(url)
        v = urlparse.parse_qs(parsed.query).get('v')
        if v:
            return f"https://youtube.com/watch?v={v[0]}"
        return url
    if "?" in url:
        return url.split("?")[0]
    return url


def deduplicate_events(events: List[Dict[str, Any]], seen: set = None) -> List[Dict[str, Any]]:
    """
    Loại bỏ trùng lặp URL bằng Streaming / Memoized Normalization.
    """
    if seen is None:
        seen = set()
    results = []
    for event in events:
        raw_url = event.get("url", "")
        if not raw_url:
            continue
        normalized = normalize_event_url(raw_url)
        if normalized not in seen:
            seen.add(normalized)
            event["url"] = normalized
            results.append(event)
    return results

def infer_event_status(event: Dict[str, Any]) -> str:
    """Nhận diện trạng thái phát trực tiếp (LIVE) thực tế."""
    status = str(event.get("status", "")).upper()
    
    title = str(event.get("title", "")).lower()
    desc = str(event.get("description", "")).lower()
    text = f"{title} {desc}"
    
    # Chỉ gán LIVE nếu có các cụm từ khẳng định đang phát sóng trực tiếp ngay lúc này
    strict_live_phrases = [
        "🔴 live", "live now", "happening now", "watching now", "online now", 
        "đang phát trực tiếp", "streaming live now", "[live now]", "live stream now"
    ]
    
    if any(phrase in text for phrase in strict_live_phrases):
        return "LIVE"
        
    return status if status else "UPCOMING"


def time_filter_events(events: List[Dict[str, Any]], max_past_days: int = 7) -> List[Dict[str, Any]]:
    """
    Loại bỏ các sự kiện đã quá cũ hoặc sai trạng thái:
    - COMPLETED: giữ lại nếu kết thúc trong vòng max_past_days ngày qua
    - UPCOMING: loại nếu scheduled_start_time đã qua hơn 1 ngày
    - LIVE: giữ lại nếu không có thông tin thời gian hoặc còn trong ngưỡng hợp lệ
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    cutoff_past = now - timedelta(days=max_past_days)
    cutoff_upcoming = now - timedelta(days=1)
    results = []

    for event in events:
        # Tự động cập nhật status thông minh
        event["status"] = infer_event_status(event)
        status = event["status"]


        # --- Parse các mốc thời gian ---
        def _parse(dt_str):
            if not dt_str:
                return None
            try:
                return datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
            except Exception:
                return None

        actual_end = _parse(event.get("actual_end_time"))
        actual_start = _parse(event.get("actual_start_time"))
        scheduled = _parse(event.get("scheduled_start_time")) or _parse(event.get("start_time"))

        if status == "COMPLETED":
            # Loại sự kiện đã kết thúc quá lâu
            if actual_end and actual_end < cutoff_past:
                continue
            # Nếu có actual_start nhưng không có actual_end, kiểm tra actual_start
            if not actual_end and actual_start and actual_start < cutoff_past:
                continue

        elif status == "UPCOMING":
            # Loại nếu scheduled_start_time đã qua hơn 1 ngày
            if scheduled and scheduled < cutoff_upcoming:
                continue

        # --- Fallback cho MỌI status: nếu không có timestamp, quét NĂM trong TITLE ---
        # Chỉ quét title (không quét description vì description hay chứa năm không liên quan)
        if not actual_end and not actual_start and not scheduled:
            import re as _re
            title = str(event.get("title", ""))
            years_in_title = [int(y) for y in _re.findall(r'\b(20\d{2})\b', title)]
            if years_in_title:
                max_year = max(years_in_title)
                if max_year < now.year:
                    # Năm mới nhất trong title đã qua → sự kiện cũ, bỏ qua
                    continue

        elif status == "LIVE":
            # Nếu có actual_end thì thực ra đã kết thúc -> bỏ qua nếu quá cũ
            if actual_end and actual_end < cutoff_past:
                continue

        results.append(event)

    removed = len(events) - len(results)
    if removed > 0:
        print(f"[Time Filter] Loại bỏ {removed} sự kiện cũ/sai trạng thái")
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
        event["score"] = score
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
        if event.get("_match_score", 0) >= 30  # Lọc thông minh: loại bỏ 100% spam Roblox/Givaway rác (< 30 điểm)
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
    force_recompile = bool(kwargs.get("force_recompile", False))

    # --- Goal Profile: gọi AI 1 lần, dùng lại cho mọi lần crawl cùng goal ---
    if use_ai:
        profile = get_or_compile(goal, force_recompile=force_recompile)
    else:
        profile = None

    # Build analysis dict từ profile (tương thích với filter_and_score_events)
    if profile:
        analysis = {
            "industries": profile.get("industries", []),
            "personas": profile.get("personas", []),
            "topics": profile.get("topics", []),
            "positive_keywords": profile.get("positive_keywords", []),
            "negative_keywords": profile.get("negative_keywords", []),
        }
        # Dùng search_queries đã compile sẵn từ profile
        queries = profile.get("search_queries", [])
        if not queries:
            queries = [goal]
    else:
        analysis = build_fallback(goal)
        if not analysis.get("industries") and not analysis.get("topics"):
            analysis = {"industries": [goal], "personas": [], "topics": [goal]}
        queries = [goal]

    # Từ khóa gốc (không hậu tố) cho nền tảng sự kiện chuyên nghiệp
    _raw_terms = list(dict.fromkeys(
        [goal] +
        analysis.get("topics", []) +
        analysis.get("industries", [])
    ))
    base_queries = [str(t).strip() for t in _raw_terms if str(t).strip()][:20]
    # Tập nền tảng chỉ dùng từ khóa gốc (không thêm hậu tố livestream/webinar)
    # Vì YouTube và TikTok đã có tuỳ chọn API/URL lọc riêng cho livestream, 
    # thêm hậu tố " live" sẽ làm mất các sự kiện có tiêu đề không chứa chữ "live".
    EVENT_ONLY_PLATFORMS = {"linkedin", "meetup", "eventbrite", "youtube", "tiktok"}

    events = []
    platform_calls = {
        "youtube": crawl_youtube_live,
        "meetup": crawl_meetup,
        "x": crawl_x_live,
        "tiktok": crawl_tiktok_live,
        "linkedin": crawl_linkedin,
        "web": crawl_web,
    }

    if crawl_eventbrite:
        platform_calls["eventbrite"] = crawl_eventbrite

    if platforms:
        expanded_keys = []
        for p in platforms:
            p_lower = str(p).lower().strip()
            if p_lower in ("video platforms", "video_platforms", "video flatform", "video_flatform", "video", "📹 video platforms (youtube, tiktok)"):
                expanded_keys.extend(["youtube", "tiktok"])
            elif p_lower in ("event platforms", "event_platforms", "events", "🤝 event platforms (meetup, linkedin, eventbrite)"):
                expanded_keys.extend(["meetup", "linkedin", "eventbrite"])
            else:
                expanded_keys.append(p_lower)
        keys = list(dict.fromkeys(expanded_keys))
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
            if platform_name in ("x", "tiktok", "linkedin"):
                # Always respect the caller's choice if provided, otherwise default to True
                crawler_opts["use_headless"] = kwargs.get("use_headless", True)
            else:
                crawler_opts["use_headless"] = kwargs.get("use_headless", False)

            # Chọn bộ từ khóa phù hợp theo loại nền tảng
            active_queries = base_queries if platform_name in EVENT_ONLY_PLATFORMS else queries

            try:
                res = crawler_fn(active_queries, limit, **crawler_opts)
            except TypeError:
                res = crawler_fn(active_queries, limit)

            print(f"[AI Crawl Tool] {platform_name} found {len(res)} items")

            if cache_enabled:
                set_cache(cache_key, res)

            return platform_name, res, None
        except Exception as e:
            print(f"[AI Crawl Tool] {platform_name} error: {e}")
            return platform_name, [], e

    seen_urls = set()

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
                    events.extend(deduplicate_events(res, seen=seen_urls))
            except concurrent.futures.TimeoutError:
                print(f"[AI Crawl Tool] {platform} timed out after {per_platform_timeout}s")
            except Exception as e:
                print(f"[AI Crawl Tool] future error for {platform}: {e}")

    # Lọc sự kiện cũ/sai trạng thái trước khi score
    events = time_filter_events(events)

    # First pass filtering/scoring
    events = filter_and_score_events(events, analysis, goal=goal)

    used_fallback = mode == "fallback_only"
    # If AI-first mode produced candidates but filtering removed them,
    # run fallback queries to try again.
    if mode == "ai_then_fallback" and not events:
        used_fallback = True
        fallback_analysis = build_fallback(goal)
        # Dùng queries từ profile nếu có, hoặc fallback queries
        fallback_queries = queries if queries else [goal]

        for platform in keys:
            crawler = platform_calls.get(platform)
            if not crawler:
                continue

            try:
                print(f"[AI Crawl Tool] Fallback searching {platform}...")
                results = crawler(fallback_queries, limit)
                events.extend(deduplicate_events(results, seen=seen_urls))
            except Exception as e:
                print(f"[AI Crawl Tool] fallback {platform} error: {e}")

            time.sleep(1)

        analysis = fallback_analysis
        queries = fallback_queries

        # Lọc sự kiện cũ/sai trạng thái
        events = time_filter_events(events)

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
