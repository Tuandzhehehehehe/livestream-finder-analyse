from crawler.youtube import crawl_youtube_live
from crawler.meetup import crawl_meetup
from crawler.x import crawl_x_live
from crawler.tiktok import crawl_tiktok_live
from crawler.linkedin import crawl_linkedin
from crawler.web_search import crawl_web
from services.goal_analyzer import analyze_goal
from services.relevance_filter import calculate_relevance

try:
    from crawler.eventbrite import crawl_eventbrite
except Exception:
    crawl_eventbrite = None


# Nền tảng event (LinkedIn, Meetup, Eventbrite) có hệ thống tìm kiếm riêng —
# chúng tự khớp keyword với nội dung chi tiết. Dùng từ khóa GỐC (không hậu tố)
# để tránh miss kết quả do query quá cụ thể.
EVENT_PLATFORMS = {"linkedin", "meetup", "eventbrite"}

# Nền tảng video (YouTube, X, TikTok) cần hậu tố để chọn đúng loại nội dung.
VIDEO_PLATFORMS = {"youtube", "x", "tiktok"}


def build_base_queries(goal_analysis, max_queries: int = 20):
    """Bộ từ khóa GỐC (không hậu tố) dùng cho LinkedIn, Meetup, Eventbrite.
    
    Nền tảng event đã có hệ thống tìm kiếm khớp với nội dung chi tiết,
    nên không cần thêm hậu tố như 'live', 'webinar'.
    """
    industries = goal_analysis.get("industries", []) or []
    personas = goal_analysis.get("personas", []) or []
    topics = goal_analysis.get("topics", []) or []

    base_terms = list(dict.fromkeys(industries + personas + topics))

    queries = []
    for term in base_terms:
        term = str(term).strip()
        if term and term not in queries:
            queries.append(term)
        if len(queries) >= max_queries:
            break

    return queries[:max_queries]


def build_queries(goal_analysis):
    """Bộ từ khóa MỞ RỘNG có hậu tố dùng cho YouTube, X, TikTok."""

    queries = []

    industries = goal_analysis.get(
        "industries",
        []
    )

    personas = goal_analysis.get(
        "personas",
        []
    )

    topics = goal_analysis.get(
        "topics",
        []
    )

    base_terms = []

    base_terms.extend(industries)
    base_terms.extend(personas)
    base_terms.extend(topics)

    base_terms = list(
        dict.fromkeys(base_terms)
    )

    for term in base_terms:

        term = str(term).strip()

        if not term:
            continue

        queries.extend(
            [
                term,
                f"{term} live",
                f"{term} livestream",
                f"{term} webinar",
                f"{term} workshop",
                f"{term} online event",
                f"{term} live session",
                f"{term} online workshop",
                f"{term} online training",
                f"{term} talk",
                f"{term} panel",
                f"{term} stream",
                f"{term} ama",
                f"{term} networking",
            ]
        )

    queries = list(
        dict.fromkeys(queries)
    )

    return queries


def normalize_event_url(url: str) -> str:
    if not url:
        return ""
    if "youtube.com/watch" in url:
        import urllib.parse as urlparse
        parsed = urlparse.urlparse(url)
        v = urlparse.parse_qs(parsed.query).get('v')
        if v:
            return f"https://youtube.com/watch?v={v[0]}"
        return url
    if "?" in url:
        return url.split("?")[0]
    return url


def deduplicate(events):
    seen = set()
    results = []
    for event in events:
        url = event.get("url", "")
        if not url:
            continue
        normalized = normalize_event_url(url)
        event["url"] = normalized
        if normalized in seen:
            continue
        seen.add(normalized)
        results.append(event)
    return results


def filter_relevant(
    events,
    analysis
):

    keywords = []

    keywords.extend(
        analysis.get(
            "industries",
            []
        )
    )

    keywords.extend(
        analysis.get(
            "topics",
            []
        )
    )

    keywords = [
        str(k).lower().strip()
        for k in keywords
        if str(k).strip()
    ]

    if not keywords:
        return events

    filtered = []

    for event in events:

        score = event.get(
            "_match_score",
            None
        )

        if score is None:
            text = (
                f"{event.get('title', '')} "
                f"{event.get('description', '')}"
            ).lower()

            score = 0

            for keyword in keywords:

                if keyword in text:
                    score += 1

            event["_match_score"] = score

        if score <= 0:
            continue

        filtered.append(event)

    filtered.sort(
        key=lambda x: x.get(
            "_match_score",
            0
        ),
        reverse=True
    )

    return filtered


def sort_events(events):

    priority = {
        "LIVE": 0,
        "UPCOMING": 1,
        "COMPLETED": 2,
    }

    events.sort(
        key=lambda x: (
            priority.get(
                x.get(
                    "status",
                    ""
                ),
                99
            ),
            -x.get(
                "_match_score",
                0
            ),
        )
    )

    return events


def search_livestreams(
    goal,
    limit=20,
    use_headless=False,
    platforms=None,
    platform_limits=None,
):

    analysis = analyze_goal(
        goal
    )

    if (
        not analysis.get("industries")
        and not analysis.get("topics")
    ):
        analysis = {
            "industries": [goal],
            "personas": [],
            "topics": [goal],
        }

    print(
        "\n===================="
    )

    print(
        "GOAL ANALYSIS"
    )

    print(
        analysis
    )

    print(
        "===================="
    )

    queries = build_queries(
        analysis
    )

    queries = queries[:20]

    # Từ khóa gốc (không hậu tố) cho nền tảng sự kiện chuyên nghiệp
    # Ưu tiên goal và topics trước vì industries thường quá chung chung.
    raw_terms = list(dict.fromkeys(
        [goal] +
        analysis.get("topics", []) +
        analysis.get("industries", [])
    ))
    base_queries = [str(t).strip() for t in raw_terms if str(t).strip()][:20]

    print(
        "\nSEARCH QUERIES"
    )

    for q in queries:
        print(q)

    print(
        f"\nBASE QUERIES (for event platforms): {base_queries[:5]}"
    )

    print(
        "===================="
    )

    events = []

    # =====================
    # YOUTUBE (dùng queries mở rộng)
    # =====================

    try:

        youtube_events = (
            crawl_youtube_live(
                base_queries,
                limit
            )
        )

        print(
            f"YouTube: {len(youtube_events)}"
        )

        events.extend(
            youtube_events
        )

    except Exception as e:

        print(
            f"YouTube Error: {e}"
        )

    # =====================
    # MEETUP (dùng base_queries gốc)
    # =====================

    try:

        meetup_events = (
            crawl_meetup(
                base_queries,
                limit
            )
        )

        print(
            f"Meetup: {len(meetup_events)}"
        )

        events.extend(
            meetup_events
        )

    except Exception as e:

        print(
            f"Meetup Error: {e}"
        )

    # =====================
    # X (dùng queries mở rộng)
    # =====================

    try:

        x_events = (
            crawl_x_live(
                queries,
                limit,
                use_headless=True,
            )
        )

        print(
            f"X: {len(x_events)}"
        )

        events.extend(
            x_events
        )

    except Exception as e:

        print(
            f"X Error: {e}"
        )

    # =====================
    # TikTok (dùng queries mở rộng)
    # =====================

    try:

        tiktok_events = (
            crawl_tiktok_live(
                base_queries,
                limit,
                use_headless=True,
            )
        )

        print(
            f"TikTok: {len(tiktok_events)}"
        )

        events.extend(
            tiktok_events
        )

    except Exception as e:

        print(
            f"TikTok Error: {e}"
        )

    # =====================
    # LinkedIn (dùng base_queries gốc)
    # =====================

    try:

        linkedin_events = (
            crawl_linkedin(
                base_queries,
                limit=platform_limits.get("linkedin", 10) if platform_limits else 10,
                use_headless=False
            )
            if platforms is None or "linkedin" in platforms
            else []
        )

        print(
            f"LinkedIn: {len(linkedin_events)}"
        )

        events.extend(
            linkedin_events
        )

    except Exception as e:

        print(
            f"LinkedIn Error: {e}"
        )

    # =====================
    # EVENTBRITE (dùng base_queries gốc)
    # =====================

    if crawl_eventbrite:

        try:

            eventbrite_events = (
                crawl_eventbrite(
                    base_queries,
                    limit
                )
            )

            print(
                f"Eventbrite: {len(eventbrite_events)}"
            )

            events.extend(
                eventbrite_events
            )

        except Exception as e:

            print(
                f"Eventbrite Error: {e}"
            )

    # =====================
    # DuckDuckGo Fallback
    # =====================
    
    if len(events) < 5:
        try:
            print("Few events found. Running Google Web Search fallback...")
            web_events = crawl_web(
                base_queries,
                limit=platform_limits.get("web", 15) if platform_limits else 15
            )
            print(f"Web Search (Google): {len(web_events)}")
            events.extend(web_events)
        except Exception as e:
            print(f"Web Search Error: {e}")

    # =====================
    # CLEAN
    # =====================

    events = deduplicate(
        events
    )
    for event in events:
        event["_match_score"] = (
            calculate_relevance(
                event,
                analysis
            )
        )

    events = filter_relevant(
        events,
        analysis
    )

    events.sort(
        key=lambda x: (

            {
                "LIVE": 0,
                "UPCOMING": 1,
                "COMPLETED": 2,
            }.get(
                x.get(
                    "status",
                    ""
                ),
                99
            ),

            -x.get(
                "_match_score",
                0
            ),
        )
    )

    print(
        f"\nFINAL EVENTS: {len(events)}"
    )

    return {
        "queries": queries,
        "analysis": analysis,
        "events": events[:limit],
    }