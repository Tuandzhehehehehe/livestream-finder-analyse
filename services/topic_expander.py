from ai.llm_client import generate, extract_json
import json


def expand_topic(keyword: str):

    prompt = f"""
You are helping find business-related livestreams.

Keyword:
{keyword}

Generate 5 search queries related to business livestreams.

Return ONLY JSON.

Example:

[
    "startup fundraising",
    "startup founder live",
    "business growth webinar"
]
"""

    try:

        response = generate(prompt)
        text = extract_json(response.text)

        queries = json.loads(
            text
        )

        if isinstance(
            queries,
            list
        ):
            result = [
                str(q).strip()
                for q in queries
                if str(q).strip()
            ]
            if keyword not in result:
                result.insert(0, keyword)

            suffixes = [
                " live",
                " livestream",
                " webinar",
                " workshop",
                " online event",
            ]
            for suffix in suffixes:
                candidate = f"{keyword}{suffix}".strip()
                if candidate not in result:
                    result.append(candidate)
                if len(result) >= 5:
                    break

            return result[:5]

    except Exception as e:

        print(
            f"Expand error: {e}"
        )

    fallback = [keyword]
    suffixes = [
        " live",
        " livestream",
        " webinar",
        " workshop",
        " online event",
    ]
    for suffix in suffixes:
        candidate = f"{keyword}{suffix}".strip()
        if candidate not in fallback:
            fallback.append(candidate)
        if len(fallback) >= 5:
            break

    return fallback