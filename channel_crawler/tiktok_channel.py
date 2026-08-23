"""
channel_crawler/tiktok_channel.py — TikTok Channel Info Crawler
===============================================================
Playwright + XHR intercept (/api/user/detail/, /api/live/detail/,
/api/post/item_list/).
Dùng profile browser "tiktok_channel" từ crawler._browser.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Optional

from crawler._browser import launch_context
from channel_crawler._utils import extract_seller_info, parse_count, bulk_crawl, compute_freq_weekly
from channel_crawler.region_mapper import map_location

_PROFILE    = "tiktok_channel"
_API_PATHS  = (
    "/api/user/detail/",
    "/api/live/detail/",
    "/api/post/item_list/",   # video/live post history
    "/api/item/list/",        # alternate endpoint on some regions
)


def _username(url: str) -> Optional[str]:
    m = re.search(r"tiktok\.com/@([^/?&#]+)", url)
    if m:
        return m.group(1).lstrip("@")
    clean = url.strip()
    if clean.startswith("@"):
        return clean.lstrip("@")
    if "/" not in clean and "." not in clean and clean:
        return clean
    return None


def _parse_user(payload: dict) -> Optional[dict]:
    info  = payload.get("userInfo") or payload.get("UserInfo") or {}
    user  = info.get("user") or payload.get("user") or {}
    stats = info.get("stats") or payload.get("stats") or {}
    uid   = user.get("id") or user.get("uid")
    if not uid:
        return None
    return {
        "id":           str(uid),
        "nickname":     user.get("nickname", ""),
        "followers":    int(stats.get("followerCount", 0) or 0),
        "verified":     bool(user.get("verified", False)),
        "region":       user.get("region", ""),
        "language":     user.get("language", ""),
        "bio":          user.get("signature", ""),
        "is_commerce":  bool(user.get("commerceUserInfo") or user.get("isECommerceUser")),
        "commerce_raw": user.get("commerceUserInfo") or {},
        # createTime is epoch seconds when the account was created
        "create_time":  int(user.get("createTime", 0) or 0),
    }


def _parse_live(payload: dict) -> Optional[dict]:
    room = payload.get("data", {}).get("room") or payload.get("room") or {}
    if not room:
        return None
    return {
        "title":    room.get("title", ""),
        "viewers":  int(room.get("user_count", 0) or 0),
        "started":  room.get("create_time", ""),
        "is_live":  room.get("status") == 2,
    }


def _parse_post_list(payload: dict) -> list[dict]:
    """
    Trích xuất danh sách post/video từ /api/post/item_list/ hoặc /api/item/list/.
    Chỉ giữ is_live và create_time — đủ tính freq và last_live_at.
    """
    items = (
        payload.get("itemList")
        or payload.get("items")
        or payload.get("data", {}).get("itemList")
        or []
    )
    return [
        {
            "is_live":     bool(
                item.get("isActivityItem")
                or item.get("isLive")
                or "live" in (item.get("desc", "") or "").lower()
            ),
            "create_time": int(item.get("createTime", 0) or 0),
        }
        for item in items
    ]


def _epoch_to_iso(epoch: int) -> Optional[str]:
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except Exception:
        return None


def crawl_tiktok_channel(channel_url: str, use_headless: bool = True) -> Optional[dict]:
    """Crawl thông tin kênh TikTok. Trả về dict cho channel_repository."""
    # pyrefly: ignore [missing-import]
    from playwright.sync_api import sync_playwright

    un = _username(channel_url)
    if not un:
        print(f"[TikTok] URL không hợp lệ: {channel_url}")
        return None

    profile_url = f"https://www.tiktok.com/@{un}"
    payloads:   list[dict] = []
    user:       Optional[dict] = None
    live:       Optional[dict] = None
    all_posts:  list[dict] = []

    def _on_response(r):
        if any(k in r.url for k in _API_PATHS):
            try:
                payloads.append(r.json())
            except Exception:
                pass

    try:
        with sync_playwright() as p:
            ctx  = launch_context(p, _PROFILE, headless=use_headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            page.on("response", _on_response)

            print(f"[TikTok] → {profile_url}")
            try:
                page.goto(profile_url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                # Scroll để trigger video list API
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(2000)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"[TikTok] Nav error: {e}")

            # Parse payloads
            for payload in payloads:
                if not user:
                    user = _parse_user(payload)
                if not live:
                    live = _parse_live(payload)
                posts = _parse_post_list(payload)
                if posts:
                    all_posts.extend(posts)

            # Scrape recent videos DOM fallback (khi post list API không fire)
            videos = []
            try:
                videos = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('[data-e2e="user-post-item"]').forEach(el => {
                        const a = el.querySelector('a');
                        const v = el.querySelector('[data-e2e="video-views"]');
                        out.push({ url: a?.href || '', views: v?.innerText?.trim() || '0' });
                    });
                    return out.slice(0, 15);
                }""") or []
            except Exception:
                pass

            # DOM fallback if API missed user info
            dom: dict = {}
            if not user:
                try:
                    dom = page.evaluate("""() => {
                        const g = s => document.querySelector(s)?.innerText?.trim() || '';
                        return {
                            nickname:    g('[data-e2e="user-title"]'),
                            followers:   g('[data-e2e="followers-count"]'),
                            bio:         g('[data-e2e="user-bio"]'),
                        };
                    }""") or {}
                except Exception:
                    pass

            ctx.close()
    except Exception as e:
        print(f"[TikTok] Crawl error: {e}")
        return None

    # ── Assemble ──────────────────────────────────────────────────────────────
    if not user and not dom:
        print(f"[TikTok] Không lấy được dữ liệu: {channel_url}")
        return None

    if user:
        info = {
            "channel_id":       user["id"],
            "display_name":     user["nickname"],
            "followers":        user["followers"],
            "verified":         user["verified"],
            "region_raw":       user["region"],
            "language":         user["language"],
            "description":      user["bio"],
            "channel_created_at": _epoch_to_iso(user.get("create_time", 0)),
            "seller": extract_seller_info(user["bio"], extra={
                "is_seller":    user["is_commerce"],
                "commerce_raw": user["commerce_raw"],
            }),
        }
    else:  # dom fallback
        info = {
            "channel_id":       un,
            "display_name":     dom.get("nickname", un),
            "followers":        parse_count(dom.get("followers", "")),
            "verified":         False,
            "region_raw":       "",
            "language":         "",
            "description":      dom.get("bio", ""),
            "channel_created_at": None,
            "seller":           extract_seller_info(dom.get("bio", "")),
        }

    # ── Live history từ post list API ─────────────────────────────────────────
    live_posts        = [p for p in all_posts if p.get("is_live")]
    total_livestreams = len(live_posts)
    broadcast_freq_weekly = compute_freq_weekly(
        [{"started_at": _epoch_to_iso(p["create_time"])} for p in live_posts if p.get("create_time")],
        date_key="started_at",
    )

    # last_live_at: ưu tiên live đang diễn ra, sau đó là post gần nhất
    last_live_at = None
    if live and live["is_live"] and live.get("started"):
        try:
            last_live_at = _epoch_to_iso(int(live["started"]))
        except (ValueError, TypeError):
            last_live_at = str(live["started"])
    elif live_posts:
        last_live_at = _epoch_to_iso(max(live_posts, key=lambda p: p.get("create_time", 0))["create_time"])

    region   = map_location(info["region_raw"])
    activity = []
    if live and live["is_live"]:
        activity.append({
            "type": "live", "title": live["title"],
            "viewers": live["viewers"], "started_at": str(live["started"]), "url": profile_url,
        })
    activity += [{"type": "video", "url": v["url"], "views": parse_count(v["views"])} for v in videos[:10]]

    return {
        "platform":              "tiktok",
        "channel_id":            info["channel_id"],
        "channel_url":           profile_url,
        "username":              f"@{un}",
        "channel_name":          info["display_name"],
        "follower_count":        info["followers"],
        "broadcast_freq_weekly": broadcast_freq_weekly,
        "last_live_at":          last_live_at,
        "avg_viewers":           live["viewers"] if live else None,
        "total_livestreams":     total_livestreams,
        "category":              None,
        "language":              info["language"],
        "description":           info["description"][:1000],
        "is_verified":           info["verified"],
        "location_raw":          info["region_raw"],
        "country":               region.get("country") or (info["region_raw"].upper() if info["region_raw"] else None),
        "region_tag":            region.get("region_tag"),
        "timezone":              None,
        "seller_info":           info["seller"],
        "activity_history":      activity,
        "channel_created_at":    info["channel_created_at"],
    }


def crawl_tiktok_channels_bulk(urls: list[str], use_headless: bool = True, delay_seconds: float = 3.0) -> list[dict]:
    return bulk_crawl(crawl_tiktok_channel, urls, "TikTok", delay=delay_seconds, use_headless=use_headless)
