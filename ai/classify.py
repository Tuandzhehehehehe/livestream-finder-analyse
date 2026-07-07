
from ai.gemini import Gemini
import json

exhausted_models = set()


def fallback_classify(title: str, description: str, goal: str = ""):

    text = f"{title} {description}".lower()

    score = 40 if goal else 20
    industry = goal.title() if goal else "General"
    buyer_persona = "Unknown"

    if goal:
        import re
        goal_words = re.findall(r'[a-zA-Z0-9]+', goal.lower())
        stop_words = {"livestream", "livestreams", "tìm", "kiếm", "ở", "về", "cho", "và", "and", "with", "the", "a", "an", "in", "on", "to", "for"}
        meaningful = [w for w in goal_words if len(w) > 2 and w not in stop_words]
        for w in meaningful:
            if w in text:
                score += 15

    business_keywords = [
        "startup",
        "founder",
        "ceo",
        "cto",
        "saas",
        "crm",
        "business",
        "marketing",
        "sales",
        "fintech",
        "recruitment",
        "hr",
        "charity",
        "nonprofit",
        "fundraising",
        "investor",
        "entrepreneur",
        "webinar",
        "conference",
        "summit",
        "networking",
    ]

    matched = []

    for keyword in business_keywords:

        if keyword in text:
            matched.append(keyword)
            score += 8

    score = min(score, 100)

    if any(
        k in text
        for k in [
            "startup",
            "founder",
            "ceo",
            "entrepreneur",
        ]
    ):
        industry = "Startup"
        buyer_persona = "Founder, CEO"

    elif any(
        k in text
        for k in [
            "recruitment",
            "hr",
            "hiring",
        ]
    ):
        industry = "Recruitment"
        buyer_persona = "Recruiter, HR Manager"

    elif any(
        k in text
        for k in [
            "charity",
            "fundraising",
            "nonprofit",
        ]
    ):
        industry = "Charity"
        buyer_persona = "Organization Manager"

    elif any(
        k in text
        for k in [
            "marketing",
            "sales",
        ]
    ):
        industry = "Sales & Marketing"
        buyer_persona = "Business Decision Maker"

    language = "English"

    priority = "Low"
    interaction_tip = (
        "Ask a clarifying question to understand their goals."
    )

    if score >= 80:
        priority = "High"
        interaction_tip = (
            "This livestream looks very relevant; engage with a thoughtful question or offer."
        )
    elif score >= 50:
        priority = "Medium"
        interaction_tip = (
            "Consider joining and comment on a useful insight to connect."
        )

    if buyer_persona == "Founder, CEO":
        interaction_tip = (
            "Chủ động hỏi về chiến lược phát triển hoặc nhu cầu hợp tác."
        )
    elif buyer_persona == "Recruiter, HR Manager":
        interaction_tip = (
            "Hỏi về thách thức tuyển dụng và tìm kiếm tài năng phù hợp."
        )
    elif buyer_persona == "Organization Manager":
        interaction_tip = (
            "Đề cập đến cơ hội gây quỹ hoặc hợp tác cộng đồng."
        )

    return {
        "industry": industry,
        "language": language,
        "buyer_persona": buyer_persona,
        "score": score,
        "priority": priority,
        "interaction_tip": interaction_tip,
        "reason": (
            "Fallback scoring used because "
            "Gemini quota was unavailable."
        ),
        "suggested_comment": (
            "Interesting point, could you expand on that a little more?"
        ),
    }


def classify_event(
    title: str,
    description: str,
    goal: str = ""
):
    from ai.llm_client import generate, extract_json

    if description and len(description) > 500:
        description = description[:500] + "..."

    prompt = f"""
Analyze this livestream.

Title:
{title}

Description:
{description}

Return ONLY valid JSON:

{{
"industry":"",
"language":"",
"buyer_persona":"",
"score":0,
"reason":"",
"suggested_comment":""
}}
"""

    try:
        response = generate(prompt)  # Gemini → Groq → OpenAI fallback
        text = extract_json(response.text)
        result = json.loads(text)

        if "priority" not in result:
            score_val = result.get("score", 0)
            result["priority"] = "High" if score_val >= 80 else "Medium" if score_val >= 50 else "Low"
        if "interaction_tip" not in result:
            result["interaction_tip"] = "Join with a relevant question or comment."

        return result
    except Exception as e:
        print(f"[AI Classify] Error: {e}")
        return fallback_classify(title, description, goal)
