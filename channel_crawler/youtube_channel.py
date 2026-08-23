"""
channel_crawler/youtube_channel.py — YouTube Channel Info Crawler
=================================================================
Dùng YouTube Data API v3. Yêu cầu YOUTUBE_API_KEY trong .env.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv  # pyrefly: ignore [missing-import]

from channel_crawler._utils import extract_seller_info, compute_freq_weekly, bulk_crawl, with_retry
from channel_crawler.region_mapper import map_location

load_dotenv()


# ── API client ────────────────────────────────────────────────────────────────

def _client():
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY chưa được cấu hình trong .env")
    from googleapiclient.discovery import build  # pyrefly: ignore [missing-import]
    return build("youtube", "v3", developerKey=key)


# ── URL → channel ID resolution ───────────────────────────────────────────────

def _parse_url(url: str) -> tuple[str, str]:
    """Trả về (id_type, value): 'id'|'forHandle'|'forUsername', value."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    path   = parsed.path.strip("/")
    if path.startswith("channel/"):
        return "id", path.split("/")[1]
    if path.startswith("@"):
        return "forHandle", path.lstrip("@")
    if path.startswith("c/"):
        return "forHandle", path.split("/")[1]
    if path.startswith("user/"):
        return "forUsername", path.split("/")[1]
    # Could be /@handle at top level
    m = re.match(r"@(.+)", path)
    if m:
        return "forHandle", m.group(1)
    return "forHandle", path  # best guess


_QUOTA_EXCEEDED = False


def _check_quota_error(e: Exception) -> bool:
    global _QUOTA_EXCEEDED
    err_str = str(e).lower()
    if "quota" in err_str or "429" in err_str or "ratelimitexceeded" in err_str:
        if not _QUOTA_EXCEEDED:
            _QUOTA_EXCEEDED = True
            print("[YT] [WARNING] YouTube API hết Quota (429)! Tự động bỏ qua các request YouTube API tiếp theo.")
        return True
    return False


def resolve_channel_id(client, url: str) -> Optional[str]:
    """URL kênh → channel ID (UCxxxxxxxx)."""
    global _QUOTA_EXCEEDED
    if _QUOTA_EXCEEDED:
        return None
    id_type, value = _parse_url(url)
    if id_type == "id":
        return value
    try:
        resp = client.channels().list(part="id", **{id_type: value}).execute()
        items = resp.get("items", [])
        return items[0]["id"] if items else None
    except Exception as e:
        _check_quota_error(e)
        print(f"[YT] resolve_channel_id error: {e}")
        return None


# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch_channel(client, channel_id: str) -> Optional[dict]:
    global _QUOTA_EXCEEDED
    if _QUOTA_EXCEEDED:
        return None
    try:
        resp  = client.channels().list(
            part="snippet,statistics,brandingSettings,topicDetails",
            id=channel_id,
        ).execute()
        items = resp.get("items", [])
        return items[0] if items else None
    except Exception as e:
        if _check_quota_error(e):
            return None
        print(f"[YT] fetch_channel error ({channel_id}): {e}")
        # Re-raise SSL/EOF errors để with_retry có thể bắt và thử lại
        raise


def _fetch_livestreams(client, channel_id: str, max_results: int = 30) -> list[dict]:
    global _QUOTA_EXCEEDED
    if _QUOTA_EXCEEDED:
        return []
    events = []
    for event_type in ("completed", "live", "upcoming"):
        if _QUOTA_EXCEEDED:
            break
        try:
            resp = client.search().list(
                part="snippet", channelId=channel_id, type="video",
                eventType=event_type, order="date", maxResults=min(max_results, 50),
            ).execute()
            video_ids = [i["id"]["videoId"] for i in resp.get("items", []) if "videoId" in i.get("id", {})]
            if not video_ids:
                continue
            details = client.videos().list(
                part="liveStreamingDetails,contentDetails,statistics",
                id=",".join(video_ids),
            ).execute()
            snippet_map = {i["id"]["videoId"]: i["snippet"] for i in resp.get("items", []) if "videoId" in i.get("id", {})}
            for vid in details.get("items", []):
                live_d = vid.get("liveStreamingDetails", {})
                stats  = vid.get("statistics", {})
                dur    = _parse_duration(vid.get("contentDetails", {}).get("duration", ""))
                snip   = snippet_map.get(vid["id"], {})
                events.append({
                    "video_id":    vid["id"],
                    "title":       snip.get("title", ""),
                    "started_at":  live_d.get("actualStartTime") or live_d.get("scheduledStartTime", ""),
                    "ended_at":    live_d.get("actualEndTime", ""),
                    "viewers":     int(live_d.get("concurrentViewers", 0) or 0),
                    "view_count":  int(stats.get("viewCount", 0) or 0),
                    "like_count":  int(stats.get("likeCount", 0) or 0),
                    "duration_min": dur,
                    "event_type":  event_type,
                    "url":         f"https://youtube.com/watch?v={vid['id']}",
                })
        except Exception as e:
            if _check_quota_error(e):
                break
            print(f"[YT] fetch_livestreams ({event_type}): {e}")
    return events


def _parse_duration(iso: str) -> Optional[int]:
    """PT1H30M15S → phút."""
    if not iso:
        return None
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return None
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 60 + mn + (1 if s >= 30 else 0)


# ── Web-based fallback crawler (No API Key required) ─────────────────────────

def crawl_youtube_channel_web(channel_url: str) -> Optional[dict]:
    """Crawl channel metadata via public web scraping (requests + BeautifulSoup). Không dùng YouTube API."""
    import requests
    from bs4 import BeautifulSoup
    from channel_crawler._utils import _HEADERS, parse_count

    url = channel_url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")

        og_title = (soup.find("meta", property="og:title") or {}).get("content", "")
        og_desc = (soup.find("meta", property="og:description") or {}).get("content", "")
        
        title_tag = soup.find("title")
        page_title = title_tag.text.replace(" - YouTube", "").strip() if title_tag else ""
        channel_name = og_title or page_title or url.split("/")[-1]

        m = re.search(r"([\d,\.]+[KkMmBb]?)\s*(?:subscribers?|người đăng ký)", resp.text, re.IGNORECASE)
        follower_count = parse_count(m.group(1)) if m else 0

        ch_id_match = re.search(r"channel/(UC[a-zA-Z0-9_-]{22})", resp.text)
        channel_id = ch_id_match.group(1) if ch_id_match else ""

        seller = extract_seller_info(og_desc, extra={"brand_name": channel_name})
        seller["social_links"] = seller.pop("links", [])

        return {
            "platform":              "youtube",
            "channel_id":            channel_id,
            "channel_url":           url,
            "username":              url.split("/")[-1],
            "channel_name":          channel_name,
            "follower_count":        follower_count,
            "total_livestreams":     0,
            "broadcast_freq_weekly": None,
            "last_live_at":          None,
            "avg_viewers":           None,
            "category":              None,
            "language":              "en",
            "description":           og_desc[:1000],
            "is_verified":           False,
            "location_raw":          "",
            "country":               None,
            "region_tag":            None,
            "timezone":              None,
            "seller_info":           seller,
            "activity_history":      [],
            "channel_created_at":    "",
        }
    except Exception as e:
        print(f"[YT Web] Error crawling channel ({url}): {e}")
        return None


# ── Main crawl function ───────────────────────────────────────────────────────

def crawl_youtube_channel(channel_url: str, max_live_history: int = 30) -> Optional[dict]:
    """Crawl thông tin kênh YouTube. Tự động dùng Web Scraper nếu API tắt hoặc hết Quota."""
    env_val = os.getenv("ENABLE_YOUTUBE_API", "false").lower()
    use_api = env_val in ("true", "1", "yes", "on")

    global _QUOTA_EXCEEDED
    if not use_api or _QUOTA_EXCEEDED:
        return crawl_youtube_channel_web(channel_url)

    try:
        yt = _client()
    except Exception as e:
        return crawl_youtube_channel_web(channel_url)

    channel_id = resolve_channel_id(yt, channel_url)
    if not channel_id:
        return crawl_youtube_channel_web(channel_url)

    raw = None
    try:
        raw = with_retry(_fetch_channel, yt, channel_id, max_retries=1, base_delay=1.0, label="YT")
    except Exception as e:
        pass

    if not raw:
        return crawl_youtube_channel_web(channel_url)

    snippet  = raw.get("snippet", {})
    stats    = raw.get("statistics", {})
    branding = raw.get("brandingSettings", {})
    topics   = raw.get("topicDetails", {})

    live_events = _fetch_livestreams(yt, channel_id, max_results=max_live_history)

    # Avg viewers from completed streams
    view_counts = [e["view_count"] for e in live_events if e.get("view_count") and e.get("event_type") == "completed"]
    avg_viewers = int(sum(view_counts) / len(view_counts)) if view_counts else None

    # Last live date
    started = sorted([e["started_at"] for e in live_events if e.get("started_at")], reverse=True)
    last_live_at = started[0] if started else None

    # Category from Wikipedia topic URL
    topic_urls = topics.get("topicCategories", [])
    category = topic_urls[0].split("/")[-1].replace("_", " ") if topic_urls else None

    # Seller info reusing shared helper + YouTube-specific brand fields
    description = snippet.get("description", "")
    seller = extract_seller_info(description, extra={
        "brand_name": branding.get("channel", {}).get("title", ""),
        "keywords":   branding.get("channel", {}).get("keywords", ""),
    })
    # Rename links → social_links for YouTube convention
    seller["social_links"] = seller.pop("links", [])

    location_raw = snippet.get("country", "")
    region       = map_location(location_raw)

    return {
        "platform":              "youtube",
        "channel_id":            channel_id,
        "channel_url":           f"https://youtube.com/channel/{channel_id}",
        "username":              snippet.get("customUrl", ""),
        "channel_name":          snippet.get("title", ""),
        "follower_count":        int(stats.get("subscriberCount", 0) or 0),
        "total_livestreams":     len(live_events),
        "broadcast_freq_weekly": compute_freq_weekly(live_events, date_key="started_at"),
        "last_live_at":          last_live_at,
        "avg_viewers":           avg_viewers,
        "category":              category,
        "language":              snippet.get("defaultLanguage") or snippet.get("defaultAudioLanguage"),
        "description":           description[:1000],
        "is_verified":           False,
        "location_raw":          location_raw,
        "country":               region.get("country") or (location_raw.upper() if location_raw else None),
        "region_tag":            region.get("region_tag"),
        "timezone":              None,
        "seller_info":           seller,
        "activity_history":      live_events[:20],
        "channel_created_at":    snippet.get("publishedAt", ""),
    }


def crawl_youtube_channels_bulk(urls: list[str], max_live_history: int = 20) -> list[dict]:
    return bulk_crawl(
        crawl_youtube_channel, urls, "YouTube",
        delay=0.5, retry=1, retry_base_delay=1.0,
        max_live_history=max_live_history,
    )
