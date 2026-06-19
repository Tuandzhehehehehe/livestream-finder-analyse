"""Summarize a livestream/event using Gemini.

Falls back to a trimmed version of the description when Gemini is unavailable
(e.g. quota or no API key), so the pipeline never breaks.
"""

from ai.gemini import Gemini


def _fallback_summary(title: str, description: str) -> str:
    text = (description or title or "").strip()
    if len(text) > 200:
        text = text[:197].rstrip() + "..."
    return text


def summarize_event(title: str, description: str = "") -> str:
    """Return a concise 1-2 sentence summary of the event."""

    prompt = f"""
Summarize this livestream/event in 1-2 concise sentences for a sales lead list.
Focus on what it is about and who it is for.

Title:
{title}

Description:
{description}

Return only the summary text, no quotes.
"""

    try:
        gemini = Gemini()
        response = gemini.generate(prompt)
        text = (response.text or "").strip().strip('"').strip()
        if text:
            return text
    except Exception as e:
        print(f"Summarize error: {e}")

    return _fallback_summary(title, description)
