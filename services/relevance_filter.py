def calculate_relevance(event, analysis, goal=""):

    text = (
        f"{event.get('title', '')} "
        f"{event.get('description', '')}"
    ).lower()

    score = 0

    industries = analysis.get(
        "industries",
        []
    )

    topics = analysis.get(
        "topics",
        []
    )

    personas = analysis.get(
        "personas",
        []
    )

    keywords = (
        industries
        + topics
        + personas
    )

    if goal:
        keywords.append(goal)

    for keyword in keywords:

        keyword = str(
            keyword
        ).lower()

        if keyword and keyword in text:
            score += 10

    # If the crawler attached the search keyword that found this event, boost score
    event_keyword = str(event.get("keyword", "")).lower()
    if event_keyword:
        for k in keywords:
            try:
                if str(k).lower() in event_keyword or event_keyword in text:
                    score += 10
                    break
            except Exception:
                continue

    if goal and goal.lower() in text:
        score += 5

    positive_words = [

        "webinar",
        "conference",
        "summit",
        "networking",
        "startup",
        "founder",
        "ceo",
        "business",
        "entrepreneur",
        "saas",
        "fundraising",
        "investor",
        "panel",
    ]

    for word in positive_words:

        if word in text:
            score += 5

    negative_words = [

        "gaming",
        "minecraft",
        "music",
        "song",
        "karaoke",
        "anime",
        "movie",
        "football",
        "valorant",
        "roblox",
        "pubg",
    ]

    for word in negative_words:

        if word in text:
            score -= 15

    return score


def is_relevant(event, goal, threshold=0):

    text = (
        f"{event.get('title', '')} "
        f"{event.get('description', '')}"
    ).lower()

    score = 0

    for keyword in [goal]:

        keyword = str(keyword).lower().strip()

        if keyword and keyword in text:
            score += 10

    return score >= threshold