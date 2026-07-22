"""
crawler/tiktok.py — TikTok Live Events & Video Crawler
======================================================
Drives a logged-in Playwright session and intercepts TikTok search API JSON responses.
"""

from datetime import datetime, timezone
from urllib.parse import quote_plus
from crawler._browser import launch_context

MAX_KEYWORDS = 4


def format_time(timestamp) -> str:
    if not timestamp:
        return ""
    try:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return str(timestamp)


def build_event(title: str, url: str, keyword: str, description: str = "", create_time: str = "", status: str = "LIVE") -> dict:
    return {
        "title": title,
        "platform": "TikTok",
        "url": url,
        "description": description,
        "keyword": keyword,
        "status": status,
        "start_time": create_time,
        "scheduled_start_time": create_time,
        "actual_start_time": create_time if status == "LIVE" else "",
        "actual_end_time": "",
    }


def _extract_items(payload: dict):
    if not isinstance(payload, dict):
        return
    for key in ("item_list", "aweme_list", "itemList"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                yield item

    for entry in payload.get("data") or []:
        if isinstance(entry, dict):
            for key in ("item", "aweme_info", "aweme"):
                item = entry.get(key)
                if isinstance(item, dict):
                    yield item
            if "live_info" in entry:
                yield entry


def _normalize_item(item: dict, keyword: str, status: str) -> dict:
    video_id = item.get("id") or item.get("aweme_id") or item.get("video_id")
    author = item.get("author")
    author_name = (author.get("uniqueId") or author.get("unique_id") or author.get("nickname")) if isinstance(author, dict) else (author or item.get("authorName") or "")

    if not video_id or not author_name:
        return None

    return build_event(
        title=item.get("desc") or item.get("text") or "TikTok Video",
        url=f"https://www.tiktok.com/@{author_name}/video/{video_id}",
        keyword=keyword,
        description=item.get("desc") or "",
        create_time=format_time(item.get("createTime") or item.get("create_time")),
        status=status,
    )


def crawl_tiktok_live(keywords: list, limit: int = 20, use_headless: bool = True) -> list:
    events = []
    seen_urls = set()

    # pyrefly: ignore [missing-import]
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            context = launch_context(p, "tiktok", headless=use_headless)
            page = context.pages[0] if context.pages else context.new_page()
            payloads = []

            page.on("response", lambda r: payloads.append(r.json()) if "/api/search/" in r.url else None)

            for keyword in keywords[:MAX_KEYWORDS]:
                if len(events) >= limit:
                    break

                for status, search_url in (("LIVE", f"https://www.tiktok.com/search/live?q={quote_plus(keyword)}"), ("VIDEO", f"https://www.tiktok.com/search?q={quote_plus(keyword)}")):
                    print(f"TikTok SEARCH ({status}): {keyword}")
                    payloads.clear()

                    try:
                        page.goto(search_url, timeout=45000)
                        page.wait_for_timeout(3500)
                        page.mouse.wheel(0, 4000)
                        page.wait_for_timeout(1500)
                    except Exception as e:
                        print(f"TikTok nav error: {e}")
                        continue

                    for p_data in payloads:
                        for item in _extract_items(p_data):
                            ev = _normalize_item(item, keyword, status)
                            if ev and ev["url"] not in seen_urls:
                                seen_urls.add(ev["url"])
                                events.append(ev)
                                if len(events) >= limit:
                                    break

            context.close()
    except Exception as e:
        print(f"TikTok crawl error: {e}")

    return events
