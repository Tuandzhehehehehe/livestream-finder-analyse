"""
tools/plot_title_likes_correlation.py — Title vs Likes Correlation Analysis
===========================================================================
Khảo sát mối tương quan đa biến giữa các yếu tố trong Tiêu đề (Title)
và Lượt Like / Tương tác cộng đồng trên 4,569 Video YouTube & 1,032,225 Bình luận.
"""

import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import pearsonr, spearmanr


def run_analysis():
    print("=" * 85)
    print("🚀 BẮT ĐẦU PHÂN TÍCH TƯƠNG QUAN GIỮA TIÊU ĐỀ (TITLE) VÀ LƯỢT LIKES / TƯƠNG TÁC")
    print("=" * 85)

    parquet_path = "data/youtube_comment_sentiment.parquet"
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(f"Không tìm thấy file {parquet_path}")

    df = pd.read_parquet(parquet_path)

    # 1. Tổng hợp theo từng Video (Groupby VideoID, VideoTitle)
    video_df = df.groupby(["VideoID", "VideoTitle"]).agg(
        total_comments=("CommentID", "count"),
        total_likes=("Likes", "sum"),
        avg_likes_per_comment=("Likes", "mean"),
        max_likes=("Likes", "max"),
        pct_positive_sentiment=("Sentiment", lambda s: (s == "Positive").mean() * 100),
        pct_negative_sentiment=("Sentiment", lambda s: (s == "Negative").mean() * 100),
    ).reset_index()

    # 2. Trích xuất các đặc trưng tiêu đề (Title Feature Extraction)
    video_df["char_length"] = video_df["VideoTitle"].apply(lambda t: len(str(t).strip()))
    video_df["word_count"] = video_df["VideoTitle"].apply(lambda t: len(str(t).strip().split()))
    video_df["caps_ratio"] = video_df["VideoTitle"].apply(lambda t: sum(1 for c in str(t) if c.isupper()) / max(1, len(str(t))))
    video_df["has_exclamation"] = video_df["VideoTitle"].apply(lambda t: 1 if "!" in str(t) else 0)
    video_df["has_question"] = video_df["VideoTitle"].apply(lambda t: 1 if "?" in str(t) else 0)
    video_df["has_number"] = video_df["VideoTitle"].apply(lambda t: 1 if any(c.isdigit() for c in str(t)) else 0)
    video_df["has_hashtag"] = video_df["VideoTitle"].apply(lambda t: 1 if "#" in str(t) else 0)
    video_df["has_separator"] = video_df["VideoTitle"].apply(lambda t: 1 if any(b in str(t) for b in ["[", "]", "|", "—", "-", ":", "•"]) else 0)

    # Phân nhóm độ dài tiêu đề
    def get_length_bracket(l):
        if l <= 30: return "1. Ngắn (≤30 ký tự)"
        elif l <= 60: return "2. Chuẩn SEO (31-60 ký tự)"
        elif l <= 90: return "3. Dài (61-90 ký tự)"
        else: return "4. Rất dài (>90 ký tự)"

    video_df["length_bracket"] = video_df["char_length"].apply(get_length_bracket)

    # 3. Vẽ cụm 4 biểu đồ phân tích chuyên sâu
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, axes = plt.subplots(2, 2, figsize=(16, 12), dpi=300)

    # --- Plot 1: Lượt Likes Trung Bình Theo Độ Dài Tiêu Đề ---
    ax1 = axes[0, 0]
    bracket_avg = video_df.groupby("length_bracket")["avg_likes_per_comment"].mean().reset_index()
    bars1 = ax1.bar(bracket_avg["length_bracket"], bracket_avg["avg_likes_per_comment"], color="#3b82f6", edgecolor="black", width=0.5)
    ax1.set_title("1. Lượt Like Trung Bình Theo Độ Dài Tiêu Đề", fontsize=12, fontweight="bold", pad=12)
    ax1.set_ylabel("Likes trung bình / comment", fontsize=10)
    ax1.tick_params(axis="x", rotation=15)
    for b in bars1:
        y = b.get_height()
        ax1.text(b.get_x() + b.get_width()/2, y + 0.1, f"{y:.2f}", ha="center", fontweight="bold")

    # --- Plot 2: Tương Quan Giữa Tỷ Lệ Viết Hoa (All-Caps) & Lượt Likes ---
    ax2 = axes[0, 1]
    sns.regplot(
        data=video_df[video_df["total_likes"] < video_df["total_likes"].quantile(0.95)],
        x="caps_ratio", y="total_likes",
        scatter_kws={"alpha": 0.25, "color": "#8b5cf6", "s": 15},
        line_kws={"color": "#ef4444", "linewidth": 2},
        ax=ax2
    )
    ax2.set_title("2. Tương Quan Tỷ Lệ Viết Hoa (Caps Ratio) vs Tổng Lượt Like", fontsize=12, fontweight="bold", pad=12)
    ax2.set_xlabel("Tỷ lệ chữ in hoa trong Tiêu đề (0.0 -> 1.0)", fontsize=10)
    ax2.set_ylabel("Tổng lượt Like (Loại bỏ 5% outlier)", fontsize=10)

    # --- Plot 3: Tác Động Của Các Yếu Tố Định Dạng (! ? Số Hashtag) Lên Likes ---
    ax3 = axes[1, 0]
    feature_impact = []
    binary_features = [
        ("has_exclamation", "Có dấu chấm than (!)"),
        ("has_question", "Có dấu hỏi (?)"),
        ("has_number", "Có số (Top 10, 24h)"),
        ("has_hashtag", "Có Hashtag (#shorts)"),
        ("has_separator", "Có phân cách (| - : )"),
    ]
    for col, name in binary_features:
        with_f = video_df[video_df[col] == 1]["avg_likes_per_comment"].mean()
        without_f = video_df[video_df[col] == 0]["avg_likes_per_comment"].mean()
        feature_impact.append({"Đặc trưng": name, "Có đặc trưng": with_f, "Không có": without_f})

    df_feat = pd.DataFrame(feature_impact).melt(id_vars="Đặc trưng", var_name="Trạng thái", value_name="Avg_Likes")
    sns.barplot(data=df_feat, x="Đặc trưng", y="Avg_Likes", hue="Trạng thái", palette=["#10b981", "#94a3b8"], ax=ax3, edgecolor="black")
    ax3.set_title("3. Tác Động Của Dấu Câu & Cấu Trúc Đến Lượt Like", fontsize=12, fontweight="bold", pad=12)
    ax3.set_ylabel("Likes trung bình / comment", fontsize=10)
    ax3.tick_params(axis="x", rotation=20)
    ax3.legend(title="Trạng thái")

    # --- Plot 4: Ma Trận Tương Quan Nhiệt (Heatmap) ---
    ax4 = axes[1, 1]
    corr_cols = ["char_length", "word_count", "caps_ratio", "total_likes", "avg_likes_per_comment", "pct_positive_sentiment", "pct_negative_sentiment"]
    corr_matrix = video_df[corr_cols].corr(method="spearman")
    rename_cols = {
        "char_length": "Độ dài ký tự",
        "word_count": "Số từ",
        "caps_ratio": "Tỷ lệ viết hoa",
        "total_likes": "Tổng Likes",
        "avg_likes_per_comment": "Likes TB/Comment",
        "pct_positive_sentiment": "% Cảm xúc Tích cực",
        "pct_negative_sentiment": "% Cảm xúc Tiêu cực",
    }
    corr_matrix.rename(index=rename_cols, columns=rename_cols, inplace=True)
    sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", center=0, fmt=".3f", linewidths=0.8, ax=ax4, square=True)
    ax4.set_title("4. Ma Trận Tương Quan Spearman (Heatmap)", fontsize=12, fontweight="bold", pad=12)

    plt.tight_layout()
    out_img = "data/title_likes_correlation.png"
    plt.savefig(out_img, dpi=300, bbox_inches="tight")
    print(f"🖼️ Đã lưu biểu đồ phân tích thành công -> {out_img}")

    # Copy to artifacts dir
    artifact_img = "/Users/ashernguyen/.gemini/antigravity-ide/brain/7f2132a6-d3f3-498f-bab0-8bc4af54e8b9/title_likes_correlation.png"
    try:
        import shutil
        shutil.copy(out_img, artifact_img)
        print(f"🖼️ Đã sao chép vào Artifacts: {artifact_img}")
    except Exception as e:
        print(f"Notice: {e}")


if __name__ == "__main__":
    run_analysis()
