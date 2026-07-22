"""
channel_crawler/x_channel.py — X (Twitter) Account Info Crawler
================================================================
Playwright + GraphQL intercept (UserByScreenName/UserByRestId).
Dùng profile browser "x" từ crawler._browser.
"""

from __future__ import annotations

import re
from typing import Optional

from crawler._browser import launch_context
from channel_crawler._utils import extract_seller_info, parse_count, bulk_crawl
from channel_crawler.region_mapper import map_location

_PROFILE = "x"
_GQL_KEYS = ("UserByScreenName", "UserByRestId", "UserTweets")


def _screen_name(url: str) -> Optional[str]:
    m = re.search(r"(?:x\.com|twitter\.com)/@?([A-Za-z0-9_]{1,50})/?$", url)
    return m.group(1) if m else None


def _parse_user(payload: dict) -> Optional[dict]:
    data   = payload.get("data") or {}
    node   = data.get("user") or data.get("user_result") or {}
    result = node.get("result") or node
    if not isinstance(result, dict):
        return None
    legacy = result.get("legacy") or {}
    rest_id = result.get("rest_id") or legacy.get("id_str")
    sn      = legacy.get("screen_name")
    if not rest_id or not sn:
        return None
    return {
        "id":          str(rest_id),
        "screen_name": sn,
        "name":        legacy.get("name", sn),
        "followers":   int(legacy.get("followers_count", 0) or 0),
        "verified":    bool(result.get("is_blue_verified") or legacy.get("verified")),
        "location":    legacy.get("location", ""),
        "bio":         legacy.get("description", ""),
        "created_at":  legacy.get("created_at", ""),
    }


def _parse_tweets(payload: dict, sn: str) -> list[dict]:
    out = []
    def _walk(node):
        if isinstance(node, dict):
            if node.get("__typename") in ("Tweet", "TweetWithVisibilityResults"):
                tw  = node.get("tweet", node)
                leg = tw.get("legacy", {})
                tid = tw.get("rest_id") or leg.get("id_str")
                if tid:
                    out.append({
                        "type":       "tweet",
                        "id":         tid,
                        "text":       leg.get("full_text", "")[:280],
                        "created_at": leg.get("created_at", ""),
                        "url":        f"https://x.com/{sn}/status/{tid}",
                    })
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node: _walk(v)
    _walk(payload)
    return out[:10]


def crawl_x_channel(channel_url: str, use_headless: bool = True) -> Optional[dict]:
    """Crawl thông tin tài khoản X. Trả về dict cho channel_repository."""
    # pyrefly: ignore [missing-import]
    from playwright.sync_api import sync_playwright

    sn = _screen_name(channel_url)
    if not sn:
        print(f"[X] URL không hợp lệ: {channel_url}")
        return None

    profile_url  = f"https://x.com/{sn}"
    captured:    list[tuple[str, dict]] = []
    user:        Optional[dict] = None
    tweets:      list[dict]     = []

    try:
        with sync_playwright() as p:
            ctx  = launch_context(p, _PROFILE, headless=use_headless)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            page.on("response", lambda r: (
                captured.append((r.url, r.json()))
                if any(k in r.url for k in _GQL_KEYS) else None
            ))

            print(f"[X] → {profile_url}")
            try:
                page.goto(profile_url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"[X] Nav error: {e}")

            for url, payload in captured:
                if not user:
                    user = _parse_user(payload)
                if "UserTweets" in url and user:
                    tweets.extend(_parse_tweets(payload, sn))

            # DOM fallback
            dom: dict = {}
            if not user:
                try:
                    dom = page.evaluate("""() => ({
                        name:      document.querySelector('[data-testid="UserName"]')?.innerText?.trim() || '',
                        bio:       document.querySelector('[data-testid="UserDescription"]')?.innerText?.trim() || '',
                        location:  document.querySelector('[data-testid="UserLocation"]')?.innerText?.trim() || '',
                        followers: document.querySelector('[href$="/followers"] span')?.innerText?.trim() || '0',
                    })""") or {}
                except Exception:
                    pass

            ctx.close()
    except Exception as e:
        print(f"[X] Crawl error: {e}")
        return None

    if user:
        followers, verified  = user["followers"], user["verified"]
        location, bio        = user["location"], user["bio"]
        channel_id, name     = user["id"], user["name"]
        created_at           = user["created_at"]
    elif dom:
        followers  = parse_count(dom.get("followers", "0"))
        verified   = False
        location   = dom.get("location", "")
        bio        = dom.get("bio", "")
        channel_id = sn
        name       = dom.get("name", sn)
        created_at = ""
    else:
        print(f"[X] Không lấy được dữ liệu: {channel_url}")
        return None

    region = map_location(location)
    return {
        "platform":              "x",
        "channel_id":            channel_id,
        "channel_url":           profile_url,
        "username":              f"@{sn}",
        "channel_name":          name,
        "follower_count":        followers,
        "broadcast_freq_weekly": None,
        "last_live_at":          None,
        "avg_viewers":           None,
        "total_livestreams":     0,
        "category":              None,
        "language":              None,
        "description":           bio[:1000],
        "is_verified":           verified,
        "location_raw":          location,
        "country":               region.get("country"),
        "region_tag":            region.get("region_tag"),
        "timezone":              None,
        "seller_info":           extract_seller_info(bio),
        "activity_history":      tweets,
        "channel_created_at":    created_at,
    }


def crawl_x_channels_bulk(urls: list[str], use_headless: bool = True, delay_seconds: float = 3.0) -> list[dict]:
    return bulk_crawl(crawl_x_channel, urls, "X", delay=delay_seconds, use_headless=use_headless)
