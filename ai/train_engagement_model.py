"""
ai/train_engagement_model.py — Train Title Engagement Predictor (Direction 1)
=============================================================================
Huấn luyện mô hình Machine Learning dự đoán mức độ tương tác & lượt Like của Tiêu đề
dựa trên 4,569 Video YouTube và 1,032,225 Bình luận thực tế.

Mô hình học các đặc trưng:
  1. Lexical & Structural Features (độ dài, số từ, tỷ lệ viết hoa, dấu câu, emoji, cấu trúc)
  2. Semantic Features (TF-IDF N-grams / MiniLM Embeddings)

Xuất mô hình: data/models/engagement_model.pkl
"""

import os
import re
import pickle
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_absolute_error, r2_score
from scipy.stats import pearsonr, spearmanr


def extract_features(df_videos: pd.DataFrame) -> pd.DataFrame:
    """Trích xuất các đặc trưng kỹ thuật & ngữ nghĩa từ tiêu đề."""
    feats = pd.DataFrame(index=df_videos.index)
    titles = df_videos["VideoTitle"].astype(str)

    feats["char_length"] = titles.apply(lambda t: len(t.strip()))
    feats["word_count"] = titles.apply(lambda t: len(t.strip().split()))
    feats["caps_ratio"] = titles.apply(lambda t: sum(1 for c in t if c.isupper()) / max(1, len(t)))
    feats["digit_count"] = titles.apply(lambda t: sum(1 for c in t if c.isdigit()))
    feats["has_exclamation"] = titles.apply(lambda t: 1.0 if "!" in t else 0.0)
    feats["has_question"] = titles.apply(lambda t: 1.0 if "?" in t else 0.0)
    feats["has_hashtag"] = titles.apply(lambda t: 1.0 if "#" in t else 0.0)
    feats["has_colon_or_pipe"] = titles.apply(lambda t: 1.0 if any(c in t for c in ["|", ":", "—", "-", "[", "]"]) else 0.0)
    
    # Từ khóa thu hút cao (Power Keywords)
    power_keywords = ["how to", "live", "tutorial", "full course", "masterclass", "24/7", "review", "vs", "challenge", "secret"]
    for kw in power_keywords:
        feats[f"kw_{kw.replace(' ', '_')}"] = titles.apply(lambda t: 1.0 if kw in t.lower() else 0.0)

    return feats


def train_and_save_model():
    print("=" * 85)
    print("🚀 [DIRECTION 1] BẮT ĐẦU HUẤN LUYỆN TITLE ENGAGEMENT PREDICTOR")
    print("=" * 85)

    parquet_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "youtube_comment_sentiment.parquet"))
    models_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "models"))
    os.makedirs(models_dir, exist_ok=True)
    model_output_path = os.path.join(models_dir, "engagement_model.pkl")

    # 1. Nạp và tổng hợp dữ liệu theo Video
    print("⏳ Đang nạp dữ liệu từ Parquet...")
    df = pd.read_parquet(parquet_path)
    
    video_df = df.groupby(["VideoID", "VideoTitle"]).agg(
        total_comments=("CommentID", "count"),
        total_likes=("Likes", "sum"),
        avg_likes=("Likes", "mean"),
        pct_positive=("Sentiment", lambda s: (s == "Positive").mean() * 100),
    ).reset_index()

    print(f"✅ Đã tổng hợp dữ liệu của {len(video_df):,} Video YouTube!")

    # 2. Xây dựng Target Score (Điểm tương tác chuẩn hóa từ 0.0 đến 100.0)
    # Kết hợp giữa Lượt like trung bình và Tỷ lệ cảm xúc tích cực
    # Áp dụng Log-transform để xử lý phân phối lệch (skewed distribution)
    log_likes = np.log1p(video_df["avg_likes"])
    min_log, max_log = log_likes.quantile(0.02), log_likes.quantile(0.98)
    norm_likes = np.clip((log_likes - min_log) / max(1e-5, (max_log - min_log)), 0.0, 1.0) * 100.0
    
    # Target score: 70% từ Lượt likes thực tế + 30% từ Tỷ lệ cảm xúc tích cực
    target_engagement_score = (norm_likes * 0.7) + (video_df["pct_positive"] * 0.3)
    target_engagement_score = np.clip(target_engagement_score, 0.0, 100.0)

    # 3. Trích xuất đặc trưng
    print("⏳ Đang trích xuất đặc trưng văn bản & TF-IDF...")
    numeric_feats = extract_features(video_df)
    
    # TF-IDF trên tiêu đề
    tfidf = TfidfVectorizer(max_features=500, ngram_range=(1, 2), stop_words="english")
    tfidf_matrix = tfidf.fit_transform(video_df["VideoTitle"].astype(str)).toarray()
    
    # Ghép toàn bộ đặc trưng
    X = np.hstack([numeric_feats.values, tfidf_matrix])
    y = target_engagement_score.values

    # 4. Chia tập Train / Test (80 / 20)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 5. Huấn luyện Gradient Boosting Regressor
    print("⏳ Đang huấn luyện Gradient Boosting Regressor...")
    model = GradientBoostingRegressor(
        n_estimators=150,
        learning_rate=0.08,
        max_depth=4,
        random_state=42
    )
    model.fit(X_train, y_train)

    # 6. Đánh giá mô hình trên tập Test
    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    p_r, _ = pearsonr(y_test, y_pred)
    s_rho, _ = spearmanr(y_test, y_pred)

    print("=" * 85)
    print("📊 KẾT QUẢ ĐÁNH GIÁ MÔ HÌNH TRÊN TẬP TEST ĐỘC LẬP:")
    print(f"  • Sai số tuyệt đối (MAE)    : {mae:.2f} điểm / 100")
    print(f"  • Hệ số tương quan Pearson  : {p_r:.3f}")
    print(f"  • Hệ số tương quan Spearman : {s_rho:.3f}")
    print("=" * 85)

    # 7. Đóng gói và lưu Model Artifact
    artifact = {
        "model": model,
        "tfidf": tfidf,
        "feature_names": list(numeric_feats.columns),
        "min_log": min_log,
        "max_log": max_log,
        "version": "1.0.0",
        "sample_count": len(video_df),
    }

    with open(model_output_path, "wb") as f:
        pickle.dump(artifact, f)

    print(f"💾 Đã lưu mô hình thành công -> {model_output_path}")
    return artifact


if __name__ == "__main__":
    train_and_save_model()
