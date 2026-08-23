"""
crawler/youtube.py — YouTube Live Events Crawler
==================================================
Searches YouTube API for live, upcoming, and completed event streams.
"""

import os
from typing import Optional
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
    if not video_ids or not youtube:
        return {}
    response = youtube.videos().list(
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


def crawl_youtube_playwright(
    keywords: list,
    limit: int = 20,
    mode: str = "all",  # "live", "upcoming", or "all"
    use_headless: bool = True,
    max_scrolls: int = 4,
) -> list:
    """
    Chuẩn hóa Playwright Scraper cho YouTube Search:
    - Sử dụng URL search parameter (`sp`) để lọc trực tiếp Live hoặc Upcoming.
    - Xử lý tự động đóng popup Cookie/Consent của Google.
    - Trích xuất siêu dữ liệu giàu thông tin: Badge LIVE, Concurrent Viewers, Scheduled Time, Channel Name & Handle.
    - Cuộn trang thông minh (Infinite Scroll) để thu thập đủ số lượng `limit`.
    """
    import re
    from urllib.parse import quote_plus
    # pyrefly: ignore [missing-import]
    from playwright.sync_api import sync_playwright
    from crawler._browser import launch_context

    events = []
    seen_urls = set()

    # URL filter parameter constants (YouTube 'sp' search parameter)
    SP_LIVE = "EgJAAQ%253D%253D"       # Filter: Live now
    SP_UPCOMING = "CAASBBABGAE%253D"   # Filter: Live/Upcoming this week

    search_modes = []
    if mode == "live":
        search_modes = [("LIVE", SP_LIVE)]
    elif mode == "upcoming":
        search_modes = [("UPCOMING", SP_UPCOMING)]
    else:
        # Default "all": Quét cả Live đang phát và Upcoming sự kiện sắp tới
        search_modes = [("LIVE", SP_LIVE), ("UPCOMING", SP_UPCOMING)]

    try:
        with sync_playwright() as p:
            context = launch_context(p, "youtube_live", headless=use_headless)
            page = context.pages[0] if context.pages else context.new_page()

            # Set viewport & user-agent chuẩn
            try:
                page.set_viewport_size({"width": 1440, "height": 900})
            except Exception:
                pass

            for kw in keywords[:5]:
                if len(events) >= limit:
                    break

                for status_mode, sp_param in search_modes:
                    if len(events) >= limit:
                        break

                    target_url = f"https://www.youtube.com/results?search_query={quote_plus(kw)}&sp={sp_param}"
                    print(f"[YouTube Playwright] [{status_mode}] Đang tìm kiếm: '{kw}'...")

                    try:
                        page.goto(target_url, timeout=25000, wait_until="domcontentloaded")
                        page.wait_for_timeout(1800)

                        # ── 1. Tự động đóng Google / YouTube Consent Popup ────────
                        consent_selectors = [
                            "button[aria-label*='Reject all']",
                            "button[aria-label*='Từ chối tất cả']",
                            "button[aria-label*='Accept all']",
                            "button[aria-label*='Chấp nhận tất cả']",
                            "ytd-consent-bump-v2-lightbox button",
                            "#dismiss-button",
                        ]
                        for c_sel in consent_selectors:
                            try:
                                btn = page.query_selector(c_sel)
                                if btn and btn.is_visible():
                                    btn.click()
                                    page.wait_for_timeout(1000)
                                    break
                            except Exception:
                                pass

                        # ── 2. Fallback: Nếu không có sp param, tương tác chip Live ──
                        chips = page.query_selector_all("yt-chip-cloud-chip-renderer")
                        for chip in chips:
                            try:
                                chip_txt = str(chip.inner_text() or "").strip().lower()
                                if status_mode == "LIVE" and chip_txt in ["live", "trực tiếp"]:
                                    chip.click()
                                    page.wait_for_timeout(1500)
                                    break
                            except Exception:
                                pass

                        # ── 3. Infinite Scroll để tải thêm video nếu cần ──────────
                        scroll_count = 0
                        while scroll_count < max_scrolls:
                            items_found = page.query_selector_all("ytd-video-renderer")
                            if len(items_found) >= (limit - len(events)) or len(items_found) >= 15:
                                break
                            page.evaluate("window.scrollBy(0, 1200)")
                            page.wait_for_timeout(1000)
                            scroll_count += 1

                        # ── 4. Bóc tách siêu dữ liệu DOM chi tiết ──────────────────
                        items = page.query_selector_all("ytd-video-renderer")
                        print(f"[YouTube Playwright] Tìm thấy {len(items)} items ({status_mode}) cho '{kw}'")

                        for item in items:
                            try:
                                title_elem = item.query_selector("#video-title")
                                if not title_elem:
                                    continue

                                title = str(title_elem.inner_text() or "").strip()
                                href = title_elem.get_attribute("href")
                                if not href or not title:
                                    continue

                                if href.startswith("/"):
                                    href = f"https://www.youtube.com{href}"

                                # Normalize video URL (loại bỏ timestamp/playlist params)
                                v_match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", href)
                                video_id = v_match.group(1) if v_match else ""
                                clean_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else href.split("&")[0]

                                if clean_url in seen_urls:
                                    continue

                                # Trích xuất mô tả / snippet
                                desc_elem = item.query_selector("#description-text, .metadata-snippet-container")
                                desc = str(desc_elem.inner_text() or "").strip() if desc_elem else ""

                                # Trích xuất thông tin kênh (Channel Name & URL)
                                ch_elem = item.query_selector("#channel-name a, #channel-info #text, #byline a")
                                channel_name = str(ch_elem.inner_text() or "").strip() if ch_elem else ""
                                ch_href = ch_elem.get_attribute("href") if ch_elem else ""
                                channel_url = f"https://www.youtube.com{ch_href}" if ch_href and ch_href.startswith("/") else ch_href

                                # Nhận diện chính xác trạng thái LIVE vs UPCOMING vs COMPLETED
                                is_live_badge = bool(item.query_selector(
                                    ".badge-style-type-live-now-alternate, badge-shape:has-text('LIVE'), badge-shape:has-text('TRỰC TIẾP'), [aria-label*='LIVE'], ytd-thumbnail-overlay-time-status-renderer[overlay-style='LIVE']"
                                ))

                                meta_line = item.query_selector("#metadata-line")
                                meta_text = str(meta_line.inner_text() or "").strip() if meta_line else ""
                                meta_text_lower = meta_text.lower()

                                # Trích xuất badge thời lượng tĩnh trên thumbnail (nếu có dạng 1:59:44 và không có badge LIVE -> VOD/Video đã kết thúc)
                                time_badge_elem = item.query_selector("ytd-thumbnail-overlay-time-status-renderer badge-shape, ytd-thumbnail-overlay-time-status-renderer span#text")
                                time_badge_text = str(time_badge_elem.inner_text() or "").strip() if time_badge_elem else ""

                                # Trích xuất số người xem trực tiếp (Concurrent Viewers)
                                viewers = ""
                                view_match = re.search(r"([\d.,KMkm]+\s*(?:watching|người đang xem|đang xem))", meta_text, re.IGNORECASE)
                                if view_match:
                                    viewers = view_match.group(1).strip()

                                # Trích xuất thời gian lên lịch phát sóng (Scheduled Time)
                                scheduled_time_str = ""
                                sched_match = re.search(r"((?:Scheduled for|Live in|Sắp diễn ra|Sắp chiếu|Premiere)\s*[^\n•]+)", meta_text, re.IGNORECASE)
                                if sched_match:
                                    scheduled_time_str = sched_match.group(1).strip()

                                # Dấu hiệu livestream ĐÃ KẾT THÚC (Streamed live X hours/days ago hoặc Đã phát trực tiếp)
                                is_ended_stream = (
                                    "streamed" in meta_text_lower
                                    or "đã phát trực tiếp" in meta_text_lower
                                    or ("views" in meta_text_lower and not viewers and not is_live_badge and not scheduled_time_str)
                                    or (bool(re.search(r"\b\d+:\d+\b", time_badge_text)) and not is_live_badge)
                                )

                                # Quyết định status chuẩn xác
                                if (is_live_badge or viewers) and not is_ended_stream:
                                    inferred_status = "LIVE"
                                elif scheduled_time_str or "scheduled" in meta_text_lower or "sắp" in meta_text_lower or "premiere" in meta_text_lower:
                                    inferred_status = "UPCOMING"
                                else:
                                    inferred_status = "COMPLETED"

                                # LỌC CHẶT THEO CHẾ ĐỘ NGƯỜI DÙNG CHỌN (Strict Mode Filter)
                                if mode == "live" and inferred_status != "LIVE":
                                    # Người dùng chỉ muốn Live đang phát -> Bỏ qua video đã kết thúc hoặc upcoming
                                    continue
                                elif mode == "upcoming" and inferred_status != "UPCOMING":
                                    # Người dùng chỉ muốn sắp diễn ra -> Bỏ qua video khác
                                    continue

                                seen_urls.add(clean_url)
                                events.append({
                                    "title": title,
                                    "platform": "YouTube",
                                    "url": clean_url,
                                    "video_id": video_id,
                                    "description": desc,
                                    "channel_name": channel_name,
                                    "channel_url": channel_url,
                                    "concurrent_viewers": viewers,
                                    "keyword": kw,
                                    "status": inferred_status,
                                    "start_time": scheduled_time_str,
                                    "scheduled_start_time": scheduled_time_str,
                                    "actual_start_time": "" if inferred_status == "UPCOMING" else "LIVE",
                                    "actual_end_time": "COMPLETED" if inferred_status == "COMPLETED" else "",
                                })

                                if len(events) >= limit:
                                    break
                            except Exception as parse_err:
                                print(f"[YouTube Playwright] Item parse error: {parse_err}")

                    except Exception as page_err:
                        print(f"[YouTube Playwright] Error scraping URL {target_url}: {page_err}")

    except Exception as e:
        print(f"[YouTube Playwright] Fatal Playwright error: {e}")

    # Sắp xếp ưu tiên: LIVE trước, sau đó tới UPCOMING
    status_order = {"LIVE": 0, "UPCOMING": 1, "COMPLETED": 2}
    events.sort(key=lambda x: status_order.get(x.get("status", "COMPLETED"), 99))
    return events


def crawl_youtube_live_web(keywords: list, limit: int = 20, mode: str = "all", use_headless: bool = True) -> list:
    """Wrapper tương thích gọi Playwright Scraper chuẩn hóa cho YouTube."""
    return crawl_youtube_playwright(keywords, limit=limit, mode=mode, use_headless=use_headless)


def crawl_youtube_live(
    keywords: list,
    limit: int = 20,
    use_api: Optional[bool] = None,
    mode: str = "all",
    use_headless: bool = True,
) -> list:
    """
    YouTube Crawler chính:
    - Ưu tiên Playwright Search Scraper chuẩn hóa khi `use_api=False` hoặc khi chưa có API Key / hết Quota.
    - Hỗ trợ đầy đủ bộ lọc Live, Upcoming và bóc tách metadata.
    """
    if use_api is None:
        env_val = os.getenv("ENABLE_YOUTUBE_API", "false").lower()
        use_api = env_val in ("true", "1", "yes", "on")

    if not use_api:
        print("[YouTube Crawler] Đang dùng Playwright Search Scraper chuẩn hóa cho YouTube...")
        return crawl_youtube_playwright(keywords, limit=limit, mode=mode, use_headless=use_headless)

    if not youtube:
        print("[YouTube Crawler] YOUTUBE_API_KEY chưa có -> Tự động chuyển sang Playwright Search Scraper...")
        return crawl_youtube_playwright(keywords, limit=limit, mode=mode, use_headless=use_headless)

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
                        print("[YouTube Crawler] [WARNING] YouTube API hết Quota (429) -> Tự động chuyển sang Playwright Search Scraper...")
                        return crawl_youtube_playwright(keywords, limit=limit, mode=mode, use_headless=use_headless)

        except Exception as e:
            print(f"Error expanding keyword '{keyword}': {e}")

    if not events:
        print("[YouTube Crawler] [WARNING] Không có kết quả từ API -> Fallback sang Playwright Search Scraper...")
        return crawl_youtube_playwright(keywords, limit=limit, mode=mode, use_headless=use_headless)

    priority = {"LIVE": 0, "UPCOMING": 1}
    events.sort(key=lambda x: (priority.get(x.get("status"), 99), x.get("scheduled_start_time", "")))
    return events