"""
Active Learning Spam Classifier (Solution 1)
--------------------------------------------
Uses Scikit-Learn Logistic Regression + MiniLM embeddings (or TF-IDF)
to learn user preferences from thumbs up/down feedback on Streamlit UI.
Trains in < 0.2s locally.
"""

import os
import sqlite3
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from database.db import DATABASE_URL, engine

# Path to database file if sqlite
DB_FILE = DATABASE_URL.replace("sqlite:///", "") if "sqlite" in DATABASE_URL else "livestream.db"

_CLF = None
_IS_TRAINED = False

SEED_SPAM_EXAMPLES = [
    ("ROBLOX GIVING FREE ROBUX LIVE STREAM 2026", "Roblox free robux giveaway promo codes", 0),
    ("FREE ROBUX GENERATOR LIVE 2026", "Get unlimited robux live stream giveaway", 0),
    ("FREE ADOPT ME PETS GIVEAWAY ROBLOX", "Free legendary pets roblox live", 0),
    ("CRYPTO PUMP 100X SIGNAL TELEGRAM", "Join group for free crypto signal", 0),
    ("FREE VBUCKS FORTNITE GENERATOR LIVE", "Unlimited vbucks giveaway fortnite", 0),
    ("MINECRAFT FREE SERVER HOSTING HACK", "Free minecraft host 247 live", 0),
    ("FREE FOLLOWERS TIKTOK GENERATOR 2026", "Get 10k followers instant live", 0),
    ("SPIN THE WHEEL FREE GIFT CARD LIVE", "Win amazon gift card live stream", 0),
    ("FREE ROBUX LIVE STREAM TODAY", "Roblox promo code live giveaway", 0),
    ("FREE DIAMONDS FREE FIRE LIVE", "Unlimited diamonds giveaway free fire", 0),
]

SEED_GOOD_EXAMPLES = [
    ("Modeling Your Non-Profit's Strategic Roadmap: A Live MNN Webinar", "Massachusetts Nonprofit Network strategic planning webinar", 1),
    ("Charity Water Fundraiser Live Stream 2026", "Raising money for clean water in Africa", 1),
    ("Tokenization Webinar with Apex Capital", "Discussion on real world asset tokenization on blockchain", 1),
    ("AI Tools for HR Recruitment Workshop", "Automate candidate sourcing with GenAI", 1),
    ("Saas Founder Summit 2026 Live", "Scaling B2B SaaS from 1M to 10M ARR", 1),
    ("Community Development Workshop Series", "Nonprofit leadership and grant writing live", 1),
    ("Philanthropy & Social Impact Conference", "Annual online summit for charitable giving", 1),
    ("Real-World Asset Tokenization Workshop", "Web3 workshop on asset tokenization", 1),
]


def init_feedback_db():
    """Tạo bảng user_feedback trong CSDL SQLite nếu chưa tồn tại và nạp dữ liệu mẫu ban đầu."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                label INTEGER NOT NULL, -- 0 = Spam/Rác, 1 = Đúng tiềm năng
                url TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Kiểm tra xem đã có dữ liệu mẫu chưa
        count = cur.execute("SELECT COUNT(*) FROM user_feedback").fetchone()[0]
        if count == 0:
            for title, desc, label in SEED_SPAM_EXAMPLES + SEED_GOOD_EXAMPLES:
                try:
                    cur.execute(
                        "INSERT OR IGNORE INTO user_feedback (title, description, label, url) VALUES (?, ?, ?, ?)",
                        (title, desc, label, f"seed_{hash(title)}")
                    )
                except Exception:
                    pass
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Spam Classifier DB] Init error: {e}")


def train_spam_model() -> bool:
    """Tự động huấn luyện mô hình Scikit-Learn trên tập dữ liệu feedback."""
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

        # Kiểm tra nếu chỉ có 1 class
        if len(set(labels)) < 2:
            return False

        # Lấy embeddings thông qua MiniLM
        from ai.minilm_scorer import _load_model
        model = _load_model()

        if model is not None:
            embeddings = model.encode(texts, normalize_embeddings=True)
        else:
            # Fallback sang TF-IDF TfidfVectorizer từ scikit-learn
            from sklearn.feature_extraction.text import TfidfVectorizer
            vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
            embeddings = vectorizer.fit_transform(texts)
            _CLF = ("tfidf", vectorizer, None)

        from sklearn.linear_model import LogisticRegression
        clf = LogisticRegression(C=1.0, max_iter=200)
        clf.fit(embeddings, labels)

        if model is not None:
            _CLF = ("minilm", model, clf)
        else:
            _CLF = ("tfidf", vectorizer, clf)

        _IS_TRAINED = True
        print(f"[Spam Classifier] Trained successfully on {len(rows)} user feedback samples!")
        return True

    except Exception as e:
        print(f"[Spam Classifier] Training error: {e}")
        return False


def predict_spam(title: str, description: str = "") -> Tuple[bool, float]:
    """
    Dự đoán xem tiêu đề + mô tả có phải là Spam/Rác hay không.
    Trả về: (is_spam: bool, spam_probability: float từ 0.0 đến 1.0)
    """
    global _CLF, _IS_TRAINED
    if not _IS_TRAINED or _CLF is None:
        train_success = train_spam_model()
        if not train_success or _CLF is None:
            return (False, 0.0)

    text = f"{str(title or '').strip()}. {str(description or '').strip()[:200]}".strip()
    if not text:
        return (False, 0.0)

    try:
        model_type = _CLF[0]
        if model_type == "minilm":
            minilm_model, clf = _CLF[1], _CLF[2]
            emb = minilm_model.encode([text], normalize_embeddings=True)
            # clf.predict_proba trả về [p_spam, p_good]
            probs = clf.predict_proba(emb)[0]
            good_prob = float(probs[1]) if len(probs) > 1 else float(probs[0])
            spam_prob = 1.0 - good_prob
        else:
            vectorizer, clf = _CLF[1], _CLF[2]
            emb = vectorizer.transform([text])
            probs = clf.predict_proba(emb)[0]
            good_prob = float(probs[1]) if len(probs) > 1 else float(probs[0])
            spam_prob = 1.0 - good_prob

        is_spam = spam_prob >= 0.55
        return (is_spam, round(spam_prob, 2))
    except Exception as e:
        print(f"[Spam Classifier] Predict error: {e}")
        return (False, 0.0)


def add_user_feedback(title: str, description: str, label: int, url: str = "") -> bool:
    """
    Ghi nhận phản hồi người dùng (label: 0 = Spam/Rác, 1 = Đúng tiềm năng)
    và kích hoạt huấn luyện lại mô hình tức thì.
    """
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

        # Huấn luyện lại mô hình ngay lập tức (mất ~0.1s)
        train_spam_model()
        return True
    except Exception as e:
        print(f"[Spam Classifier] Add feedback error: {e}")
        return False
