def calculate_relevance(event, analysis, goal=""):
    title = str(event.get('title', '')).lower()
    url = str(event.get('url', '')).lower()
    text = (
        f"{title} "
        f"{str(event.get('description', '')).lower()}"
    )

    # 🛑 1. Active Learning Spam Classifier (Solution 1)
    try:
        from ai.spam_classifier import predict_spam
        is_spam, spam_prob = predict_spam(
            title=event.get("title", ""),
            description=event.get("description", "")
        )
        event["spam_probability"] = spam_prob
        if is_spam:
            event["is_spam_detected"] = True
            return 0
    except Exception as e:
        print(f"[Relevance Filter] Spam Classifier error: {e}")

    # 🛑 Tự động lọc bỏ 100% phòng livestream rác / lừa đảo (Spam & Scam streams)
    spam_scam_patterns = [
        "free robux", "roblox giving free", "free robux giveaway", 
        "robux generator", "free adopt me", "giving free robux"
    ]
    if any(pattern in title for pattern in spam_scam_patterns):
        return 0

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

    PLATFORM_QUERY_TRUST = {"linkedin", "meetup", "eventbrite"}
    platform = str(event.get("platform", "")).lower().strip()
    if any(p in platform for p in PLATFORM_QUERY_TRUST):
        if event_keyword:
            keyword_is_relevant = False
            for kw in keywords:
                if kw and len(kw) > 2 and (
                    kw in event_keyword
                    or event_keyword in kw
                ):
                    keyword_is_relevant = True
                    break
            if keyword_is_relevant:
                title_text = str(event.get("title", "")).lower()
                title_has_keyword = any(
                    kw and len(kw) > 2 and kw in title_text
                    for kw in keywords
                )
                if title_has_keyword:
                    score = max(score, 15)
                else:
                    score = max(score, 5)

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
                score += len(matched_core_terms) * 20

    if goal and goal.lower() in text:
        score += 5

    positive_words = analysis.get("positive_keywords") or []
    for word in positive_words:
        if str(word).lower() in text:
            score += 5

    negative_words = analysis.get("negative_keywords") or []
    for word in negative_words:
        if str(word).lower() in text:
            score -= 15

    # ── MiniLM Semantic Similarity NLP Model ────────────────────────────
    try:
        from ai.minilm_scorer import compute_minilm_score
        target_queries = [goal] + keywords if goal else keywords
        minilm_sim_score = compute_minilm_score(
            title=event.get("title", ""),
            description=event.get("description", ""),
            target_queries=target_queries
        )
        event["minilm_score"] = minilm_sim_score
        
        final_score = max(score, int(minilm_sim_score))
        if minilm_sim_score >= 60:
            final_score += 10
        score = final_score
    except Exception as e:
        print(f"[Relevance Filter] MiniLM error: {e}")

    # ── Solution 2: Zero-Shot Cross-Encoder Scorer ──────────────────────
    try:
        from ai.cross_encoder_scorer import compute_cross_encoder_score
        if goal:
            ce_score = compute_cross_encoder_score(
                title=event.get("title", ""),
                description=event.get("description", ""),
                goal=goal
            )
            event["cross_encoder_score"] = ce_score
            if ce_score >= 60:
                score = max(score, int(ce_score))
    except Exception as e:
        print(f"[Relevance Filter] Cross-Encoder error: {e}")

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