"""
Zero-Shot / Cross-Encoder Classifier Scorer (Solution 2)
---------------------------------------------------------
Uses SentenceTransformers CrossEncoder 'cross-encoder/ms-marco-MiniLM-L-6-v2'
to compute pairwise relevance between target search Goal and Event Title.
Evaluates natural language relevance without hardcoded word rules.
"""

import os
from typing import List, Dict, Any, Optional

_CROSS_ENCODER = None
_CE_FAILED = False


def _load_cross_encoder():
    global _CROSS_ENCODER, _CE_FAILED
    if _CROSS_ENCODER is not None:
        return _CROSS_ENCODER
    if _CE_FAILED:
        return None
    try:
        from sentence_transformers import CrossEncoder
        print("[Cross-Encoder Scorer] Loading ms-marco-MiniLM-L-6-v2 model...")
        _CROSS_ENCODER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        print("[Cross-Encoder Scorer] Model loaded successfully!")
    except Exception as e:
        print(f"[Cross-Encoder Scorer] Notice: CrossEncoder load fallback: {e}")
        _CE_FAILED = True
    return _CROSS_ENCODER


def compute_cross_encoder_score(title: str, description: str = "", goal: str = "") -> float:
    """
    Tính điểm tương quan Cross-Encoder giữa Goal và (Title + Description).
    Trả về điểm từ 0.0 đến 100.0
    """
    if not goal or not title:
        return 0.0

    ce_model = _load_cross_encoder()
    if ce_model is None:
        return 0.0

    event_text = f"{title.strip()}. {description.strip()[:200]}".strip()
    pair = [goal.strip(), event_text]

    try:
        # CrossEncoder trả về logit score (thường từ -10 đến +10)
        logit = float(ce_model.predict(pair))
        
        # Sigmoid transform logit sang xắc suất 0 - 100%
        import math
        prob = 1.0 / (1.0 + math.exp(-logit))
        score = prob * 100.0
        return round(max(0.0, min(100.0, score)), 1)
    except Exception as e:
        print(f"[Cross-Encoder Scorer] Prediction error: {e}")
        return 0.0
