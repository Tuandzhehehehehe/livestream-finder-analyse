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

load_dotenv()


def get_youtube_client():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY not found in .env")
    return build("youtube", "v3", developerKey=api_key)


def search_by_event_type(keyword: str, event_type: str, limit: int = 20) -> dict:
    client = get_youtube_client()
    return client.search().list(
        part="snippet",
        q=keyword,
        type="video",
        eventType=event_type,
        order="date",
        maxResults=limit,
        relevanceLanguage="en",
    ).execute()


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


def crawl_youtube_live(keywords: list, limit: int = 20) -> list:
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
                    print(f"[YouTube] Search error for '{keyword}' ({status}): {e}")
        except Exception as e:
            print(f"[YouTube] Error processing keyword '{keyword}': {e}")

    priority = {"LIVE": 0, "UPCOMING": 1}
    events.sort(key=lambda x: (priority.get(x.get("status"), 99), x.get("scheduled_start_time", "")))
    return events