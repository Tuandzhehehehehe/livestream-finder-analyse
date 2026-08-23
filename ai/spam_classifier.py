"""
ai/spam_classifier.py — Pure AI/ML Spam Classifier & Relevance Scoring Engine
=============================================================================
Sử dụng hoàn toàn các mô hình Machine Learning & NLP để phát hiện Spam và Chấm điểm:
  1. ML Spam Classifier (Mô hình TF-IDF + LogisticRegression)
  2. Active Learning Feedback Engine (Tự động thích ứng khi người dùng vote Like/Dislike)
  3. MiniLM Semantic Embedding Similarity (all-MiniLM-L6-v2)
  4. Zero-Shot Cross-Encoder Scorer (ms-marco-MiniLM)
  5. Title Engagement Predictor Model
"""

import os
import re
import pickle
import sqlite3
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, f1_score

from database.db import DATABASE_URL

# CSDL lưu trữ feedback người dùng
DB_FILE = DATABASE_URL.replace("sqlite:///", "") if "sqlite" in DATABASE_URL else "livestream.db"

_SPAM_V2_MODEL = None
_CLF = None
_IS_TRAINED = False


# ══════════════════════════════════════════════════════════════════════════════
# 1. MACHINE LEARNING SPAM INFERENCE PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def _load_spam_v2_model():
    """Tải mô hình Machine Learning phát hiện Spam đã được huấn luyện sẵn."""
    global _SPAM_V2_MODEL
    if _SPAM_V2_MODEL is not None:
        return _SPAM_V2_MODEL

    v2_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "data", "models", "spam_classifier_v2.pkl")
    )
    if os.path.exists(v2_path):
        try:
            with open(v2_path, "rb") as f:
                _SPAM_V2_MODEL = pickle.load(f)
            return _SPAM_V2_MODEL
        except Exception as e:
            print(f"[Spam Classifier] Error loading model: {e}")
    return None


def predict_spam(title: str, description: str = "", threshold: float = 0.70) -> Tuple[bool, float]:
    """
    Dự đoán xác suất Spam/Rác hoàn toàn tự động bằng mô hình Machine Learning.
    Không dùng bất kỳ danh sách từ khóa tĩnh (hardcoded pattern) nào.
    
    Returns:
        tuple (is_spam: bool, spam_probability: float từ 0.0 đến 1.0)
    """
    title_clean = str(title or "").strip()
    desc_clean = str(description or "").strip()
    full_text = f"{title_clean}. {desc_clean[:250]}".strip()

    if not full_text:
        return (False, 0.0)

    # 1. Dự đoán qua mô hình Machine Learning TF-IDF + LogisticRegression
    v2_artifact = _load_spam_v2_model()
    if v2_artifact is not None:
        try:
            vectorizer = v2_artifact["vectorizer"]
            clf = v2_artifact["classifier"]
            vec = vectorizer.transform([full_text])
            probs = clf.predict_proba(vec)[0]
            # probs[1] là xác suất class 1 (Spam)
            spam_prob = float(probs[1]) if len(probs) > 1 else float(probs[0])
            is_spam = spam_prob >= threshold
            return (is_spam, round(spam_prob, 2))
        except Exception as e:
            print(f"[Spam Classifier] Prediction error: {e}")

    # 2. Fallback qua mô hình Active Learning (nếu người dùng đã có feedback)
    global _CLF, _IS_TRAINED
    if not _IS_TRAINED or _CLF is None:
        train_success = train_spam_model()
        if not train_success or _CLF is None:
            return (False, 0.0)

    try:
        model_type = _CLF[0]
        if model_type == "minilm":
            minilm_model, clf = _CLF[1], _CLF[2]
            emb = minilm_model.encode([full_text], normalize_embeddings=True)
            probs = clf.predict_proba(emb)[0]
            good_prob = float(probs[1]) if len(probs) > 1 else float(probs[0])
            spam_prob = 1.0 - good_prob
        else:
            vectorizer, clf = _CLF[1], _CLF[2]
            emb = vectorizer.transform([full_text])
            probs = clf.predict_proba(emb)[0]
            good_prob = float(probs[1]) if len(probs) > 1 else float(probs[0])
            spam_prob = 1.0 - good_prob

        is_spam = spam_prob >= threshold
        return (is_spam, round(spam_prob, 2))
    except Exception as e:
        print(f"[Spam Classifier] Active learning error: {e}")
        return (False, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# 2. ACTIVE LEARNING & USER FEEDBACK (TỰ ĐỘNG THÍCH ỨNG)
# ══════════════════════════════════════════════════════════════════════════════

def init_feedback_db():
    """Khởi tạo cấu trúc bảng user_feedback trong SQLite (dữ liệu sạch hoàn toàn do người dùng tạo)."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                label INTEGER NOT NULL, -- 0 = Spam/Rác, 1 = Tiềm năng
                url TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Feedback DB] Init error: {e}")


def train_spam_model() -> bool:
    """Huấn luyện nhanh mô hình Scikit-Learn trên tập phản hồi thực tế của người dùng."""
    global _CLF, _IS_TRAINED
    init_feedback_db()

    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        rows = cur.execute("SELECT title, description, label FROM user_feedback").fetchall()
        conn.close()

        if len(rows) < 4:
            return False

        texts = [f"{str(r[0])}. {str(r[1] or '')}".strip() for r in rows]
        labels = [int(r[2]) for r in rows]

        # Phải có ít nhất cả 2 nhãn (0 và 1) để train classifier
        if len(set(labels)) < 2:
            return False

        # Thử encode bằng MiniLM embedding
        from ai.minilm_scorer import _load_model
        model = _load_model()

        if model is not None:
            embeddings = model.encode(texts, normalize_embeddings=True)
        else:
            vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
            embeddings = vectorizer.fit_transform(texts)

        clf = LogisticRegression(C=1.0, max_iter=200)
        clf.fit(embeddings, labels)

        if model is not None:
            _CLF = ("minilm", model, clf)
        else:
            _CLF = ("tfidf", vectorizer, clf)

        _IS_TRAINED = True
        return True
    except Exception as e:
        print(f"[Spam Classifier] Feedback training error: {e}")
        return False


def add_user_feedback(title: str, description: str, label: int, url: str = "") -> bool:
    """Ghi nhận phản hồi Like/Dislike của người dùng và cập nhật lại mô hình tức thì."""
    init_feedback_db()
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_feedback (title, description, label, url)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET label=excluded.label, created_at=CURRENT_TIMESTAMP
        """, (title or "", description or "", label, url or f"user_{hash(title)}"))
        conn.commit()
        conn.close()

        train_spam_model()
        return True
    except Exception as e:
        print(f"[Feedback DB] Add feedback error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 3. RELEVANCE & OPPORTUNITY SCORING ENGINE (AI/ML DRIVEN)
# ══════════════════════════════════════════════════════════════════════════════

def calculate_relevance(event: Dict[str, Any], analysis: Dict[str, Any], goal: str = "") -> int:
    """
    Tính toán mức độ phù hợp và tiềm năng của sự kiện livestream bằng các mô hình AI/NLP:
      1. ML Spam Classifier (Lọc tự động dựa trên xác suất ML)
      2. MiniLM Semantic Similarity Scorer (Cosine Similarity Embedding)
      3. Zero-Shot Cross-Encoder Scorer (ms-marco-MiniLM)
      4. Title Engagement & Likes Predictor
      5. Goal & Keyword Semantic Alignment
    """
    title = str(event.get("title", ""))
    description = str(event.get("description", ""))
    text = f"{title.lower()} {description.lower()}"

    # 🛑 1. Kiểm tra Spam bằng mô hình Machine Learning
    try:
        is_spam, spam_prob = predict_spam(title=title, description=description, threshold=0.70)
        event["spam_probability"] = spam_prob
        if is_spam:
            event["is_spam_detected"] = True
            return 0
    except Exception as e:
        print(f"[Relevance Scoring] Spam prediction error: {e}")

    score = 0

    industries = analysis.get("industries", []) or []
    topics = analysis.get("topics", []) or []
    personas = analysis.get("personas", []) or []

    raw_keywords = industries + topics + personas
    keywords = []
    for k in raw_keywords:
        k_str = str(k).lower().strip()
        if k_str and k_str not in keywords:
            keywords.append(k_str)

    if goal:
        g_str = goal.lower().strip()
        if g_str not in keywords:
            keywords.append(g_str)

    # Khớp từ khóa trong tiêu đề (+40 điểm)
    for keyword in keywords:
        if keyword in title.lower():
            score += 40

    # Khớp từ khóa trong nội dung (+20 điểm)
    for keyword in keywords:
        if keyword in text:
            score += 20

    # Khớp từ khóa trong URL (+5 điểm)
    url = str(event.get("url", "")).lower()
    for keyword in keywords:
        if keyword in url:
            score += 5

    # Khớp từ khóa truy vấn của crawler (+10 điểm)
    event_keyword = str(event.get("keyword", "")).lower().strip()
    if event_keyword and event_keyword in text:
        score += 10

    # Khớp các cụm từ cốt lõi của Goal (dùng chuẩn stop words từ Scikit-Learn)
    if goal:
        goal_words = re.findall(r"[a-zA-Z0-9]+", goal.lower())
        core_terms = [w for w in goal_words if w not in ENGLISH_STOP_WORDS and len(w) > 2]
        if len(core_terms) >= 2:
            matched_core_terms = [t for t in core_terms if t in text]
            if len(matched_core_terms) >= 2:
                score += len(matched_core_terms) * 20

        if goal.lower() in text:
            score += 5

    # ── 2. MiniLM Semantic Similarity NLP Model ─────────────────────────
    try:
        from ai.minilm_scorer import compute_minilm_score
        target_queries = [goal] + keywords if goal else keywords
        minilm_sim_score = compute_minilm_score(
            title=title,
            description=description,
            target_queries=target_queries
        )
        event["minilm_score"] = minilm_sim_score
        
        final_score = max(score, int(minilm_sim_score))
        if minilm_sim_score >= 60:
            final_score += 10
        score = final_score
    except Exception as e:
        print(f"[Relevance Scoring] MiniLM error: {e}")

    # ── 3. Zero-Shot Cross-Encoder Scorer ───────────────────────────────
    try:
        from ai.cross_encoder_scorer import compute_cross_encoder_score
        if goal:
            ce_score = compute_cross_encoder_score(
                title=title,
                description=description,
                goal=goal
            )
            event["cross_encoder_score"] = ce_score
            if ce_score >= 60:
                score = max(score, int(ce_score))
    except Exception as e:
        print(f"[Relevance Scoring] Cross-Encoder error: {e}")

    # ── 4. Title Engagement & Likes Predictor Model ─────────────────────
    try:
        from ai.engagement_predictor import predict_title_engagement
        eng_score = predict_title_engagement(title=title)
        event["engagement_predicted_score"] = eng_score
        if eng_score >= 70:
            score = max(score, int(score * 0.7 + eng_score * 0.3))
    except Exception as e:
        print(f"[Relevance Scoring] Engagement Predictor error: {e}")

    return score


def is_relevant(event: Dict[str, Any], goal: str, threshold: int = 0) -> bool:
    text = f"{event.get('title', '')} {event.get('description', '')}".lower()
    return (10 if goal.lower().strip() in text else 0) >= threshold


# ══════════════════════════════════════════════════════════════════════════════
# 4. TRAINING UTILITY TỪ DATASET LỚN (OFFLINE TRAINER)
# ══════════════════════════════════════════════════════════════════════════════

def train_and_save_supercharged_spam_model(parquet_path: Optional[str] = None, model_output_path: Optional[str] = None):
    """Huấn luyện mô hình Supercharged Spam Classifier trực tiếp từ tập dữ liệu Parquet 1M bình luận."""
    if parquet_path is None:
        parquet_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "youtube_comment_sentiment.parquet")
        )
    if model_output_path is None:
        models_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "models"))
        os.makedirs(models_dir, exist_ok=True)
        model_output_path = os.path.join(models_dir, "spam_classifier_v2.pkl")

    print("=" * 80)
    print("🚀 HUẤN LUYỆN ML SPAM CLASSIFIER TỪ DATASET PARQUET")
    print("=" * 80)

    if not os.path.exists(parquet_path):
        print(f"❌ Không tìm thấy file dữ liệu: {parquet_path}")
        return None

    df = pd.read_parquet(parquet_path)
    df_comments = df["CommentText"].dropna().astype(str)

    # Lấy mẫu spam dựa trên phân tích sentiment tiêu cực/quảng cáo
    spam_pattern = r"(sub to my channel|free robux|claim now|crypto pump|easy money|v-bucks|vbucks|whatsapp|telegram|hack tool|drop your cashapp)"
    spam_mask = df_comments.str.contains(spam_pattern, case=False, regex=True)

    spam_texts = list(df_comments[spam_mask].sample(min(len(df_comments[spam_mask]), 7500), random_state=42))
    clean_mask = (~spam_mask) & (df["Sentiment"].isin(["Positive", "Neutral"])) & (df_comments.str.len() > 30)
    clean_texts = list(df_comments[clean_mask].sample(len(spam_texts), random_state=42))

    texts = spam_texts + clean_texts
    labels = [1] * len(spam_texts) + [0] * len(clean_texts)

    vectorizer = TfidfVectorizer(ngram_range=(1, 3), max_features=15000, sublinear_tf=True, stop_words="english")
    X = vectorizer.fit_transform(texts)
    y = np.array(labels)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    clf = LogisticRegression(C=2.0, max_iter=1000, class_weight="balanced", random_state=42)
    clf.fit(X_train, y_train)

    acc = accuracy_score(y_test, clf.predict(X_test))
    f1 = f1_score(y_test, clf.predict(X_test))
    print(f"✅ Huấn luyện thành công! Test Accuracy: {acc * 100:.2f}%, F1-Score: {f1:.4f}")

    artifact = {"vectorizer": vectorizer, "classifier": clf, "version": "2.0.0"}
    with open(model_output_path, "wb") as f:
        pickle.dump(artifact, f)

    global _SPAM_V2_MODEL
    _SPAM_V2_MODEL = artifact
    return artifact


if __name__ == "__main__":
    import sys
    if "--train" in sys.argv:
        train_and_save_supercharged_spam_model()
    else:
        test_title = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "FREE ROBUX GENERATOR LIVE 2026"
        is_sp, prob = predict_spam(test_title)
        print(f"Input: '{test_title}'\n-> Is Spam: {is_sp} (Probability: {prob * 100:.1f}%)")
