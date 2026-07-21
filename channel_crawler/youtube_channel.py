"""
channel_crawler/youtube_channel.py — YouTube Channel Info Crawler
=================================================================
Thu thập thông tin kênh YouTube qua YouTube Data API v3.

Không phụ thuộc vào bất kỳ module nào khác của dự án.
Yêu cầu: YOUTUBE_API_KEY trong môi trường hoặc file .env

Dữ liệu thu thập:
  - Thông tin cơ bản kênh (snippet, statistics, brandingSettings)
  - Lịch sử livestream gần đây (tối đa 50 buổi)
  - Tần suất phát sóng (broadcast_frequency)
  - Thông tin nhà bán hàng / creator (từ description + links)
  - Vị trí khu vực (country code từ API)
"""

from __future__ import annotations

import os
import re
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()


# ── YouTube API client ────────────────────────────────────────────────────────

def _get_yt_client():
    """Tạo YouTube API client. Raise nếu thiếu API key."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY không tìm thấy trong .env hoặc environment")
    # pyrefly: ignore [missing-import]
    from googleapiclient.discovery import build
    return build("youtube", "v3", developerKey=api_key)


# ── URL parsing ───────────────────────────────────────────────────────────────

def extract_channel_identifier(url: str) -> tuple[str, str]:
    """
    Phân tích URL kênh YouTube → (id_type, value).

    Ví dụ:
      https://youtube.com/channel/UCxxxxxx → ("id", "UCxxxxxx")
      https://youtube.com/c/ChannelName   → ("forHandle", "ChannelName")
      https://youtube.com/@handle         → ("forHandle", "@handle")
      https://youtube.com/user/username   → ("forUsername", "username")
    """
    parsed = urlparse(url)
    path   = parsed.path.rstrip("/")
    parts  = [p for p in path.split("/") if p]

    if not parts:
        raise ValueError(f"URL kênh YouTube không hợp lệ: {url}")

    if parts[0] == "channel" and len(parts) >= 2:
        return "id", parts[1]
    if parts[0] in ("c", "user") and len(parts) >= 2:
        return "forUsername", parts[1]
    if parts[0].startswith("@"):
        return "forHandle", parts[0]

    # Fallback: thử coi phần cuối là handle
    return "forHandle", f"@{parts[-1]}"


def resolve_channel_id(client, url: str) -> Optional[str]:
    """
    Resolve URL kênh YouTube → channel_id thực.
    Trả về None nếu không tìm thấy.
    """
    try:
        id_type, value = extract_channel_identifier(url)
        params = {
            "part": "id",
            id_type: value,
            "maxResults": 1,
        }
        resp = client.channels().list(**params).execute()
        items = resp.get("items", [])
        return items[0]["id"] if items else None
    except Exception as e:
        print(f"[YT] resolve_channel_id error ({url}): {e}")
        return None


# ── Channel info extraction ───────────────────────────────────────────────────

def _fetch_channel_details(client, channel_id: str) -> Optional[dict]:
    """Gọi channels.list với đầy đủ part."""
    try:
        resp = client.channels().list(
            part="snippet,statistics,brandingSettings,contentDetails,topicDetails",
            id=channel_id,
        ).execute()
        items = resp.get("items", [])
        return items[0] if items else None
    except Exception as e:
        print(f"[YT] fetch_channel_details error ({channel_id}): {e}")
        return None


def _extract_seller_info(snippet: dict, branding: dict) -> dict:
    """
    Phân tích description và brandingSettings để trích xuất thông tin seller/creator.

    Returns dict với các trường:
      brand_name, shop_url, contact_email, social_links, keywords
    """
    description = snippet.get("description", "")
    seller: dict = {
        "brand_name":    branding.get("channel", {}).get("title", ""),
        "keywords":      branding.get("channel", {}).get("keywords", ""),
        "contact_email": None,
        "shop_url":      None,
        "social_links":  [],
        "description_snippet": description[:500] if description else "",
    }

    if description:
        # Email
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", description)
        if emails:
            seller["contact_email"] = emails[0]

        # URLs
        urls = re.findall(r"https?://[^\s\)\"'<>]+", description)
        shop_patterns = re.compile(r"(shop|store|shopee|lazada|tiki|sendo|tiktokshop|amazon)", re.I)
        for u in urls:
            if shop_patterns.search(u):
                seller["shop_url"] = u
                break
        seller["social_links"] = urls[:10]  # Tối đa 10 links

    return seller


def _fetch_recent_livestreams(client, channel_id: str, max_results: int = 50) -> list[dict]:
    """
    Lấy danh sách livestream gần đây của kênh.
    Trả về list of {title, video_id, started_at, ended_at, viewers, duration_min}.
    """
    events = []
    try:
        for event_type in ("completed", "live", "upcoming"):
            try:
                resp = client.search().list(
                    part="snippet",
                    channelId=channel_id,
                    type="video",
                    eventType=event_type,
                    order="date",
                    maxResults=min(max_results, 50),
                ).execute()

                video_ids = [
                    item["id"]["videoId"]
                    for item in resp.get("items", [])
                    if "videoId" in item.get("id", {})
                ]
                if not video_ids:
                    continue

                # Fetch live streaming details
                details_resp = client.videos().list(
                    part="liveStreamingDetails,contentDetails,statistics",
                    id=",".join(video_ids),
                ).execute()

                for vid in details_resp.get("items", []):
                    live_d = vid.get("liveStreamingDetails", {})
                    content_d = vid.get("contentDetails", {})
                    stats_d = vid.get("statistics", {})

                    # Parse duration (ISO 8601: PT1H30M → 90 min)
                    duration_min = _parse_duration_minutes(content_d.get("duration", ""))

                    # Find snippet
                    snip = next(
                        (i["snippet"] for i in resp.get("items", [])
                         if i.get("id", {}).get("videoId") == vid["id"]),
                        {}
                    )

                    events.append({
                        "video_id":    vid["id"],
                        "title":       snip.get("title", ""),
                        "started_at":  live_d.get("actualStartTime") or live_d.get("scheduledStartTime", ""),
                        "ended_at":    live_d.get("actualEndTime", ""),
                        "viewers":     int(live_d.get("concurrentViewers", 0) or 0),
                        "view_count":  int(stats_d.get("viewCount", 0) or 0),
                        "like_count":  int(stats_d.get("likeCount", 0) or 0),
                        "duration_min": duration_min,
                        "event_type":  event_type,
                        "url":         f"https://youtube.com/watch?v={vid['id']}",
                    })
            except Exception as e:
                print(f"[YT] fetch_recent_livestreams ({event_type}): {e}")

    except Exception as e:
        print(f"[YT] fetch_recent_livestreams error: {e}")

    return events


def _parse_duration_minutes(iso_duration: str) -> Optional[int]:
    """Chuyển ISO 8601 duration (PT1H30M15S) → phút."""
    if not iso_duration:
        return None
    pattern = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
    m = pattern.match(iso_duration)
    if not m:
        return None
    h, mn, s = (int(x or 0) for x in m.groups())
    return h * 60 + mn + (1 if s >= 30 else 0)


def _compute_broadcast_frequency(events: list[dict]) -> Optional[float]:
    """
    Tính tần suất phát sóng trung bình (số buổi / tuần)
    từ danh sách livestream history.
    """
    if not events:
        return None

    timestamps = []
    for ev in events:
        ts_str = ev.get("started_at") or ev.get("ended_at")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            timestamps.append(ts)
        except Exception:
            pass

    if len(timestamps) < 2:
        return None

    timestamps.sort()
    earliest = timestamps[0]
    latest   = timestamps[-1]
    span_days = (latest - earliest).days

    if span_days < 1:
        return None

    weeks = span_days / 7.0
    return round(len(timestamps) / weeks, 2)


def _compute_avg_viewers(events: list[dict]) -> Optional[int]:
    """Tính lượt xem trung bình mỗi buổi live đã hoàn thành."""
    views = [
        ev["view_count"] for ev in events
        if ev.get("view_count") and ev.get("event_type") == "completed"
    ]
    if not views:
        return None
    return int(sum(views) / len(views))


# ── Main crawl function ───────────────────────────────────────────────────────

def crawl_youtube_channel(channel_url: str, max_live_history: int = 30) -> Optional[dict]:
    """
    Thu thập toàn bộ thông tin của một kênh YouTube.

    Args:
        channel_url:       URL trang kênh YouTube
        max_live_history:  Số buổi live gần nhất cần lấy (mỗi loại: completed/live/upcoming)

    Returns:
        dict chuẩn để truyền vào repository.upsert_channel(), hoặc None nếu thất bại.

    Keys trả về:
        platform, channel_id, channel_url, username, channel_name,
        follower_count, total_livestreams, broadcast_freq_weekly,
        last_live_at, avg_viewers, category, language, description,
        is_verified, location_raw, country, region_tag, timezone,
        seller_info, activity_history, channel_created_at
    """
    # Import region_mapper ở đây để tránh circular (cùng package)
    from channel_crawler.region_mapper import enrich_channel_with_region

    try:
        client = _get_yt_client()
    except RuntimeError as e:
        print(f"[YT] {e}")
        return None

    # 1. Resolve channel ID
    channel_id = resolve_channel_id(client, channel_url)
    if not channel_id:
        print(f"[YT] Không resolve được channel_id từ: {channel_url}")
        return None

    # 2. Fetch channel details
    raw = _fetch_channel_details(client, channel_id)
    if not raw:
        print(f"[YT] Không lấy được thông tin kênh: {channel_id}")
        return None

    snippet  = raw.get("snippet", {})
    stats    = raw.get("statistics", {})
    branding = raw.get("brandingSettings", {})
    topics   = raw.get("topicDetails", {})

    # 3. Fetch livestream history
    live_events = _fetch_recent_livestreams(client, channel_id, max_results=max_live_history)

    # 4. Compute derived metrics
    broadcast_freq  = _compute_broadcast_frequency(live_events)
    avg_viewers_val = _compute_avg_viewers(live_events)

    last_live_at = None
    completed = [e for e in live_events if e.get("started_at")]
    if completed:
        completed.sort(key=lambda e: e["started_at"], reverse=True)
        last_live_at = completed[0]["started_at"]

    # 5. Extract topic/category
    topic_categories = topics.get("topicCategories", [])
    category = None
    if topic_categories:
        # URL format: https://en.wikipedia.org/wiki/Music → "Music"
        category = topic_categories[0].split("/")[-1].replace("_", " ")

    # 6. Seller info
    seller_info = _extract_seller_info(snippet, branding)

    # 7. Location
    location_raw = snippet.get("country", "")  # ISO 2-letter country code from API
    # YouTube API returns ISO country code, map directly
    from channel_crawler.region_mapper import map_location
    region_info  = map_location(location_raw)

    # 8. Assemble channel data dict
    channel_data = {
        "platform":             "youtube",
        "channel_id":           channel_id,
        "channel_url":          f"https://youtube.com/channel/{channel_id}",
        "username":             snippet.get("customUrl", ""),
        "channel_name":         snippet.get("title", ""),
        "follower_count":       int(stats.get("subscriberCount", 0) or 0),
        "total_livestreams":    len(live_events),
        "broadcast_freq_weekly":broadcast_freq,
        "last_live_at":         last_live_at,
        "avg_viewers":          avg_viewers_val,
        "category":             category,
        "language":             snippet.get("defaultLanguage", "") or snippet.get("defaultAudioLanguage", ""),
        "description":          snippet.get("description", "")[:1000],
        "is_verified":          False,  # YouTube API không expose verified badge qua standard API
        "location_raw":         location_raw,
        "country":              region_info.get("country") or location_raw.upper() if location_raw else None,
        "region_tag":           region_info.get("region_tag"),
        "timezone":             None,
        "seller_info":          seller_info,
        "activity_history":     live_events[:20],  # lưu tối đa 20 buổi gần nhất
        "channel_created_at":   snippet.get("publishedAt", ""),
    }

    return channel_data


def crawl_youtube_channels_bulk(channel_urls: list[str], max_live_history: int = 20) -> list[dict]:
    """
    Crawl nhiều kênh YouTube cùng lúc.

    Args:
        channel_urls:     Danh sách URL kênh
        max_live_history: Số buổi live history mỗi kênh

    Returns:
        List các dict đã crawl thành công (bỏ qua kênh lỗi).
    """
    results = []
    for i, url in enumerate(channel_urls, 1):
        print(f"[YT] ({i}/{len(channel_urls)}) Crawling: {url}")
        data = crawl_youtube_channel(url, max_live_history)
        if data:
            results.append(data)
        else:
            print(f"[YT] ⚠ Bỏ qua: {url}")
    return results
