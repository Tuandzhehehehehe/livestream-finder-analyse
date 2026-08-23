"""
services/topic_expander.py — Search Topic & Query Expansion
=============================================================
Expands business keywords into multi-platform search queries using LLM or rule-based fallback.
"""

import json
from typing import List
from ai.llm_client import generate, extract_json

EXPANSION_SUFFIXES = [" live", " livestream", " webinar", " workshop", " online event"]


def expand_topic(keyword: str) -> List[str]:
    """Expands a single keyword into up to 5 targeted search queries."""
    clean_keyword = str(keyword or "").strip()
    if not clean_keyword:
        return []

    prompt = f"""You are helping find business-related livestreams.
Keyword: {clean_keyword}
Generate 5 search queries related to business livestreams.
Return ONLY valid JSON array of strings, e.g. ["startup fundraising", "startup founder live", "business growth webinar"]"""

    try:
        response = generate(prompt, category="topic_expansion")
        text = extract_json(response.text)
        queries = json.loads(text)

        if isinstance(queries, list):
            result = [str(q).strip() for q in queries if str(q).strip()]
            if clean_keyword not in result:
                result.insert(0, clean_keyword)

            for suffix in EXPANSION_SUFFIXES:
                candidate = f"{clean_keyword}{suffix}".strip()
                if candidate not in result:
                    result.append(candidate)
                if len(result) >= 5:
                    break

            return result[:5]
    except Exception as e:
        print(f"[Topic Expander] Error: {e}")

    # Fallback heuristic expansion
    fallback = [clean_keyword]
    for suffix in EXPANSION_SUFFIXES:
        candidate = f"{clean_keyword}{suffix}".strip()
        if candidate not in fallback:
            fallback.append(candidate)
        if len(fallback) >= 5:
            break

    return fallback[:5]