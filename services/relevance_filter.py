"""
services/relevance_filter.py — Relevance Scoring Engine
=========================================================
Calculates domain-specific relevance scores for scraped event items.
"""

import re
from typing import Dict, Any

DEFAULT_POSITIVE = {"webinar", "conference", "summit", "networking", "startup", "founder", "ceo", "business", "saas", "investor"}
DEFAULT_NEGATIVE = {"gaming", "minecraft", "music", "song", "karaoke", "anime", "movie", "football", "valorant", "roblox", "pubg"}
STOP_WORDS = {"livestream", "livestreams", "lĩnh", "vực", "tìm", "kiếm", "khách", "hàng", "ở", "về", "cho", "và", "and", "with", "the", "a", "an", "or", "in", "on", "at", "to", "by", "of", "for"}


def calculate_relevance(event: Dict[str, Any], analysis: Dict[str, Any], goal: str = "") -> int:
    title = str(event.get('title', '')).lower()
    url = str(event.get('url', '')).lower()
    description = str(event.get('description', '')).lower()
    text = f"{title} {description}"

    score = 0
    raw_keywords = (analysis.get("industries") or []) + (analysis.get("topics") or []) + (analysis.get("personas") or [])
    keywords = list(dict.fromkeys([str(k).lower().strip() for k in raw_keywords if str(k).strip()]))
    if goal and goal.lower().strip() not in keywords:
        keywords.append(goal.lower().strip())

    for kw in keywords:
        if kw in title:
            score += 40
        if kw in text:
            score += 20
        if kw in url:
            score += 5

    event_kw = str(event.get("keyword", "")).lower().strip()
    if event_kw and event_kw in text:
        score += 10

    if goal:
        core_terms = [w for w in re.findall(r'[a-zA-Z0-9]+', goal.lower()) if w not in STOP_WORDS and len(w) > 2]
        if len(core_terms) >= 2:
            matched = [t for t in core_terms if t in text]
            if len(matched) >= 2:
                score += len(matched) * 20

    pos_words = [str(w).lower() for w in (analysis.get("positive_keywords") or DEFAULT_POSITIVE)]
    for w in pos_words:
        if w in text:
            score += 5

    neg_words = [str(w).lower() for w in (analysis.get("negative_keywords") or DEFAULT_NEGATIVE)]
    for w in neg_words:
        if w in text:
            score -= 15

    return score


def is_relevant(event: Dict[str, Any], goal: str, threshold: int = 0) -> bool:
    text = f"{event.get('title', '')} {event.get('description', '')}".lower()
    return (10 if goal.lower().strip() in text else 0) >= threshold