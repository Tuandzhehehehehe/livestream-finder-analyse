"""
services/relevance_filter.py — Relevance Scoring Engine
=========================================================
Tính điểm relevance cho sự kiện livestream dựa trên:
  - Keyword matching (title / description / url)
  - Active Learning Spam Classifier
  - MiniLM Semantic Similarity Scorer
  - Zero-Shot Cross-Encoder Scorer
"""

import re
from typing import Dict, Any

DEFAULT_POSITIVE = {"webinar", "conference", "summit", "networking", "startup", "founder", "ceo", "business", "saas", "investor"}
DEFAULT_NEGATIVE = {"free robux", "robux generator", "free adopt me", "crypto pump", "free vbucks"}
STOP_WORDS = {
    "livestream", "livestreams", "lĩnh", "vực", "tìm", "kiếm", "khách", "hàng",
    "ở", "về", "cho", "và", "and", "with", "the", "a", "an", "or",
    "in", "on", "at", "to", "by", "of", "for", "is", "are",
}

_SPAM_PATTERNS = [
    "free robux", "roblox giving free", "free robux giveaway",
    "robux generator", "free adopt me", "giving free robux",
]


def calculate_relevance(event: Dict[str, Any], analysis: Dict[str, Any], goal: str = "") -> int:
    title       = str(event.get("title", "")).lower()
    url         = str(event.get("url", "")).lower()
    description = str(event.get("description", "")).lower()
    text        = f"{title} {description}"

    # ── Spam Classifier (bỏ qua khi xác suất spam >= 85%) ────────────────
    try:
        from ai.spam_classifier import predict_spam
        is_spam, spam_prob = predict_spam(title=event.get("title", ""), description=event.get("description", ""))
        event["spam_probability"] = spam_prob
        if is_spam and spam_prob >= 0.85:
            event["is_spam_detected"] = True
            return 0
    except Exception as e:
        print(f"[Relevance Filter] Spam Classifier error: {e}")

    # ── Hard-coded spam/scam patterns ─────────────────────────────────────
    if any(p in title for p in _SPAM_PATTERNS):
        return 0

    score = 0

    # ── Keyword matching ──────────────────────────────────────────────────
    industries = analysis.get("industries", []) or []
    topics     = analysis.get("topics", []) or []
    personas   = analysis.get("personas", []) or []

    # Dedup để tránh cộng điểm hai lần cho cùng một từ khóa
    seen: set[str] = set()
    keywords: list[str] = []
    for k in industries + topics + personas:
        k_str = str(k).lower().strip()
        if k_str and k_str not in seen:
            seen.add(k_str)
            keywords.append(k_str)
    if goal:
        g_str = goal.lower().strip()
        if g_str not in seen:
            keywords.append(g_str)

    for keyword in keywords:
        if keyword in title: score += 40
    for keyword in keywords:
        if keyword in text:  score += 20
    for keyword in keywords:
        if keyword in url:   score += 5

    event_keyword = str(event.get("keyword", "")).lower().strip()
    if event_keyword and event_keyword in text:
        score += 10

    if goal:
        goal_words = [w for w in re.findall(r"[a-zA-Z0-9]+", goal.lower()) if w not in STOP_WORDS and len(w) > 2]
        if len(goal_words) >= 2:
            matched = [t for t in goal_words if t in text]
            if len(matched) >= 2:
                score += len(matched) * 20
        if goal.lower() in text:
            score += 5

    positive_words = [str(w).lower() for w in (analysis.get("positive_keywords") or DEFAULT_POSITIVE)]
    for word in positive_words:
        if word in text:
            score += 5

    negative_words = [str(w).lower() for w in (analysis.get("negative_keywords") or DEFAULT_NEGATIVE)]
    for word in negative_words:
        if word in text:
            score -= 15

    # ── MiniLM Semantic Similarity ────────────────────────────────────────
    try:
        from ai.minilm_scorer import compute_minilm_score
        target_queries = [goal] + keywords if goal else keywords
        minilm_score = compute_minilm_score(
            title=event.get("title", ""),
            description=event.get("description", ""),
            target_queries=target_queries,
        )
        event["minilm_score"] = minilm_score
        score = max(score, int(minilm_score))
        if minilm_score >= 60:
            score += 10
    except Exception as e:
        print(f"[Relevance Filter] MiniLM error: {e}")

    # ── Zero-Shot Cross-Encoder ───────────────────────────────────────────
    try:
        from ai.cross_encoder_scorer import compute_cross_encoder_score
        if goal:
            ce_score = compute_cross_encoder_score(
                title=event.get("title", ""),
                description=event.get("description", ""),
                goal=goal,
            )
            event["cross_encoder_score"] = ce_score
            if ce_score >= 60:
                score = max(score, int(ce_score))
    except Exception as e:
        print(f"[Relevance Filter] Cross-Encoder error: {e}")

    return score
