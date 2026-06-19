from crawler.youtube import crawl_youtube_live
from crawler.meetup import crawl_meetup
from crawler.x import crawl_x_live
from crawler.tiktok import crawl_tiktok_live
from services.goal_analyzer import analyze_goal
from services.relevance_filter import calculate_relevance

try:
    from crawler.eventbrite import crawl_eventbrite
except Exception:
    crawl_eventbrite = None


def build_queries(goal_analysis):

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


def deduplicate(events):

    seen = set()

    results = []

    for event in events:

        url = event.get(
            "url",
            ""
        )

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)

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

        if score < 0:
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

    print(
        "\nSEARCH QUERIES"
    )

    for q in queries:
        print(q)

    print(
        "===================="
    )

    events = []

    # =====================
    # YOUTUBE
    # =====================

    try:

        youtube_events = (
            crawl_youtube_live(
                queries,
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
    # MEETUP
    # =====================

    try:

        meetup_events = (
            crawl_meetup(
                queries,
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
    # X
    # =====================

    try:

        x_events = (
            crawl_x_live(
                queries,
                limit,
                use_headless=use_headless,
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
    # TikTok
    # =====================

    try:

        tiktok_events = (
            crawl_tiktok_live(
                queries,
                limit,
                use_headless=use_headless,
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
    # EVENTBRITE
    # =====================

    if crawl_eventbrite:

        try:

            eventbrite_events = (
                crawl_eventbrite(
                    queries,
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