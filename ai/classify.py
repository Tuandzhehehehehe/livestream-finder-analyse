"""
ai/classify.py — AI Event Classifier & NLP Fallback Engine
===========================================================
Phân loại sự kiện livestream bằng mô hình LLM (Gemini / Groq / OpenAI)
hoặc suy luận tự động qua mô hình Semantic Embedding (MiniLM) khi offline.
Không sử dụng bất kỳ từ điển tĩnh hay danh sách hardcode nào.
"""

import json
from typing import Dict, Any
from ai.llm_client import generate, extract_json


def fallback_classify(title: str, description: str = "", goal: str = "") -> Dict[str, Any]:
    """
    Phân loại dự phòng hoàn toàn tự động bằng NLP & Semantic Embeddings
    khi không kết nối được LLM API (không dùng từ khóa tĩnh).
    """
    clean_title = str(title or "").strip()
    clean_desc = str(description or "").strip()
    clean_goal = str(goal or "General Business & Networking").strip()

    # 1. Dự đoán mức độ liên quan bằng mô hình MiniLM Semantic Embedding
    from ai.minilm_scorer import compute_minilm_score
    from ai.spam_classifier import predict_spam

    is_spam, _ = predict_spam(clean_title, clean_desc)
    if is_spam:
        score = 0
    else:
        score = int(compute_minilm_score(clean_title, clean_desc, [clean_goal]))

    priority = "High" if score >= 80 else ("Medium" if score >= 50 else "Low")

    # 2. Xác định Persona và Industry động từ Goal của người dùng
    industry = clean_goal.title() if clean_goal else "General"
    buyer_persona = f"{clean_goal} Decision Maker" if clean_goal else "Professional"
    interaction_tip = f"Engage with a specific question regarding {clean_goal}."

    return {
        "industry": industry,
        "language": "Auto-detected",
        "buyer_persona": buyer_persona,
        "score": score,
        "priority": priority,
        "interaction_tip": interaction_tip,
        "reason": f"Semantic similarity score: {score}/100 with target goal '{clean_goal}'.",
        "suggested_comment": f"Great insights on this topic. Could you share more practical use-cases regarding {clean_goal}?",
    }


def classify_event(title: str, description: str = "", goal: str = "") -> Dict[str, Any]:
    """
    Phân loại sự kiện livestream bằng mô hình LLM (Gemini / Groq LLaMA / OpenAI).
    Tự động fallback sang MiniLM Embedding khi mất kết nối.
    """
    clean_title = str(title or "").strip()
    clean_desc = str(description or "").strip()
    clean_goal = str(goal or "General business & networking").strip()
    desc_snippet = clean_desc[:500] + "..." if len(clean_desc) > 500 else clean_desc

    prompt = f"""Analyze this livestream event for relevance to a target goal.
Goal: {clean_goal}
Title: {clean_title}
Description: {desc_snippet}

Return ONLY valid JSON in format:
{{
  "industry": "Specific industry of event",
  "language": "Language spoken (e.g. English, Vietnamese)",
  "buyer_persona": "Target audience persona (e.g. Founder, HR Manager, Engineer)",
  "score": 85,
  "interaction_tip": "Actionable tip for how to interact in chat",
  "reason": "Brief reason for the score",
  "suggested_comment": "A natural, non-generic comment to post in live chat"
}}
Note: "score" MUST be an integer from 0 to 100 representing relevance to the Goal."""

    try:
        response = generate(prompt, category="classify")
        text = extract_json(response.text)
        result = json.loads(text)

        score_val = int(result.get("score", 0))
        # Nâng thang điểm 1-10 lên 10-100 nếu LLM trả về thang điểm 10
        if 0 < score_val <= 10:
            score_val = score_val * 10
            result["score"] = score_val

        result["priority"] = "High" if score_val >= 80 else ("Medium" if score_val >= 50 else "Low")
        if not result.get("interaction_tip"):
            result["interaction_tip"] = f"Join chat with a relevant question about {clean_goal}."

        return result
    except Exception as e:
        print(f"[AI Classify] LLM API notice: {e} -> Running NLP Semantic Fallback...")
        return fallback_classify(clean_title, clean_desc, clean_goal)
