"""
crawler/x.py — X (Twitter) Live Events Crawler
===============================================
Drives a logged-in Playwright session and intercepts SearchTimeline GraphQL endpoints.
"""

from urllib.parse import quote_plus
from crawler._browser import launch_context

MAX_KEYWORDS = 4


def build_event(title: str, url: str, keyword: str, description: str = "", create_time: str = "") -> dict:
    return {
        "title": title,
        "platform": "X",
        "url": url,
        "description": description,
        "keyword": keyword,
        "status": "LIVE",
        "start_time": create_time,
        "scheduled_start_time": create_time,
        "actual_start_time": create_time,
        "actual_end_time": "",
    }


def _find_tweets(node, found: list):
    if isinstance(node, dict):
        if node.get("__typename") in ("Tweet", "TweetWithVisibilityResults"):
            tweet = node.get("tweet", node)
            if isinstance(tweet, dict) and tweet.get("legacy"):
                found.append(tweet)
        for value in node.values():
            _find_tweets(value, found)
    elif isinstance(node, list):
        for value in node:
            _find_tweets(value, found)


def _screen_name(tweet: dict) -> str:
    user = (tweet.get("core") or {}).get("user_results") or {}
    res = user.get("result") or {}
    legacy = res.get("legacy") or {}
    return legacy.get("screen_name") or (res.get("core") or {}).get("screen_name") or ""


def _normalize_tweet(tweet: dict, keyword: str) -> dict:
    legacy = tweet.get("legacy") or {}
    tweet_id = tweet.get("rest_id") or legacy.get("id_str")
    screen_name = _screen_name(tweet)
    if not tweet_id or not screen_name:
        return None

    text = legacy.get("full_text") or legacy.get("text") or ""
    return build_event(
        title=text or f"Post by @{screen_name}",
        url=f"https://x.com/{screen_name}/status/{tweet_id}",
        keyword=keyword,
        description=text,
        create_time=legacy.get("created_at") or "",
    )


def crawl_x_live(keywords: list, limit: int = 20, use_headless: bool = True) -> list:
    events = []
    seen_urls = set()

    # pyrefly: ignore [missing-import]
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            context = launch_context(p, "x", headless=use_headless)
            page = context.pages[0] if context.pages else context.new_page()
            payloads = []

            page.on("response", lambda r: payloads.append(r.json()) if "SearchTimeline" in r.url else None)

            for keyword in keywords[:MAX_KEYWORDS]:
                if len(events) >= limit:
                    break

                url = f"https://x.com/search?q={quote_plus(keyword + ' live')}&src=typed_query&f=live"
                print(f"X SEARCH: {keyword}")
                payloads.clear()

                try:
                    page.goto(url, timeout=45000)
                    page.wait_for_timeout(3500)
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"X nav error: {e}")
                    continue

                tweets = []
                for p_data in payloads:
                    _find_tweets(p_data, tweets)

                for tweet in tweets:
                    item = _normalize_tweet(tweet, keyword)
                    if item and item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        events.append(item)
                        if len(events) >= limit:
                            break

            context.close()
    except Exception as e:
        print(f"X crawl error: {e}")

    return events
