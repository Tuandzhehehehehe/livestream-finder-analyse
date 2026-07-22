"""
channel_crawler/tiktok_channel.py — TikTok Channel Info Crawler
===============================================================
Playwright + XHR intercept (/api/user/detail/, /api/live/detail/).
Dùng profile browser "tiktok_channel" từ crawler._browser.
"""

from __future__ import annotations

import re
from typing import Optional

from crawler._browser import launch_context
from channel_crawler._utils import extract_seller_info, parse_count, bulk_crawl
from channel_crawler.region_mapper import map_location

_PROFILE    = "tiktok_channel"
_API_PATHS  = ("/api/user/detail/", "/api/live/detail/")


def _username(url: str) -> Optional[str]:
    m = re.search(r"tiktok\.com/@([^/?&#]+)", url)
    return m.group(1).lstrip("@") if m else None


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

    try:
        with sync_playwright() as p:
            ctx  = launch_context(p, _PROFILE, headless=use_headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            page.on("response", lambda r: (
                payloads.append(r.json())
                if any(k in r.url for k in _API_PATHS) else None
            ))

            print(f"[TikTok] → {profile_url}")
            try:
                page.goto(profile_url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[TikTok] Nav error: {e}")

            for payload in payloads:
                if not user:
                    user = _parse_user(payload)
                if not live:
                    live = _parse_live(payload)

            # Scrape recent videos
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

            # DOM fallback if API missed
            dom: dict = {}
            if not user:
                try:
                    dom = page.evaluate("""() => {
                        const g = s => document.querySelector(s)?.innerText?.trim() || '';
                        return {
                            nickname:  g('[data-e2e="user-title"]'),
                            followers: g('[data-e2e="followers-count"]'),
                            bio:       g('[data-e2e="user-bio"]'),
                        };
                    }""") or {}
                except Exception:
                    pass

            ctx.close()
    except Exception as e:
        print(f"[TikTok] Crawl error: {e}")
        return None

    # ── Assemble ──────────────────────────────────────────────────────────────
    if user:
        followers    = user["followers"]
        verified     = user["verified"]
        region_raw   = user["region"]
        language     = user["language"]
        description  = user["bio"]
        channel_id   = user["id"]
        display_name = user["nickname"]
        seller       = extract_seller_info(description, extra={
            "is_seller":    user["is_commerce"],
            "commerce_raw": user["commerce_raw"],
        })
    elif dom:
        followers    = parse_count(dom.get("followers", ""))
        verified     = False
        region_raw   = ""
        language     = ""
        description  = dom.get("bio", "")
        channel_id   = un
        display_name = dom.get("nickname", un)
        seller       = extract_seller_info(description)
    else:
        print(f"[TikTok] Không lấy được dữ liệu: {channel_url}")
        return None

    region   = map_location(region_raw)
    activity = []
    if live and live["is_live"]:
        activity.append({"type": "live", "title": live["title"], "viewers": live["viewers"],
                         "started_at": str(live["started"]), "url": profile_url})
    activity += [{"type": "video", "url": v["url"], "views": parse_count(v["views"])} for v in videos[:10]]

    return {
        "platform":              "tiktok",
        "channel_id":            channel_id,
        "channel_url":           profile_url,
        "username":              f"@{un}",
        "channel_name":          display_name,
        "follower_count":        followers,
        "broadcast_freq_weekly": None,
        "last_live_at":          str(live["started"]) if live else None,
        "avg_viewers":           live["viewers"] if live else None,
        "total_livestreams":     0,
        "category":              None,
        "language":              language,
        "description":           description[:1000],
        "is_verified":           verified,
        "location_raw":          region_raw,
        "country":               region.get("country") or (region_raw.upper() if region_raw else None),
        "region_tag":            region.get("region_tag"),
        "timezone":              None,
        "seller_info":           seller,
        "activity_history":      activity,
        "channel_created_at":    None,
    }


def crawl_tiktok_channels_bulk(urls: list[str], use_headless: bool = True, delay_seconds: float = 3.0) -> list[dict]:
    return bulk_crawl(crawl_tiktok_channel, urls, "TikTok", delay=delay_seconds, use_headless=use_headless)
