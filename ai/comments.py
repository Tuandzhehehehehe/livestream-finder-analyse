"""Generate an engagement comment for a livestream/event using Gemini.

Falls back to a generic comment when Gemini is unavailable (e.g. quota or no
API key), so the pipeline never breaks.
"""

from ai.gemini import Gemini

FALLBACK_COMMENT = (
    "Interesting topic! Could you share more about what inspired this?"
)


def generate_comment(title: str, description: str = "", buyer_persona: str = ""):
    """Return a short, friendly comment to start a conversation at the event."""

    prompt = f"""
You are a friendly business professional joining a livestream/event to network.

Title:
{title}

Description:
{description}

Target audience:
{buyer_persona or "Unknown"}

Write ONE short, natural comment (max 2 sentences) to post in the chat that
sparks a genuine conversation. Do not use hashtags or emojis. Return only the
comment text, no quotes.
"""

    try:
        gemini = Gemini()
        response = gemini.generate(prompt)
        text = (response.text or "").strip().strip('"').strip()
        if text:
            return text
    except Exception as e:
        print(f"Comment generation error: {e}")

    return FALLBACK_COMMENT
