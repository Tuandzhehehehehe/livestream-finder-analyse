"""
ai/classify.py — AI Event Classifier & Rule-based Fallback
===========================================================
Analyzes event title and description via LLM or rule-based fallback.
"""

import json
import re


PERSONA_MAP = [
    (["startup", "founder", "ceo", "entrepreneur"], "Startup", "Founder, CEO", "Chủ động hỏi về chiến lược phát triển hoặc nhu cầu hợp tác."),
    (["recruitment", "hr", "hiring"], "Recruitment", "Recruiter, HR Manager", "Hỏi về thách thức tuyển dụng và tìm kiếm tài năng phù hợp."),
    (["charity", "fundraising", "nonprofit"], "Charity", "Organization Manager", "Đề cập đến cơ hội gây quỹ hoặc hợp tác cộng đồng."),
    (["marketing", "sales"], "Sales & Marketing", "Business Decision Maker", "Consider joining and comment on a useful insight to connect."),
]

BUSINESS_KEYWORDS = {
    "startup", "founder", "ceo", "cto", "saas", "crm", "business", "marketing",
    "sales", "fintech", "recruitment", "hr", "charity", "nonprofit", "fundraising",
    "investor", "entrepreneur", "webinar", "conference", "summit", "networking"
}


def fallback_classify(title: str, description: str, goal: str = "") -> dict:
    text = f"{title} {description}".lower()
    score = 40 if goal else 20
    industry = goal.title() if goal else "General"
    buyer_persona = "Unknown"
    interaction_tip = "Ask a clarifying question to understand their goals."

    if goal:
        stop_words = {"livestream", "livestreams", "tìm", "kiếm", "ở", "về", "cho", "và", "and", "with", "the", "a", "an", "in", "on", "to", "for"}
        goal_words = [w for w in re.findall(r'[a-zA-Z0-9]+', goal.lower()) if len(w) > 2 and w not in stop_words]
        for w in goal_words:
            if w in text:
                score += 15

    for keyword in BUSINESS_KEYWORDS:
        if keyword in text:
            score += 8

    score = min(score, 100)

    for keywords, ind, persona, tip in PERSONA_MAP:
        if any(k in text for k in keywords):
            industry = ind
            buyer_persona = persona
            interaction_tip = tip
            break

    priority = "High" if score >= 80 else ("Medium" if score >= 50 else "Low")

    return {
        "industry": industry,
        "language": "English",
        "buyer_persona": buyer_persona,
        "score": score,
        "priority": priority,
        "interaction_tip": interaction_tip,
        "reason": "Fallback scoring used because LLM was unavailable.",
        "suggested_comment": "Interesting point, could you expand on that a little more?",
    }


def classify_event(title: str, description: str, goal: str = "") -> dict:
    from ai.llm_client import generate, extract_json

    desc_snippet = description[:500] + "..." if description and len(description) > 500 else (description or "")

    prompt = f"""Analyze this livestream event for relevance to a target goal.
Goal: {goal if goal else "General business & networking"}
Title: {title}
Description: {desc_snippet}

Return ONLY valid JSON:
{{"industry":"", "language":"", "buyer_persona":"", "score":0, "reason":"", "suggested_comment":""}}
Note: "score" MUST be an integer from 0 to 100 representing relevance to the Goal (e.g. 85 for highly relevant, 20 for irrelevant)."""

    try:
        response = generate(prompt, category="classify")
        text = extract_json(response.text)
        result = json.loads(text)

        score_val = int(result.get("score", 0))
        # Nâng thang điểm 1-10 lên 10-100 nếu LLM trả về thang 1-10
        if 0 < score_val <= 10:
            score_val = score_val * 10
            result["score"] = score_val

        result["priority"] = "High" if score_val >= 80 else ("Medium" if score_val >= 50 else "Low")
        if "interaction_tip" not in result:
            result["interaction_tip"] = "Join with a relevant question or comment."

        return result
    except Exception as e:
        print(f"[AI Classify] Error: {e}")
        return fallback_classify(title, description, goal)
