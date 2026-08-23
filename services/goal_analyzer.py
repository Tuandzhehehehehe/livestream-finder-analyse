import re


_MAPPING = {
    "charity":     ["charity", "nonprofit", "fundraising", "ngo", "social impact"],
    "startup":     ["startup", "founder", "entrepreneur", "venture capital", "saas"],
    "fintech":     ["fintech", "finance", "banking", "payments", "digital banking"],
    "ai":          ["artificial intelligence", "machine learning", "generative ai", "llm", "automation"],
    "marketing":   ["digital marketing", "seo", "content marketing", "growth marketing", "social media"],
    "ecommerce":   ["ecommerce", "shopify", "amazon seller", "online store", "dropshipping"],
    "recruitment": ["recruitment", "hr", "talent acquisition", "hiring", "human resources"],
    "saas":        ["saas", "software startup", "b2b software", "software founder"],
}

_STOP_WORDS = {
    "livestream", "livestreams", "lĩnh", "vực", "tìm", "kiếm", "khách", "hàng",
    "ở", "về", "cho", "và", "and", "with", "the", "a", "an", "or",
    "in", "on", "at", "to", "by", "of", "for", "is", "are",
}


def build_fallback(goal: str) -> dict:
    """Xây dựng analysis dict không cần AI — dùng làm fallback."""
    industries: list[str] = []
    topics: list[str] = []

    words = [w for w in re.findall(r"[a-zA-Z0-9]+", goal.lower()) if w not in _STOP_WORDS and len(w) > 2]

    for word in words:
        matched = next((v for k, v in _MAPPING.items() if k in word or word in k), None)
        if matched:
            industries.extend(matched)
            topics.extend(matched)
        else:
            industries.append(word)
            topics.append(word)

    if not industries:
        industries.append(goal)
        topics.append(goal)

    return {
        "industries": list(dict.fromkeys(industries)),
        "personas":   [],
        "topics":     list(dict.fromkeys(topics)),
    }