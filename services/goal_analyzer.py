import os
import json


def build_fallback(goal: str):
    text = goal.lower()

    industries = []
    personas = []
    topics = []

    mapping = {
        "charity": [
            "charity",
            "nonprofit",
            "fundraising",
            "ngo",
            "social impact",
        ],
        "startup": [
            "startup",
            "founder",
            "entrepreneur",
            "venture capital",
            "saas",
        ],
        "fintech": [
            "fintech",
            "finance",
            "banking",
            "payments",
            "digital banking",
        ],
        "ai": [
            "artificial intelligence",
            "machine learning",
            "generative ai",
            "llm",
            "automation",
        ],
        "marketing": [
            "digital marketing",
            "seo",
            "content marketing",
            "growth marketing",
            "social media",
        ],
        "ecommerce": [
            "ecommerce",
            "shopify",
            "amazon seller",
            "online store",
            "dropshipping",
        ],
        "recruitment": [
            "recruitment",
            "hr",
            "talent acquisition",
            "hiring",
            "human resources",
        ],
        "saas": [
            "saas",
            "software startup",
            "b2b software",
            "software founder",
        ],
    }

    # Extract potential English/industry words from the goal
    import re
    words = re.findall(r'[a-zA-Z0-9]+', text)
    
    # Vietnamese/English stop words or generic search words to ignore
    stop_words = {
        "livestream", "livestreams", "lĩnh", "vực", "tìm", "kiếm", "khách", "hàng", "ở", "về", "cho", 
        "và", "and", "with", "the", "a", "an", "or", "in", "on", "at", "to", "by", "of", "for", "is", "are"
    }
    
    meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]
    
    found_any = False
    for word in meaningful_words:
        matched_key = None
        for key in mapping:
            if key in word or word in key:
                matched_key = key
                break
        
        if matched_key:
            industries.extend(mapping[matched_key])
            topics.extend(mapping[matched_key])
            found_any = True
        else:
            # Preserve terms that aren't mapped (e.g. "tokenization")
            industries.append(word)
            topics.append(word)
            found_any = True

    if not found_any:
        industries.append(goal)
        topics.append(goal)

    return {
        "industries": list(dict.fromkeys(industries)),
        "personas": personas,
        "topics": list(dict.fromkeys(topics)),
    }


def analyze_goal(goal):

    try:

        prompt = f"""
Analyze this business goal:

{goal}

Return ONLY valid JSON.

Format:

{{
    "industries": [],
    "personas": [],
    "topics": []
}}

Rules:

- industries = business industries and broad fields
- personas = target decision makers
- topics = searchable event topics. **CRITICAL: You MUST include synonyms, related technologies, and alternative terms!** For example, if the goal is "tokenization", include "RWA", "smart contracts", "blockchain", "digital assets", "web3", etc. This is needed because some events use these related words instead of the exact keyword.

Example:

Input:
Find charity livestreams

Output:

{{
    "industries": [
        "charity",
        "nonprofit",
        "fundraising"
    ],
    "personas": [
        "ngo director",
        "fundraising manager"
    ],
    "topics": [
        "charity",
        "fundraising",
        "social impact"
    ]
}}
"""

        from ai.llm_client import generate, extract_json
        response = generate(prompt)
        text = extract_json(response.text)

        result = json.loads(text)

        return {
            "industries": result.get(
                "industries",
                []
            ),
            "personas": result.get(
                "personas",
                []
            ),
            "topics": result.get(
                "topics",
                []
            ),
        }

    except Exception as e:

        print(
            f"Goal Analyzer Fallback: {e}"
        )

        return build_fallback(goal)