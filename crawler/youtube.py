"""
crawler/youtube.py — YouTube Live Events Crawler
==================================================
Searches YouTube API for live, upcoming, and completed event streams.
"""

import os
from datetime import datetime, timezone, timedelta
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from googleapiclient.discovery import build

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()


API_KEY = os.getenv("YOUTUBE_API_KEY")
youtube = None
if API_KEY:
    try:
        youtube = build("youtube", "v3", developerKey=API_KEY)
    except Exception as e:
        print(f"[WARNING] Không thể khởi tạo YouTube API client: {e}")
else:
    print("[WARNING] YOUTUBE_API_KEY chưa được thiết lập trong .env - Sẽ dùng Playwright Live Scraper cho YouTube.")


def search_by_event_type(keyword: str, event_type: str, limit: int = 20) -> dict:
    if not youtube:
        return {}
    return (
        youtube.search()
        .list(
            part="snippet",
            q=keyword,
            type="video",
            eventType=event_type,
            order="date",
            maxResults=limit,
            relevanceLanguage="en",
        )
        .execute()
    )


def get_video_details(video_ids: list) -> dict:
    if not video_ids:
        return {}
    client = get_youtube_client()
    response = client.videos().list(
        part="liveStreamingDetails",
        id=",".join(video_ids)
    ).execute()
    return {item["id"]: item.get("liveStreamingDetails", {}) for item in response.get("items", [])}


def build_event(snippet: dict, video_id: str, keyword: str, query: str, status: str, details: dict) -> dict:
    return {
        "title": snippet.get("title", ""),
        "platform": "YouTube",
        "url": f"https://youtube.com/watch?v={video_id}",
        "description": snippet.get("description", ""),
        "keyword": keyword,
        "search_query": query,
        "status": status,
        "start_time": snippet.get("publishedAt", ""),
        "scheduled_start_time": details.get("scheduledStartTime", ""),
        "actual_start_time": details.get("actualStartTime", ""),
        "actual_end_time": details.get("actualEndTime", ""),
    }


def is_valid_language(snippet: dict) -> bool:
    lang = snippet.get("defaultAudioLanguage", "")
    return not lang or lang.startswith("en") or lang.startswith("vi")


def is_valid_event(details: dict) -> bool:
    scheduled = details.get("scheduledStartTime")
    actual_start = details.get("actualStartTime")
    actual_end = details.get("actualEndTime")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)

    def _parse(s):
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00")) if s else None
        except Exception:
            return None

    actual_end_dt = _parse(actual_end)
    actual_start_dt = _parse(actual_start)
    scheduled_dt = _parse(scheduled)

    if actual_end_dt:
        return actual_end_dt >= cutoff
    if actual_start_dt:
        return actual_start_dt >= cutoff
    if not scheduled_dt:
        return True
    if scheduled_dt > (now + timedelta(days=30)) or scheduled_dt < (now - timedelta(days=1)):
        return False

    return True


def crawl_youtube_live_web(keywords, limit=20):
    """Playwright scraper cho YouTube Live streams: Tự động truy cập trang tìm kiếm và chọn tab Live/Trực tiếp."""
    events = []
    seen_urls = set()
    from urllib.parse import quote_plus
    from playwright.sync_api import sync_playwright
    from crawler._browser import launch_context

    try:
        with sync_playwright() as p:
            context = launch_context(p, "youtube_live", headless=True)
            page = context.pages[0] if context.pages else context.new_page()

            for kw in keywords[:4]:
                if len(events) >= limit:
                    break
                url = f"https://www.youtube.com/results?search_query={quote_plus(kw)}"
                try:
                    print(f"[YouTube Live Web] Truy cập tìm kiếm YouTube cho: '{kw}'...")
                    page.goto(url, timeout=25000)
                    page.wait_for_timeout(2000)

                    # Tự động tìm và bấm vào chip/tab "Live" hoặc "Trực tiếp"
                    chips = page.query_selector_all("yt-chip-cloud-chip-renderer")
                    live_chip = None
                    for chip in chips:
                        chip_text = str(chip.inner_text() or "").strip().lower()
                        if chip_text in ["live", "trực tiếp"]:
                            live_chip = chip
                            break

                    if live_chip:
                        print(f"[YouTube Live Web] Bấm tab '{live_chip.inner_text().strip()}'...")
                        live_chip.click()
                        page.wait_for_timeout(3000)
                    else:
                        print("[YouTube Live Web] Không thấy chip 'Live' - Thử bấm nút Bộ lọc (Filters)...")
                        filter_btn = page.query_selector("ytd-toggle-button-renderer:has-text('Filters'), ytd-toggle-button-renderer:has-text('Bộ lọc')")
                        if filter_btn:
                            filter_btn.click()
                            page.wait_for_timeout(1000)
                            live_opt = page.query_selector("ytd-search-filter-renderer:has-text('Live'), ytd-search-filter-renderer:has-text('Trực tiếp')")
                            if live_opt:
                                live_opt.click()
                                page.wait_for_timeout(3000)

                    items = page.query_selector_all("ytd-video-renderer")
                    print(f"[YouTube Live Web] Tìm thấy {len(items)} video trong tab Live")

                    for item in items:
                        title_elem = item.query_selector("#video-title")
                        if not title_elem:
                            continue
                        title = title_elem.inner_text().strip()
                        href = title_elem.get_attribute("href")
                        if not href:
                            continue
                        if href.startswith("/"):
                            href = f"https://www.youtube.com{href}"
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)

                        desc_elem = item.query_selector("#description-text")
                        desc = desc_elem.inner_text().strip() if desc_elem else ""

                        events.append({
                            "title": title,
                            "platform": "YouTube",
                            "url": href,
                            "description": desc,
                            "keyword": kw,
                            "status": "LIVE",
                            "start_time": "",
                            "actual_start_time": "",
                            "actual_end_time": ""
                        })
                        if len(events) >= limit:
                            break
                except Exception as e:
                    print(f"[YouTube Live Web] Lỗi cào cho từ khóa '{kw}': {e}")
    except Exception as e:
        print(f"[YouTube Live Web] Lỗi Playwright: {e}")

    return events


def crawl_youtube_live(keywords: list, limit: int = 20) -> list:
    if not youtube:
        print("[YouTube Crawler] YOUTUBE_API_KEY chưa có - tự động dùng Playwright Live Scraper cho YouTube...")
        return crawl_youtube_live_web(keywords, limit=limit)
    events = []
    seen_urls = set()


    for keyword in keywords:
        try:
            for status in ("live", "upcoming", "completed"):
                try:
                    status_upper = status.upper()
                    response = search_by_event_type(keyword, status, limit)
                    items = response.get("items", [])
                    video_ids = [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]
                    details_map = get_video_details(video_ids)

                    for item in items:
                        if "videoId" not in item.get("id", {}):
                            continue
                        snippet = item.get("snippet", {})
                        if not is_valid_language(snippet):
                            continue

                        video_id = item["id"]["videoId"]
                        details = details_map.get(video_id, {})

                        if status_upper == "UPCOMING" and not is_valid_event(details):
                            continue

                        url = f"https://youtube.com/watch?v={video_id}"
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)

                        events.append(build_event(snippet, video_id, keyword, keyword, status_upper, details))
                except Exception as e:
                    err_str = str(e)
                    print(f"Error crawling keyword '{keyword}' ({status}): {e}")
                    if "quota" in err_str.lower() or "429" in err_str or "rateLimitExceeded" in err_str:
                        print("[YouTube Crawler] [WARNING] YouTube API hết Quota (429) -> Tự động chuyển sang Playwright Live Scraper cho YouTube...")
                        return crawl_youtube_live_web(keywords, limit=limit)

        except Exception as e:
            print(f"Error expanding keyword '{keyword}': {e}")

    if not events:
        print("[YouTube Crawler] [WARNING] Không có kết quả từ API -> Fallback sang Playwright Live Scraper cho YouTube...")
        return crawl_youtube_live_web(keywords, limit=limit)

    priority = {"LIVE": 0, "UPCOMING": 1}
    events.sort(key=lambda x: (priority.get(x.get("status"), 99), x.get("scheduled_start_time", "")))
    return events