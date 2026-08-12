"""
services/goal_analyzer.py — Goal Analysis & Expansion Engine
=============================================================
Analyzes business search goals to extract target industries, buyer personas,
and related topic synonyms using LLM or rule-based semantic mapping.
"""

import json
import re
from typing import Dict, List, Any
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from ai.llm_client import generate, extract_json

INDUSTRY_MAPPING = {
    "charity": ["charity", "nonprofit", "fundraising", "ngo", "social impact"],
    "startup": ["startup", "founder", "entrepreneur", "venture capital", "saas"],
    "fintech": ["fintech", "finance", "banking", "payments", "digital banking"],
    "ai": ["artificial intelligence", "machine learning", "generative ai", "llm", "automation"],
    "marketing": ["digital marketing", "seo", "content marketing", "growth marketing", "social media"],
    "ecommerce": ["ecommerce", "shopify", "amazon seller", "online store", "dropshipping"],
    "recruitment": ["recruitment", "hr", "talent acquisition", "hiring", "human resources"],
    "saas": ["saas", "software startup", "b2b software", "software founder"],
}


def build_fallback(goal: str) -> Dict[str, List[str]]:
    """Builds heuristic industries, personas, and topics when LLM is offline."""
    text = str(goal or "").lower().strip()
    industries, personas, topics = [], [], []

    words = re.findall(r"[a-zA-Z0-9]+", text)
    meaningful_words = [w for w in words if w not in ENGLISH_STOP_WORDS and len(w) > 2]

    found_any = False
    for word in meaningful_words:
        matched_key = None
        for key in INDUSTRY_MAPPING:
            if key in word or word in key:
                matched_key = key
                break

        if matched_key:
            industries.extend(INDUSTRY_MAPPING[matched_key])
            topics.extend(INDUSTRY_MAPPING[matched_key])
            found_any = True
        else:
            industries.append(word)
            topics.append(word)
            found_any = True

    if not found_any and goal:
        industries.append(goal)
        topics.append(goal)

    return {
        "industries": list(dict.fromkeys(industries)),
        "personas": personas,
        "topics": list(dict.fromkeys(topics)),
    }


def analyze_goal(goal: str) -> Dict[str, List[str]]:
    """Analyzes a business goal via LLM with heuristic fallback."""
    clean_goal = str(goal or "").strip()
    if not clean_goal:
        return {"industries": [], "personas": [], "topics": []}

    prompt = f"""Analyze this business goal:
{clean_goal}

Return ONLY valid JSON with format:
{{
    "industries": ["industry1", "industry2"],
    "personas": ["persona1", "persona2"],
    "topics": ["topic1", "topic2", "synonyms"]
}}
Rules:
- industries = business industries and broad fields
- personas = target decision makers
- topics = searchable event topics and technology synonyms (e.g. for "tokenization" include "RWA", "smart contracts", "blockchain")"""

    try:
        response = generate(prompt, category="goal_analysis")
        text = extract_json(response.text)
        result = json.loads(text)

        return {
            "industries": result.get("industries", []),
            "personas": result.get("personas", []),
            "topics": result.get("topics", []),
        }
    except Exception as e:
        print(f"[Goal Analyzer] Fallback to rules: {e}")
        return build_fallback(clean_goal)