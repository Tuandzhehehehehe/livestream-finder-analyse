"""
channel_crawler/tiktok_channel.py — TikTok Channel Info Crawler
===============================================================
Thu thập thông tin kênh TikTok qua Playwright (Chromium persistent profile).

TikTok không có public API, nên cần dùng browser automation để:
  1. Intercept XHR response từ /api/user/detail/ → follower count, verified, region
  2. Scrape trang profile /@username → bio, live room status, recent videos

Yêu cầu:
  - playwright đã install: pip install playwright && playwright install chromium
  - Đã đăng nhập TikTok vào browser profile "tiktok_channel"
    (chạy một lần với headless=False để login thủ công)

Dùng lại: crawler._browser.launch_context để quản lý persistent browser profile.
"""

from __future__ import annotations

import re
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── Shared browser helpers (crawler._browser) ─────────────────────────────────
from crawler._browser import launch_context as _launch_context_base

_PROFILE_NAME = "tiktok_channel"


def _launch_context(playwright, headless: bool = True):
    """Khởi động Chromium persistent context dùng profile 'tiktok_channel'."""
    return _launch_context_base(playwright, _PROFILE_NAME, headless=headless)


# ── Username extraction ───────────────────────────────────────────────────────

def _extract_username(channel_url: str) -> Optional[str]:
    """
    Trích xuất username từ URL TikTok.
    VD: https://www.tiktok.com/@username → "username"
    """
    match = re.search(r"tiktok\.com/@([^/?&#]+)", channel_url)
    return match.group(1) if match else None


def _normalize_username(username: str) -> str:
    """Đảm bảo username không có @."""
    return username.lstrip("@")


# ── API response parsing ──────────────────────────────────────────────────────

def _parse_user_detail_api(payload: dict) -> Optional[dict]:
    """
    Phân tích response từ TikTok /api/user/detail/ endpoint.
    Trả về dict thông tin user cơ bản.
    """
    # Cấu trúc response: {userInfo: {user: {...}, stats: {...}}}
    user_info = (
        payload.get("userInfo") or
        payload.get("UserInfo") or
        {}
    )
    user  = user_info.get("user", {}) or payload.get("user", {})
    stats = user_info.get("stats", {}) or payload.get("stats", {})

    if not user and not stats:
        return None

    uid = user.get("id") or user.get("uid")
    if not uid:
        return None

    return {
        "tiktok_user_id":   str(uid),
        "unique_id":        user.get("uniqueId") or user.get("unique_id", ""),
        "nickname":         user.get("nickname", ""),
        "follower_count":   int(stats.get("followerCount", 0) or 0),
        "following_count":  int(stats.get("followingCount", 0) or 0),
        "heart_count":      int(stats.get("heartCount", 0) or 0),
        "video_count":      int(stats.get("videoCount", 0) or 0),
        "verified":         bool(user.get("verified", False)),
        "region":           user.get("region", ""),
        "language":         user.get("language", ""),
        "signature":        user.get("signature", ""),   # bio
        "avatar_url":       user.get("avatarLarger", "") or user.get("avatarMedium", ""),
        "is_live":          bool(user.get("roomId") or user.get("isUnderAge18") is False and user.get("openFavorite")),
        "room_id":          user.get("roomId"),
        "commerce_user":    bool(user.get("commerceUserInfo") or user.get("isECommerceUser", False)),
        "seller_info_raw":  user.get("commerceUserInfo") or {},
    }


def _parse_live_room_api(payload: dict) -> Optional[dict]:
    """
    Phân tích response từ /api/live/detail/ hoặc live room info.
    Trả về thông tin buổi live hiện tại nếu đang live.
    """
    room = (
        payload.get("data", {}).get("room") or
        payload.get("room") or
        {}
    )
    if not room:
        return None

    return {
        "room_id":      room.get("id", ""),
        "title":        room.get("title", ""),
        "viewer_count": int(room.get("user_count", 0) or 0),
        "like_count":   int(room.get("like_count", 0) or 0),
        "started_at":   room.get("create_time", ""),
        "is_live":      room.get("status") == 2,
    }


def _extract_recent_videos_from_page(page) -> list[dict]:
    """
    Scrape danh sách video gần đây từ trang profile đã load.
    Dùng DOM query để lấy thumbnail, link, view count.
    """
    try:
        items = page.evaluate("""() => {
            const videos = [];
            document.querySelectorAll('[data-e2e="user-post-item"]').forEach(el => {
                const link = el.querySelector('a');
                const views = el.querySelector('[data-e2e="video-views"]');
                videos.push({
                    url: link ? link.href : '',
                    views: views ? views.innerText.trim() : '0',
                });
            });
            return videos.slice(0, 15);
        }""")
        return items or []
    except Exception:
        return []


def _parse_view_count(view_str: str) -> int:
    """Chuyển '1.2M', '500K', '10K' → số nguyên."""
    if not view_str:
        return 0
    view_str = view_str.strip().upper().replace(",", "")
    try:
        if "M" in view_str:
            return int(float(view_str.replace("M", "")) * 1_000_000)
        if "K" in view_str:
            return int(float(view_str.replace("K", "")) * 1_000)
        return int(float(view_str))
    except Exception:
        return 0


def _extract_seller_info_tiktok(user_detail: dict) -> dict:
    """
    Trích xuất thông tin seller/creator từ dữ liệu TikTok user.
    """
    sig = user_detail.get("signature", "")
    seller: dict = {
        "is_seller":         user_detail.get("commerce_user", False),
        "seller_info_raw":   user_detail.get("seller_info_raw", {}),
        "contact_email":     None,
        "shop_url":          None,
        "bio":               sig[:500] if sig else "",
        "links":             [],
    }

    if sig:
        # Email trong bio
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", sig)
        if emails:
            seller["contact_email"] = emails[0]

        # URLs trong bio
        urls = re.findall(r"https?://[^\s\)\"'<>]+", sig)
        shop_re = re.compile(r"(shop|shopee|lazada|tiki|tiktokshop|amazon|store)", re.I)
        for u in urls:
            if shop_re.search(u):
                seller["shop_url"] = u
                break
        seller["links"] = urls[:10]

    return seller


# ── Main crawl functions ──────────────────────────────────────────────────────

def crawl_tiktok_channel(channel_url: str, use_headless: bool = True) -> Optional[dict]:
    """
    Thu thập thông tin đầy đủ của một kênh TikTok.

    Args:
        channel_url:   URL profile TikTok (VD: https://www.tiktok.com/@username)
        use_headless:  False để xem browser (debug / login lần đầu)

    Returns:
        dict chuẩn để truyền vào repository.upsert_channel(), hoặc None nếu thất bại.
    """
    from channel_crawler.region_mapper import map_location

    username = _extract_username(channel_url)
    if not username:
        print(f"[TikTok] Không parse được username từ: {channel_url}")
        return None

    username = _normalize_username(username)
    profile_url = f"https://www.tiktok.com/@{username}"

    user_detail_data: Optional[dict] = None
    live_room_data:   Optional[dict] = None
    api_payloads: list[dict] = []

    # pyrefly: ignore [missing-import]
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            context = _launch_context(p, headless=use_headless)  # reuses crawler._browser
            page = context.pages[0] if context.pages else context.new_page()

            # ── Intercept API responses ────────────────────────────────────────
            def _capture_response(resp):
                try:
                    url = resp.url
                    if "/api/user/detail/" in url or "/api/live/detail/" in url:
                        data = resp.json()
                        if isinstance(data, dict):
                            api_payloads.append(data)
                except Exception:
                    pass

            page.on("response", _capture_response)

            # ── Navigate to profile ────────────────────────────────────────────
            print(f"[TikTok] Đang truy cập: {profile_url}")
            try:
                page.goto(profile_url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                # Scroll để trigger lazy load
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[TikTok] Navigation error: {e}")

            # ── Parse API responses ────────────────────────────────────────────
            for payload in api_payloads:
                if not user_detail_data:
                    user_detail_data = _parse_user_detail_api(payload)
                if not live_room_data:
                    live_room_data = _parse_live_room_api(payload)

            # ── Scrape recent videos from DOM ──────────────────────────────────
            recent_videos = _extract_recent_videos_from_page(page)

            # ── Fallback: scrape stats từ DOM nếu API không capture được ──────
            dom_stats = {}
            if not user_detail_data:
                try:
                    dom_stats = page.evaluate("""() => {
                        const getNumber = (sel) => {
                            const el = document.querySelector(sel);
                            return el ? el.innerText.trim() : null;
                        };
                        return {
                            nickname: getNumber('[data-e2e="user-title"]'),
                            followers: getNumber('[data-e2e="followers-count"]'),
                            following: getNumber('[data-e2e="following-count"]'),
                            likes: getNumber('[data-e2e="likes-count"]'),
                            bio: getNumber('[data-e2e="user-bio"]'),
                        };
                    }""") or {}
                except Exception:
                    pass

            context.close()

    except Exception as e:
        print(f"[TikTok] Crawl error ({channel_url}): {e}")
        return None

    # ── Assemble channel data ─────────────────────────────────────────────────
    if user_detail_data:
        follower_count = user_detail_data.get("follower_count", 0)
        verified       = user_detail_data.get("verified", False)
        region_raw     = user_detail_data.get("region", "") or ""
        language       = user_detail_data.get("language", "")
        description    = user_detail_data.get("signature", "")
        channel_id     = user_detail_data.get("tiktok_user_id", username)
        display_name   = user_detail_data.get("nickname", username)
        seller_info    = _extract_seller_info_tiktok(user_detail_data)

    elif dom_stats:
        # Fallback từ DOM scrape
        follower_count = _parse_view_count(dom_stats.get("followers", "") or "")
        verified       = False
        region_raw     = ""
        language       = ""
        description    = dom_stats.get("bio", "")
        channel_id     = username
        display_name   = dom_stats.get("nickname", username)
        seller_info    = {"is_seller": False, "bio": description}

    else:
        print(f"[TikTok] Không lấy được dữ liệu cho: {channel_url}")
        return None

    # Region mapping
    region_info = map_location(region_raw)

    # Activity history từ live_room + recent videos
    activity_history: list[dict] = []
    if live_room_data and live_room_data.get("is_live"):
        activity_history.append({
            "type":        "live",
            "title":       live_room_data.get("title", ""),
            "viewers":     live_room_data.get("viewer_count", 0),
            "started_at":  str(live_room_data.get("started_at", "")),
            "url":         profile_url,
        })
    for v in recent_videos[:10]:
        activity_history.append({
            "type":   "video",
            "url":    v.get("url", ""),
            "views":  _parse_view_count(v.get("views", "0")),
        })

    channel_data = {
        "platform":              "tiktok",
        "channel_id":            channel_id,
        "channel_url":           profile_url,
        "username":              f"@{username}",
        "channel_name":          display_name,
        "follower_count":        follower_count,
        "broadcast_freq_weekly": None,        # TikTok không có live history API công khai
        "last_live_at":          live_room_data.get("started_at") if live_room_data else None,
        "avg_viewers":           live_room_data.get("viewer_count") if live_room_data else None,
        "total_livestreams":     0,            # sẽ tích luỹ qua các lần crawl
        "category":              None,
        "language":              language,
        "description":           str(description)[:1000] if description else "",
        "is_verified":           verified,
        "location_raw":          region_raw,
        "country":               region_info.get("country") or (region_raw.upper() if region_raw else None),
        "region_tag":            region_info.get("region_tag"),
        "timezone":              None,
        "seller_info":           seller_info,
        "activity_history":      activity_history,
        "channel_created_at":    None,
    }

    return channel_data


def crawl_tiktok_channels_bulk(
    channel_urls: list[str],
    use_headless: bool = True,
    delay_seconds: float = 3.0,
) -> list[dict]:
    """
    Crawl nhiều kênh TikTok tuần tự với delay giữa các lần.

    Args:
        channel_urls:   Danh sách URL profile TikTok
        use_headless:   Chạy headless hay không
        delay_seconds:  Thời gian nghỉ giữa các kênh (để tránh rate limit)

    Returns:
        List dict thành công (bỏ qua kênh lỗi).
    """
    results = []
    for i, url in enumerate(channel_urls, 1):
        print(f"[TikTok] ({i}/{len(channel_urls)}) Crawling: {url}")
        data = crawl_tiktok_channel(url, use_headless=use_headless)
        if data:
            results.append(data)
            print(f"[TikTok] ✅ {data['channel_name']} — {data['follower_count']:,} followers")
        else:
            print(f"[TikTok] ⚠ Bỏ qua: {url}")

        if i < len(channel_urls) and delay_seconds > 0:
            print(f"[TikTok] Chờ {delay_seconds}s trước kênh tiếp theo...")
            time.sleep(delay_seconds)

    return results
