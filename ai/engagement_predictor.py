"""
ai/engagement_predictor.py — Title Engagement Predictor Inference Engine
========================================================================
Dự đoán mức độ hút tương tác & tỷ lệ Like của Tiêu đề (0.0 đến 100.0)
sử dụng mô hình Gradient Boosting đã được huấn luyện trên 4,569 Video YouTube.
"""

import os
import pickle
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any

_ENGAGEMENT_MODEL_ARTIFACT = None
_MODEL_LOAD_FAILED = False


def _load_model() -> Optional[Dict[str, Any]]:
    global _ENGAGEMENT_MODEL_ARTIFACT, _MODEL_LOAD_FAILED
    if _ENGAGEMENT_MODEL_ARTIFACT is not None:
        return _ENGAGEMENT_MODEL_ARTIFACT
    if _MODEL_LOAD_FAILED:
        return None

    model_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "data", "models", "engagement_model.pkl")
    )
    if not os.path.exists(model_path):
        # Auto-train if not exists
        try:
            from ai.train_engagement_model import train_and_save_model
            _ENGAGEMENT_MODEL_ARTIFACT = train_and_save_model()
            return _ENGAGEMENT_MODEL_ARTIFACT
        except Exception as e:
            print(f"[Engagement Predictor] Auto-train error: {e}")
            _MODEL_LOAD_FAILED = True
            return None

    try:
        with open(model_path, "rb") as f:
            _ENGAGEMENT_MODEL_ARTIFACT = pickle.load(f)
        return _ENGAGEMENT_MODEL_ARTIFACT
    except Exception as e:
        print(f"[Engagement Predictor] Load model error: {e}")
        _MODEL_LOAD_FAILED = True
        return None


def predict_title_engagement(title: str) -> float:
    """
    Dự đoán điểm tiềm năng tương tác (Engagement Score) của Tiêu đề.
    Trả về điểm từ 0.0 đến 100.0 (Thang chuẩn hóa).
    """
    t = str(title or "").strip()
    if not t:
        return 0.0

    artifact = _load_model()
    if artifact is None:
        # Heuristic fallback if model not loaded
        length = len(t)
        base = 50.0
        if 30 <= length <= 70: base += 20.0
        if any(c in t for c in ["!", "?", "|", ":", "—"]): base += 10.0
        return float(min(100.0, max(0.0, base)))

    model = artifact["model"]
    tfidf = artifact["tfidf"]
    feature_names = artifact["feature_names"]

    # 1. Trích xuất đặc trưng số
    feats = {}
    feats["char_length"] = len(t)
    feats["word_count"] = len(t.split())
    feats["caps_ratio"] = sum(1 for c in t if c.isupper()) / max(1, len(t))
    feats["digit_count"] = sum(1 for c in t if c.isdigit())
    feats["has_exclamation"] = 1.0 if "!" in t else 0.0
    feats["has_question"] = 1.0 if "?" in t else 0.0
    feats["has_hashtag"] = 1.0 if "#" in t else 0.0
    feats["has_colon_or_pipe"] = 1.0 if any(c in t for c in ["|", ":", "—", "-", "[", "]"]) else 0.0

    power_keywords = ["how to", "live", "tutorial", "full course", "masterclass", "24/7", "review", "vs", "challenge", "secret"]
    for kw in power_keywords:
        feats[f"kw_{kw.replace(' ', '_')}"] = 1.0 if kw in t.lower() else 0.0

    num_vec = np.array([[feats.get(k, 0.0) for k in feature_names]])

    # 2. Trích xuất TF-IDF
    tfidf_vec = tfidf.transform([t]).toarray()

    # 3. Ghép vector & Dự đoán
    X = np.hstack([num_vec, tfidf_vec])
    pred = float(model.predict(X)[0])

    return round(float(np.clip(pred, 0.0, 100.0)), 1)
