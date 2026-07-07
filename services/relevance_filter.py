def calculate_relevance(event, analysis, goal=""):

    title = str(event.get('title', '')).lower()
    url = str(event.get('url', '')).lower()
    text = (
        f"{title} "
        f"{str(event.get('description', '')).lower()}"
    )

    score = 0

    industries = analysis.get("industries", []) or []
    topics = analysis.get("topics", []) or []
    personas = analysis.get("personas", []) or []

    # Deduplicate keywords to prevent duplicate scoring of the same concepts
    raw_keywords = industries + topics + personas
    keywords = []
    for k in raw_keywords:
        k_str = str(k).lower().strip()
        if k_str and k_str not in keywords:
            keywords.append(k_str)

    if goal:
        g_str = goal.lower().strip()
        if g_str not in keywords:
            keywords.append(g_str)

    # Nếu có trong title thì gần như chắc chắn đúng
    for keyword in keywords:
        if keyword in title:
            score += 40
            
    # Nếu có trong nội dung (description), rất quan trọng cho các sự kiện
    # không để keyword ở title (ví dụ: title="Web3 Summit", nội dung="Bàn về tokenization")
    for keyword in keywords:
        if keyword in text:
            score += 20
            
    for keyword in keywords:
        if keyword in url:
            score += 5

    # Boost score only if the crawler query keyword actually appears in the text
    event_keyword = str(event.get("keyword", "")).lower().strip()
    if event_keyword and event_keyword in text:
        score += 10

    # Platform trust boost: nếu nền tảng trả về sự kiện này dựa trên từ khóa tìm kiếm
    # nhưng từ khóa không xuất hiện trong đoạn văn bản cào được (vì nó nằm trong nội dung
    # chi tiết chưa cào hết), ta vẫn tin tưởng kết quả của nền tảng và cấp điểm cơ sở.
    if event_keyword:
        for kw in keywords:
            if kw and (kw in event_keyword or event_keyword in kw or
                       any(part in event_keyword for part in kw.split()) or
                       any(part in kw for part in event_keyword.split())):
                score += 15
                break

    # ── NEW: Platform query boost ──────────────────────────────────────────────
    # Các nền tảng như LinkedIn, Meetup, Eventbrite có hệ thống tìm kiếm riêng.
    # Nếu họ trả về sự kiện dựa trên từ khóa gốc (không hậu tố), điều đó chứng tỏ
    # từ khóa tồn tại ở đâu đó trong nội dung chi tiết của sự kiện — dù chúng ta
    # chưa cào được. Ta cấp điểm cơ sở để sự kiện vượt qua bộ lọc score > 0.
    PLATFORM_QUERY_TRUST = {"linkedin", "meetup", "eventbrite"}
    platform = str(event.get("platform", "")).lower().strip()
    if any(p in platform for p in PLATFORM_QUERY_TRUST):
        if event_keyword:
            keyword_is_relevant = False
            for kw in keywords:
                # Chỉ match khi keyword đầy đủ có trong event_keyword hoặc ngược lại
                # Không dùng partial word match để tránh false positive
                if kw and len(kw) > 2 and (
                    kw in event_keyword
                    or event_keyword in kw
                ):
                    keyword_is_relevant = True
                    break
            # Chỉ cấp điểm tin cậy nếu title cũng chứa keyword (không chỉ dựa vào search query)
            if keyword_is_relevant:
                # Kiểm tra title có chứa ít nhất 1 keyword không
                title_text = str(event.get("title", "")).lower()
                title_has_keyword = any(
                    kw and len(kw) > 2 and kw in title_text
                    for kw in keywords
                )
                if title_has_keyword:
                    score = max(score, 15)  # Chỉ boost khi title cũng match
                else:
                    score = max(score, 5)   # Boost nhẹ nếu chỉ keyword match
    # ── END: Platform query boost ──────────────────────────────────────────────

    # Intersection bonus: if the goal contains multiple distinct keywords (e.g. charity, tokenization)
    # and both are matched in the text, give a massive relevance boost!
    if goal:
        import re
        goal_words = re.findall(r'[a-zA-Z0-9]+', goal.lower())
        stop_words = {
            "livestream", "livestreams", "lĩnh", "vực", "tìm", "kiếm", "khách", "hàng", "ở", "về", "cho", 
            "và", "and", "with", "the", "a", "an", "or", "in", "on", "at", "to", "by", "of", "for", "is", "are"
        }
        core_terms = [w for w in goal_words if w not in stop_words and len(w) > 2]
        if len(core_terms) >= 2:
            matched_core_terms = [t for t in core_terms if t in text]
            if len(matched_core_terms) >= 2:
                # Add a big bonus for matching multiple core search concepts
                score += len(matched_core_terms) * 20

    if goal and goal.lower() in text:
        score += 5

    # Dùng positive/negative keywords từ profile nếu có, fallback sang danh sách mặc định
    positive_words = analysis.get("positive_keywords") or [
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
        if str(word).lower() in text:
            score += 5

    negative_words = analysis.get("negative_keywords") or [
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
        if str(word).lower() in text:
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