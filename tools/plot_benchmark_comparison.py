"""
tools/plot_benchmark_comparison.py — Generate Benchmark Comparison Charts
=========================================================================
So sánh điểm trung bình của:
  - Human (Ground Truth)
  - Agent (Project's Scoring Pipeline)
  - ChatGPT (GPT-4o)
  - Claude (Claude 3.5 Sonnet)
  - Gemini (Gemini 2.0 / 1.5)
"""

import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import pearsonr, spearmanr

# 1. Load Data
df_human = pd.read_csv("data/BenchmarkDatasetHuman.csv")
df_agent = pd.read_csv("data/AgentScore.csv")
df_chatgpt = pd.read_csv("data/ChatGPTscore.csv")
df_claude = pd.read_csv("data/CaludeScore.csv")
df_gemini = pd.read_csv("data/GeminiScore.csv")

# Load Categories from BenchmarkDatasetHuman.json if available
category_map = {}
json_path = "data/BenchmarkDatasetHuman.json"
if os.path.exists(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
        for it in items:
            category_map[it["id"]] = it.get("category", "General")
else:
    for i in range(1, 101):
        if i <= 35: category_map[i] = "Curiosity/Challenge"
        elif i <= 65: category_map[i] = "Search/Educational"
        elif i <= 85: category_map[i] = "Community/Gaming"
        else: category_map[i] = "Low Quality"

# Merge all into one consolidated DataFrame
df_all = pd.DataFrame({
    "ID": df_human["ID"],
    "Title": df_human["Title"],
    "Category": df_human["ID"].map(category_map),
    "Human": pd.to_numeric(df_human["Điểm"], errors="coerce"),
    "Agent": pd.to_numeric(df_agent["Điểm"], errors="coerce"),
    "ChatGPT": pd.to_numeric(df_chatgpt["Điểm mới"], errors="coerce"),
    "Claude": pd.to_numeric(df_claude["Điểm Claude"], errors="coerce"),
    "Gemini": pd.to_numeric(df_gemini["Điểm mới"], errors="coerce"),
})

# Calculate Overall Means
means = {
    "Human (Ground Truth)": df_all["Human"].mean(),
    "Agent (Project Engine)": df_all["Agent"].mean(),
    "ChatGPT (GPT-4o)": df_all["ChatGPT"].mean(),
    "Claude (3.5 Sonnet)": df_all["Claude"].mean(),
    "Gemini (Google)": df_all["Gemini"].mean(),
}

# Calculate MAE & Pearson Correlation with Human
metrics = {}
for model in ["Agent", "ChatGPT", "Claude", "Gemini"]:
    mae = np.mean(np.abs(df_all[model] - df_all["Human"]))
    p_corr, _ = pearsonr(df_all[model], df_all["Human"])
    s_corr, _ = spearmanr(df_all[model], df_all["Human"])
    metrics[model] = {
        "MAE": mae,
        "Pearson_r": p_corr,
        "Spearman_rho": s_corr,
        "Mean_Score": df_all[model].mean()
    }

print("="*80)
print("📊 BẢNG TỔNG HỢP ĐIỂM TRUNG BÌNH & ĐỘ TƯƠNG QUAN VỚI HUMAN (100 TITLES)")
print("="*80)
print(f"• Human (Chuẩn người thật) : Điểm TB = {means['Human (Ground Truth)']:.2f} / 10.0")
for m, v in metrics.items():
    print(f"• {m:10s} : Điểm TB = {v['Mean_Score']:.2f} | MAE vs Human = {v['MAE']:.3f} | Pearson r = {v['Pearson_r']:.3f} | Spearman rho = {v['Spearman_rho']:.3f}")
print("="*80)

# Category-wise averages
cat_means = df_all.groupby("Category")[["Human", "Agent", "ChatGPT", "Claude", "Gemini"]].mean()
print("\n📋 Điểm trung bình theo 4 danh mục:")
print(cat_means.round(2))

# ── PLOTTING HIGH QUALITY COMPOSITE FIGURE ────────────────────────────────────
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
fig, axes = plt.subplots(1, 3, figsize=(20, 6.5), dpi=300)
colors = ["#2b5c8f", "#10b981", "#8b5cf6", "#f59e0b", "#ec4899"]

# Subplot 1: Overall Average Score Comparison
ax1 = axes[0]
names = list(means.keys())
score_vals = list(means.values())
bars = ax1.bar(names, score_vals, color=colors, width=0.55, edgecolor="black", linewidth=1.2)
ax1.set_title("Điểm Trung Bình Tổng Thể (Overall Average Score / 10.0)", fontsize=13, fontweight="bold", pad=15)
ax1.set_ylabel("Điểm số trung bình (1.0 - 10.0)", fontsize=11)
ax1.set_ylim(0, 10.5)
ax1.tick_params(axis="x", rotation=25)

# Add values above bars
for bar in bars:
    yval = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.2, f"{yval:.2f}", ha="center", va="bottom", fontsize=11, fontweight="bold")

# Add horizontal reference line for Human
ax1.axhline(means["Human (Ground Truth)"], color="#2b5c8f", linestyle="--", alpha=0.7, label=f"Human Baseline ({means['Human (Ground Truth)']:.2f})")
ax1.legend(loc="upper left")

# Subplot 2: Average Score by 4 Categories
ax2 = axes[1]
cat_df_plot = cat_means.reset_index().melt(id_vars="Category", var_name="Evaluator", value_name="Avg_Score")
sns.barplot(data=cat_df_plot, x="Category", y="Avg_Score", hue="Evaluator", palette=colors, ax=ax2, edgecolor="black", linewidth=0.8)
ax2.set_title("Điểm Trung Bình Theo 4 Danh Mục (Category Breakdown)", fontsize=13, fontweight="bold", pad=15)
ax2.set_ylabel("Điểm số (1.0 - 10.0)", fontsize=11)
ax2.set_xlabel("Danh mục bài test", fontsize=11)
ax2.set_ylim(0, 10.5)
ax2.tick_params(axis="x", rotation=15)
ax2.legend(title="Người chấm / Mô hình", loc="upper right")

# Subplot 3: Correlation & MAE vs Human (Độ chính xác so với người thật)
ax3 = axes[2]
models_eval = ["Agent", "ChatGPT", "Claude", "Gemini"]
maes = [metrics[m]["MAE"] for m in models_eval]
corrs = [metrics[m]["Pearson_r"] for m in models_eval]

x = np.arange(len(models_eval))
width = 0.35
b1 = ax3.bar(x - width/2, maes, width, label="MAE Sai số vs Human (Càng thấp càng tốt)", color="#ef4444", edgecolor="black", linewidth=1.1)
b2 = ax3.bar(x + width/2, corrs, width, label="Pearson r Tương quan (Càng cao càng tốt)", color="#3b82f6", edgecolor="black", linewidth=1.1)

ax3.set_title("Độ Chuẩn Xác So Với Người Thật (MAE & Correlation vs Human)", fontsize=13, fontweight="bold", pad=15)
ax3.set_xticks(x)
ax3.set_xticklabels(models_eval, fontsize=11, fontweight="bold")
ax3.set_ylim(0, 1.2)
ax3.legend(loc="upper right")

for b in b1:
    y = b.get_height()
    ax3.text(b.get_x() + b.get_width()/2, y + 0.02, f"{y:.2f}", ha="center", fontsize=10, fontweight="bold")
for b in b2:
    y = b.get_height()
    ax3.text(b.get_x() + b.get_width()/2, y + 0.02, f"{y:.2f}", ha="center", fontsize=10, fontweight="bold")

plt.tight_layout()

# Save image
out_path = "data/benchmark_comparison_chart.png"
plt.savefig(out_path, dpi=300, bbox_inches="tight")
print(f"\n🖼️ Đã lưu biểu đồ so sánh thành công: {out_path}")

# Copy to artifacts dir
artifact_img = "/Users/ashernguyen/.gemini/antigravity-ide/brain/7f2132a6-d3f3-498f-bab0-8bc4af54e8b9/benchmark_comparison_chart.png"
try:
    import shutil
    shutil.copy(out_path, artifact_img)
    print(f"🖼️ Đã sao chép biểu đồ vào Artifacts: {artifact_img}")
except Exception as e:
    print(f"Notice: {e}")
