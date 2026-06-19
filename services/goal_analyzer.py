from google import genai
import os
import json

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


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

    found = False

    for keyword, values in mapping.items():

        if keyword in text:

            industries.extend(values)
            topics.extend(values)

            found = True

    if not found:

        industries.append(goal)
        topics.append(goal)

    return {
        "industries": list(set(industries)),
        "personas": personas,
        "topics": list(set(topics)),
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

- industries = business industries
- personas = target decision makers
- topics = searchable event topics

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

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        text = (
            response.text
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

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