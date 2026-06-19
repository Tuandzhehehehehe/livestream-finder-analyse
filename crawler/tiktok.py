"""TikTok crawler.

TikTok search is gated behind login for anonymous users (the page only renders
empty skeleton cards), so we drive a real, logged-in Chromium via Playwright and
read the structured JSON the page fetches from TikTok's own search API instead of
scraping fragile HTML.

Run ``python -m crawler.session_login tiktok`` once to create the session.
"""

import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

from crawler._browser import DEFAULT_USER_AGENT, launch_context

headers = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}

# Browser-based crawling is slow; cap how many query variants we visit per run.
MAX_KEYWORDS = 4


def build_event(
    title,
    url,
    keyword,
    description="",
    create_time="",
    status="LIVE",
):
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


def format_time(timestamp):
    if not timestamp:
        return ""
    try:
        ts = int(timestamp)
        return (
            datetime.fromtimestamp(ts, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except Exception:
        return str(timestamp)


def _extract_items(payload):
    """Yield TikTok video item dicts from any search API JSON payload shape."""

    if not isinstance(payload, dict):
        return

    # Direct lists used by various TikTok endpoints.
    for key in ("item_list", "aweme_list", "itemList"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                yield item

    # The general search endpoint wraps items inside a "data" array.
    for entry in payload.get("data") or []:
        if not isinstance(entry, dict):
            continue
        for key in ("item", "aweme_info", "aweme"):
            item = entry.get(key)
            if isinstance(item, dict):
                yield item

    # Live search results.
    for entry in payload.get("data") or []:
        if isinstance(entry, dict) and "live_info" in entry:
            yield entry


def _normalize_item(item, keyword, status):
    """Convert a raw TikTok item dict into our event dict, or None."""

    video_id = (
        item.get("id")
        or item.get("aweme_id")
        or item.get("video_id")
    )

    author = item.get("author")
    if isinstance(author, dict):
        author_name = (
            author.get("uniqueId")
            or author.get("unique_id")
            or author.get("nickname")
            or ""
        )
    else:
        author_name = author or item.get("authorName") or ""

    if not video_id or not author_name:
        return None

    url = f"https://www.tiktok.com/@{author_name}/video/{video_id}"
    title = item.get("desc") or item.get("text") or "TikTok Video"
    description = item.get("desc") or ""
    create_time = format_time(item.get("createTime") or item.get("create_time"))

    return build_event(
        title,
        url,
        keyword,
        description=description,
        create_time=create_time,
        status=status,
    )


def _looks_logged_out(page):
    try:
        login_buttons = page.locator(
            "button:has-text('Log in'), a:has-text('Log in')"
        ).count()
    except Exception:
        login_buttons = 0
    return login_buttons > 0


def _crawl_headless(keywords, limit, seen_urls, events):
    """Drive a logged-in browser and read TikTok's search JSON responses."""

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = launch_context(p, "tiktok", headless=True)
        page = context.pages[0] if context.pages else context.new_page()

        payloads = []

        def on_response(response):
            if "/api/search/" not in response.url:
                return
            try:
                payloads.append(response.json())
            except Exception:
                pass

        page.on("response", on_response)

        # Browser crawling is slow, so cap how many query variants we visit.
        for keyword in keywords[:MAX_KEYWORDS]:
            for status, search_url in (
                ("LIVE", f"https://www.tiktok.com/search/live?q={quote_plus(keyword)}"),
                ("VIDEO", f"https://www.tiktok.com/search?q={quote_plus(keyword)}"),
            ):
                print(f"TikTok SEARCH ({status}): {keyword}")
                payloads.clear()

                try:
                    page.goto(search_url, timeout=45000)
                    page.wait_for_timeout(3500)
                    for _ in range(2):
                        page.mouse.wheel(0, 4000)
                        page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"TikTok navigation error: {e}")
                    continue

                if _looks_logged_out(page):
                    print(
                        "TikTok appears logged out. Run "
                        "'python -m crawler.session_login tiktok' once to "
                        "create a session."
                    )
                    context.close()
                    return events

                for payload in payloads:
                    for item in _extract_items(payload):
                        event = _normalize_item(item, keyword, status)
                        if not event or event["url"] in seen_urls:
                            continue
                        seen_urls.add(event["url"])
                        events.append(event)
                        if len(events) >= limit:
                            context.close()
                            return events

        context.close()

    return events


def _crawl_requests(keywords, limit, seen_urls, events):
    """Best-effort fallback using plain HTTP (works only when not gated)."""

    for keyword in keywords:
        url = f"https://www.tiktok.com/search?q={quote_plus(keyword)}"
        print(f"TikTok SEARCH (requests): {keyword}")

        try:
            response = requests.get(url, headers=headers, timeout=15)
        except Exception as e:
            print(f"TikTok Request Error: {e}")
            continue

        if response.status_code != 200:
            print(f"TikTok Error {response.status_code}")
            time.sleep(1)
            continue

        for payload in _extract_inline_json(response.text):
            for item in _extract_items(payload):
                event = _normalize_item(item, keyword, "VIDEO")
                if not event or event["url"] in seen_urls:
                    continue
                seen_urls.add(event["url"])
                events.append(event)
                if len(events) >= limit:
                    return events

        time.sleep(1)

    return events


def _extract_inline_json(html):
    """Pull inline rehydration JSON blobs out of a TikTok HTML page."""

    blobs = []

    for pattern in (
        r"<script id=\"__UNIVERSAL_DATA_FOR_REHYDRATION__\"[^>]*>(.*?)</script>",
        r"<script id=\"SIGI_STATE\"[^>]*>(.*?)</script>",
        r"window\['SIGI_STATE'\] = (\{.*?\});",
    ):
        match = re.search(pattern, html, re.S)
        if match:
            try:
                blobs.append(json.loads(match.group(1).strip()))
            except Exception:
                pass

    # SIGI_STATE keeps videos under ItemModule.
    for blob in list(blobs):
        item_module = blob.get("ItemModule") if isinstance(blob, dict) else None
        if isinstance(item_module, dict):
            blobs.append({"item_list": list(item_module.values())})

    return blobs


def crawl_tiktok_live(keywords, limit=20, use_headless=True):
    """Search TikTok for ``keywords`` and return a list of event dicts.

    ``use_headless`` drives a real (logged-in) browser via Playwright, which is
    required because TikTok blocks anonymous search. When False, a best-effort
    HTTP fallback is used (usually returns nothing while logged out).
    """

    events = []
    seen_urls = set()

    if use_headless:
        try:
            return _crawl_headless(keywords, limit, seen_urls, events)
        except Exception as e:
            print(f"TikTok headless error: {e}. Falling back to requests.")

    return _crawl_requests(keywords, limit, seen_urls, events)
