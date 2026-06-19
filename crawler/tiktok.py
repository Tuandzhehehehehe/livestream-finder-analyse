import json
import re
import time
from datetime import datetime
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def build_event(title, url, keyword, description="", create_time=""):
    return {
        "title": title,
        "platform": "TikTok",
        "url": url,
        "description": description,
        "keyword": keyword,
        "status": "LIVE",
        "start_time": create_time,
        "scheduled_start_time": create_time,
        "actual_start_time": "",
        "actual_end_time": "",
    }


def extract_json(html):
    match = re.search(
        r"<script id=\"SIGI_STATE\"[^>]*>(.*?)</script>",
        html,
        re.S,
    )

    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    match = re.search(
        r"window\['SIGI_STATE'\] = (\{.*?\});",
        html,
        re.S,
    )

    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    return {}


def format_time(timestamp):
    if not timestamp:
        return ""
    try:
        ts = int(timestamp)
        return datetime.utcfromtimestamp(ts).isoformat() + "Z"
    except Exception:
        return str(timestamp)


def _fetch_html(url, use_headless=False):
    if use_headless:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_extra_http_headers({
                    "Accept-Language": "en-US,en;q=0.9",
                    "User-Agent": headers["User-Agent"],
                })
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=30000)
                html = page.content()
                try:
                    browser.close()
                except Exception:
                    pass
                return html
        except Exception as e:
            print(f"Playwright unavailable or error on TikTok: {e}. Falling back to requests.")

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=15,
        )
        if response.status_code == 200:
            return response.text
        print(f"TikTok Error {response.status_code}")
    except Exception as e:
        print(f"TikTok Request Error: {e}")

    return ""


def crawl_tiktok_live(keywords, limit=20, use_headless=False):
    events = []
    seen_urls = set()

    for keyword in keywords:
        variants = [
            keyword,
            f"{keyword} live",
            f"{keyword} livestream",
            f"{keyword} stream",
            f"{keyword} webinar",
            f"{keyword} workshop",
            f"{keyword} online event",
            f"{keyword} talk",
            f"{keyword} panel",
            f"{keyword} ama",
        ]

        for q in variants:
            query = quote_plus(q)
            url = f"https://www.tiktok.com/search?q={query}"

            print(f"TikTok SEARCH: {q}")

            html = _fetch_html(url, use_headless=use_headless)
            if not html:
                time.sleep(1)
                continue

        data = extract_json(html)
        items = data.get("ItemModule", {})

        for item in items.values():
            video_id = item.get("id")
            if not video_id:
                continue

            author = item.get("author") or item.get("authorName") or ""
            event_url = f"https://www.tiktok.com/@{author}/video/{video_id}" if author else f"https://www.tiktok.com/@unknown/video/{video_id}"

            if event_url in seen_urls:
                continue

            title = item.get("desc") or item.get("text") or "TikTok Video"
            description = item.get("desc") or ""
            create_time = format_time(item.get("createTime"))

            seen_urls.add(event_url)

            events.append(
                build_event(
                    title,
                    event_url,
                    keyword,
                    description=description,
                    create_time=create_time,
                )
            )

            if len(events) >= limit:
                return events

        if len(events) >= limit:
            return events

        time.sleep(1)

    return events
