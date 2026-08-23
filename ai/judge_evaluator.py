"""
ai/judge_evaluator.py — Independent Third-Party LLM-as-a-Judge
===============================================================
Đóng vai trò 'Ban giám khảo độc lập' (Third-Party Judge) sử dụng phương pháp G-Eval / Ragas
để chấm điểm mù (Double-Blind Evaluation) cho kết quả của Agent.
Không sử dụng bộ nhớ hay dữ liệu nội bộ của Agent để đảm bảo 100% khách quan.
"""

import os
import json
import re
from typing import Dict, Any, Optional
from ai.llm_client import _try_gemini, _try_groq, _try_openai, LLMResponse


JUDGE_RUBRIC_PROMPT = """You are an impartial, strict third-party AI Judge evaluating an AI Discovery Agent's search output.
Your goal is to evaluate if the discovered livestream/webinar is high quality and relevant to the user's business search goal.

Evaluation Rubric (Total: 0 to 100 points):
1. Goal Relevance & Topical Alignment (0 to 40 pts):
   - Is this livestream specifically about the target search goal topic? (Not just matching random generic words).
2. Business Value & Buyer Persona Match (0 to 30 pts):
   - Does this event target professional founders, B2B executives, engineers, or decision-makers?
3. Actionability & Engagement Potential (0 to 30 pts):
   - Does this offer meaningful Q&A, networking, or business partnership opportunity?
4. Spam & Noise Penalty (-50 to 0 pts):
   - If this is a video game scam (Roblox, Free Robux, Fortnite, Vbucks, Hack, Crypto Pump, Clickbait Giveaway), award 0 points total!

Target Search Goal: "{goal}"

Discovered Event to Evaluate:
- Title: "{title}"
- Channel: "{channel_name}"
- Description: "{description}"
- Status: "{status}"
- Viewers: "{viewers}"

Output ONLY a JSON object with this exact structure:
```json
{{
  "judge_score": <number 0 to 100>,
  "goal_relevance_pts": <number 0 to 40>,
  "persona_match_pts": <number 0 to 30>,
  "actionability_pts": <number 0 to 30>,
  "is_spam": <true or false>,
  "is_relevant": <true or false>,
  "critique": "<brief 1-sentence explanation of the score>"
}}
```
"""


def evaluate_with_llm_judge(
    title: str,
    description: str = "",
    channel_name: str = "",
    goal: str = "",
    status: str = "LIVE",
    viewers: str = "",
) -> Dict[str, Any]:
    """
    Gọi LLM bên thứ 3 (Gemini / Groq / OpenAI) để chấm điểm mù kết quả.
    """
    clean_title = str(title or "").strip()
    clean_desc = str(description or "").strip()[:400]
    clean_goal = str(goal or "Business Webinar").strip()

    if not clean_title:
        return {
            "judge_score": 0.0,
            "goal_relevance_pts": 0,
            "persona_match_pts": 0,
            "actionability_pts": 0,
            "is_spam": True,
            "is_relevant": False,
            "critique": "Missing title or empty event.",
        }

    # ML-based spam detection penalty
    from ai.spam_classifier import predict_spam
    is_sp, prob = predict_spam(clean_title, clean_desc)
    if is_sp and prob >= 0.75:
        return {
            "judge_score": 0.0,
            "goal_relevance_pts": 0,
            "persona_match_pts": 0,
            "actionability_pts": 0,
            "is_spam": True,
            "is_relevant": False,
            "critique": f"ML Spam Classifier detected spam/scam (probability: {prob * 100:.0f}%).",
        }

    prompt = JUDGE_RUBRIC_PROMPT.format(
        goal=clean_goal,
        title=clean_title,
        channel_name=channel_name or "Unknown Channel",
        description=clean_desc,
        status=status or "LIVE",
        viewers=viewers or "N/A",
    )

    # Thử lần lượt các Judge LLM độc lập
    resp: Optional[LLMResponse] = None
    for provider_fn in [_try_groq, _try_gemini, _try_openai]:
        try:
            resp = provider_fn(prompt, category="third_party_judge")
            if resp and resp.text:
                break
        except Exception:
            pass

    if not resp or not resp.text:
        # Fallback heuristic judge if all LLM keys unavailable
        words = set(re.findall(r'\w+', clean_goal.lower()))
        title_words = set(re.findall(r'\w+', clean_title.lower()))
        overlap = len(words.intersection(title_words))
        score = min(100.0, float(overlap * 35.0))
        return {
            "judge_score": score,
            "goal_relevance_pts": min(40, overlap * 20),
            "persona_match_pts": min(30, overlap * 15),
            "actionability_pts": 15,
            "is_spam": False,
            "is_relevant": score >= 50.0,
            "critique": f"Heuristic overlap score: {score:.1f}/100",
        }

    try:
        raw_text = resp.text.strip()
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if json_match:
            raw_text = json_match.group(1)
        data = json.loads(raw_text)
        judge_score = float(data.get("judge_score", 0.0))
        return {
            "judge_score": max(0.0, min(100.0, judge_score)),
            "goal_relevance_pts": data.get("goal_relevance_pts", 0),
            "persona_match_pts": data.get("persona_match_pts", 0),
            "actionability_pts": data.get("actionability_pts", 0),
            "is_spam": bool(data.get("is_spam", False)),
            "is_relevant": bool(data.get("is_relevant", judge_score >= 50.0)),
            "critique": str(data.get("critique", "LLM Judge evaluation completed.")),
            "judge_model": f"{resp.provider}/{resp.model}",
        }
    except Exception as parse_err:
        print(f"[Third-Party Judge] JSON parse warning: {parse_err}")
        return {
            "judge_score": 50.0,
            "is_spam": False,
            "is_relevant": True,
            "critique": f"Raw Judge Output: {resp.text[:100]}",
            "judge_model": f"{resp.provider}/{resp.model}",
        }
