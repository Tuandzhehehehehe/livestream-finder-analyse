
from googleapiclient.discovery import build
from dotenv import load_dotenv
from services.topic_expander import expand_topic

from datetime import datetime
from datetime import timezone
from datetime import timedelta

import os

load_dotenv()

API_KEY = os.getenv(
    "YOUTUBE_API_KEY"
)

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

youtube = None
if API_KEY:
    try:
        youtube = build(
            "youtube",
            "v3",
            developerKey=API_KEY
        )
    except Exception as e:
        print(f"[WARNING] Không thể khởi tạo YouTube API client: {e}")
else:
    print("[WARNING] YOUTUBE_API_KEY chưa được thiết lập trong .env - Sẽ bỏ qua YouTube crawler.")



def search_by_event_type(
    keyword,
    event_type,
    limit=20
):
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
            relevanceLanguage="en"

        )
        .execute()
    )


def get_video_details(
    video_ids
):

    if not video_ids:
        return {}

    response = (
        youtube.videos()
        .list(
            part="liveStreamingDetails",
            id=",".join(video_ids)
        )
        .execute()
    )

    details = {}

    for item in response.get(
        "items",
        []
    ):

        details[
            item["id"]
        ] = item.get(
            "liveStreamingDetails",
            {}
        )

    return details


def build_event(
    snippet,
    video_id,
    keyword,
    query,
    status,
    details
):

    return {

        "title": snippet.get(
            "title",
            ""
        ),

        "platform": "YouTube",

        "url":
        f"https://youtube.com/watch?v={video_id}",

        "description":
        snippet.get(
            "description",
            ""
        ),

        "keyword": keyword,

        "search_query": query,

        "status": status,

        "start_time":
        snippet.get(
            "publishedAt",
            ""
        ),

        "scheduled_start_time":
        details.get(
            "scheduledStartTime",
            ""
        ),

        "actual_start_time":
        details.get(
            "actualStartTime",
            ""
        ),

        "actual_end_time":
        details.get(
            "actualEndTime",
            ""
        ),
    }


def is_valid_language(
    snippet
):

    lang = snippet.get(
        "defaultAudioLanguage",
        ""
    )

    if not lang:
        return True

    return (
        lang.startswith("en")
        or lang.startswith("vi")
    )


def is_valid_event(
    details
):
    from datetime import datetime, timezone, timedelta

    scheduled = details.get("scheduledStartTime")
    actual_start = details.get("actualStartTime")
    actual_end = details.get("actualEndTime")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)  # Không lấy sự kiện đã qua hơn 7 ngày

    def _parse(s):
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00")) if s else None
        except Exception:
            return None

    actual_end_dt = _parse(actual_end)
    actual_start_dt = _parse(actual_start)
    scheduled_dt = _parse(scheduled)

    # Sự kiện đã kết thúc: chỉ lấy nếu kết thúc trong 7 ngày qua
    if actual_end_dt:
        return actual_end_dt >= cutoff

    # Đang live nhưng có actual_start: chỉ giữ nếu bắt đầu trong 7 ngày qua
    if actual_start_dt:
        return actual_start_dt >= cutoff

    # Chưa bắt đầu (UPCOMING): cần có scheduled_start_time
    if not scheduled_dt:
        # Không có thông tin ngày giờ — không chắc là cũ, cho qua
        return True

    # Không lấy upcoming quá xa trong tương lai (> 30 ngày)
    if scheduled_dt > (now + timedelta(days=30)):
        return False

    # Loại upcoming đã qua hơn 1 ngày mà chưa bắt đầu
    if scheduled_dt < (now - timedelta(days=1)):
        return False

    return True


def crawl_youtube_live(
    keywords,
    limit=20
):
    if not youtube:
        print("[YouTube Crawler] YOUTUBE_API_KEY chưa có - tự động dùng Web Search fallback cho YouTube...")
        from crawler.web_search import crawl_web
        web_events = crawl_web(keywords, limit=limit)
        for ev in web_events:
            ev["platform"] = "YouTube"
        return web_events

    events = []
    seen_urls = set()


    for keyword in keywords:

        try:

            # Dùng keyword trực tiếp đã được expand sẵn từ Goal Profile,
            # không cần expand_topic ở đây nữa (tiết kiệm token AI)
            expanded_queries = [keyword]

            print(
                f"\nKeyword: {keyword}"
            )

            for query in expanded_queries:

                try:

                    live_response = (
                        search_by_event_type(
                            query,
                            "live",
                            limit
                        )
                    )

                    upcoming_response = (
                        search_by_event_type(
                            query,
                            "upcoming",
                            limit
                        )
                    )

                    completed_response = (
                        search_by_event_type(
                            query,
                            "completed",
                            limit
                        )
                    )

                    sources = [

                        (
                            "LIVE",
                            live_response
                        ),

                        (
                            "UPCOMING",
                            upcoming_response
                        ),

                        (
                            "COMPLETED",
                            completed_response
                        ),
                    ]

                    for status, response in sources:

                        ids = [

                            item["id"]["videoId"]

                            for item in response.get(
                                "items",
                                []
                            )

                            if "videoId"
                            in item["id"]
                        ]

                        details_map = (
                            get_video_details(
                                ids
                            )
                        )

                        for item in response.get(
                            "items",
                            []
                        ):

                            if (
                                "videoId"
                                not in item["id"]
                            ):
                                continue

                            snippet = item[
                                "snippet"
                            ]

                            if not is_valid_language(
                                snippet
                            ):
                                continue

                            video_id = item[
                                "id"
                            ][
                                "videoId"
                            ]

                            details = (
                                details_map.get(
                                    video_id,
                                    {}
                                )
                            )

                            if (
                                status
                                == "UPCOMING"
                            ):

                                print(
                                    f"""
UPCOMING CHECK
Title: {snippet.get('title')}
Scheduled: {details.get('scheduledStartTime')}
Actual Start: {details.get('actualStartTime')}
Actual End: {details.get('actualEndTime')}
"""
                                )

                                if not is_valid_event(
                                    details
                                ):
                                    continue

                            url = (
                                f"https://youtube.com/watch?v={video_id}"
                            )

                            if (
                                url
                                in seen_urls
                            ):
                                continue

                            seen_urls.add(
                                url
                            )

                            events.append(
                                build_event(
                                    snippet,
                                    video_id,
                                    keyword,
                                    query,
                                    status,
                                    details
                                )
                            )

                except Exception as e:

                    print(
                        f"Error crawling query '{query}': {e}"
                    )

        except Exception as e:

            print(
                f"Error expanding keyword '{keyword}': {e}"
            )

    priority = {

        "LIVE": 0,

        "UPCOMING": 1
    }

    events.sort(
        key=lambda x: (

            priority.get(
                x.get("status"),
                99
            ),

            x.get(
                "scheduled_start_time",
                ""
            )
        )
    )

    return events