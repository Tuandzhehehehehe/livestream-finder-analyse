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

from channel_crawler._utils import extract_seller_info, compute_freq_weekly, bulk_crawl
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


def resolve_channel_id(client, url: str) -> Optional[str]:
    """URL kênh → channel ID (UCxxxxxxxx)."""
    id_type, value = _parse_url(url)
    if id_type == "id":
        return value
    try:
        resp = client.channels().list(part="id", **{id_type: value}).execute()
        items = resp.get("items", [])
        return items[0]["id"] if items else None
    except Exception as e:
        print(f"[YT] resolve_channel_id error: {e}")
        return None


# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch_channel(client, channel_id: str) -> Optional[dict]:
    try:
        resp  = client.channels().list(
            part="snippet,statistics,brandingSettings,topicDetails",
            id=channel_id,
        ).execute()
        items = resp.get("items", [])
        return items[0] if items else None
    except Exception as e:
        print(f"[YT] fetch_channel error ({channel_id}): {e}")
        return None


def _fetch_livestreams(client, channel_id: str, max_results: int = 30) -> list[dict]:
    events = []
    for event_type in ("completed", "live", "upcoming"):
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


# ── Main crawl function ───────────────────────────────────────────────────────

def crawl_youtube_channel(channel_url: str, max_live_history: int = 30) -> Optional[dict]:
    """Crawl thông tin kênh YouTube. Trả về dict cho channel_repository."""
    try:
        yt = _client()
    except RuntimeError as e:
        print(f"[YT] {e}")
        return None

    channel_id = resolve_channel_id(yt, channel_url)
    if not channel_id:
        print(f"[YT] Không resolve được channel_id: {channel_url}")
        return None

    raw = _fetch_channel(yt, channel_id)
    if not raw:
        print(f"[YT] Không lấy được dữ liệu kênh: {channel_id}")
        return None

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
    return bulk_crawl(crawl_youtube_channel, urls, "YouTube", delay=0, max_live_history=max_live_history)
