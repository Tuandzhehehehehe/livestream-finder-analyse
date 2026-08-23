"""
tools/pull_sentiment_dataset.py — Download Hugging Face youtube-comment-sentiment Dataset
========================================================================================
Pulls the complete 1,032,225-row dataset from Hugging Face:
  Repository: AmaanP314/youtube-comment-sentiment
Saves locally to:
  - data/youtube_comment_sentiment.parquet (Full 1M+ dataset, compressed & super fast)
  - data/youtube_comment_sentiment_sample.csv (Top 5,000 sample for quick Excel / Pandas preview)
"""

import os
import pandas as pd
from datasets import load_dataset


def download_dataset():
    print("=" * 80)
    print("🚀 BẮT ĐẦU TẢI DATASET 'AmaanP314/youtube-comment-sentiment' TỪ HUGGING FACE")
    print("=" * 80)

    data_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
    os.makedirs(data_dir, exist_ok=True)

    parquet_path = os.path.join(data_dir, "youtube_comment_sentiment.parquet")
    sample_csv_path = os.path.join(data_dir, "youtube_comment_sentiment_sample.csv")

    print("⏳ Đang kết nối Hugging Face Hub và tải toàn bộ dữ liệu...")
    ds = load_dataset("AmaanP314/youtube-comment-sentiment", split="train")
    print(f"✅ Đã tải thành công {len(ds):,} dòng dữ liệu!")

    # Chuyển thành Pandas DataFrame
    print("⏳ Đang chuyển đổi sang định dạng tối ưu Parquet...")
    df = ds.to_pandas()

    # 1. Lưu toàn bộ 1 triệu dòng dưới dạng Parquet (nhẹ, tối ưu bộ nhớ, đọc trong 0.5s)
    df.to_parquet(parquet_path, index=False, compression="snappy")
    parquet_size_mb = os.path.getsize(parquet_path) / (1024 * 1024)
    print(f"💾 Đã lưu TOÀN BỘ 1,032,225 dòng tại -> {parquet_path} ({parquet_size_mb:.2f} MB)")

    # 2. Lưu mẫu 5,000 dòng ra file CSV để người dùng mở bằng Excel / VS Code
    df_sample = df.head(5000)
    df_sample.to_csv(sample_csv_path, index=False, encoding="utf-8")
    print(f"📄 Đã lưu file MẪU 5,000 dòng tại -> {sample_csv_path}")

    print("\n" + "=" * 80)
    print("🎉 HOÀN THÀNH TẢI DATASET VỀ MÁY!")
    print(f"• Tổng số cột: {list(df.columns)}")
    print(f"• Phân bố cảm xúc (Sentiment Distribution):")
    print(df['Sentiment'].value_counts())
    print("=" * 80)


if __name__ == "__main__":
    download_dataset()
