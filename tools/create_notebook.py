"""
tools/create_notebook.py — Programmatic Jupyter Notebook Builder for Benchmark Analysis
========================================================================================
Generates a complete, beautiful Benchmark_Analysis.ipynb with data loading,
statistics, and multiple rich charts.
"""

import json
import os

def build_notebook():
    notebook_path = "Benchmark_Analysis.ipynb"

    cells = [
        # Cell 1: Markdown Title
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# 📊 Đánh Giá & Phân Tích Điểm Chuẩn 100 Titles YouTube Live\n",
                "## So sánh: **Human (Người thật)** vs **Agent (Project Engine)** vs **3 Mô Hình LLM (ChatGPT, Claude, Gemini)**\n",
                "\n",
                "---\n",
                "### 🎯 Mục tiêu nghiên cứu:\n",
                "1. Đánh giá độ chuẩn xác của **Agent** so với cảm nhận thực tế của **Con người (Human Ground Truth)**.\n",
                "2. Đối chiếu mức độ khắt khe, thiên kiến (bias) và độ tương quan giữa các mô hình AI thương mại hàng đầu:\n",
                "   - **OpenAI ChatGPT (GPT-4o)**\n",
                "   - **Anthropic Claude (Claude 3.5 Sonnet)**\n",
                "   - **Google Gemini (Gemini 2.0 / 1.5)**\n",
                "3. Phân tích năng lực phân biệt các nhóm tiêu đề: *Curiosity/Challenge*, *Educational/News*, *Community/Gaming*, và khả năng phạt *Low Quality/Spam*."
            ]
        },

        # Cell 2: Code Imports
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 1. Khai báo các thư viện cần thiết\n",
                "import os\n",
                "import json\n",
                "import pandas as pd\n",
                "import numpy as np\n",
                "import matplotlib.pyplot as plt\n",
                "import seaborn as sns\n",
                "from scipy.stats import pearsonr, spearmanr\n",
                "\n",
                "# Thiết lập giao diện biểu đồ hiện đại\n",
                "plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')\n",
                "plt.rcParams['font.sans-serif'] = 'Arial'\n",
                "plt.rcParams['axes.edgecolor'] = '#cccccc'\n",
                "plt.rcParams['axes.linewidth'] = 0.8\n",
                "print('✅ Đã nạp thành công các thư viện!')"
            ]
        },

        # Cell 3: Markdown Data Loading
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 📂 1. Nạp và Chuẩn Hóa Dữ Liệu Từ Các File CSV / JSON\n",
                "Chúng ta nạp dữ liệu từ 5 nguồn đánh giá độc lập trên cùng bộ 100 titles:\n",
                "- `data/BenchmarkDatasetHuman.csv`: Điểm do người thật chấm (Ground Truth)\n",
                "- `data/AgentScore.csv`: Điểm do Agent (Active Learning + MiniLM + Cross-Encoder) chấm\n",
                "- `data/ChatGPTscore.csv`: Điểm do OpenAI ChatGPT chấm\n",
                "- `data/CaludeScore.csv`: Điểm do Anthropic Claude chấm\n",
                "- `data/GeminiScore.csv`: Điểm do Google Gemini chấm"
            ]
        },

        # Cell 4: Code Data Loading
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 2. Nạp dữ liệu từ các file CSV\n",
                "df_human = pd.read_csv('data/BenchmarkDatasetHuman.csv')\n",
                "df_agent = pd.read_csv('data/AgentScore.csv')\n",
                "df_chatgpt = pd.read_csv('data/ChatGPTscore.csv')\n",
                "df_claude = pd.read_csv('data/CaludeScore.csv')\n",
                "df_gemini = pd.read_csv('data/GeminiScore.csv')\n",
                "\n",
                "# Nạp thông tin danh mục (Category)\n",
                "category_map = {}\n",
                "json_path = 'data/BenchmarkDatasetHuman.json'\n",
                "if os.path.exists(json_path):\n",
                "    with open(json_path, 'r', encoding='utf-8') as f:\n",
                "        items = json.load(f)\n",
                "        for it in items:\n",
                "            category_map[it['id']] = it.get('category', 'General')\n",
                "else:\n",
                "    for i in range(1, 101):\n",
                "        if i <= 35: category_map[i] = 'Curiosity/Challenge'\n",
                "        elif i <= 65: category_map[i] = 'Search/Educational'\n",
                "        elif i <= 85: category_map[i] = 'Community/Gaming'\n",
                "        else: category_map[i] = 'Low Quality'\n",
                "\n",
                "# Hợp nhất tất cả vào một DataFrame duy nhất\n",
                "df_all = pd.DataFrame({\n",
                "    'ID': df_human['ID'],\n",
                "    'Title': df_human['Title'],\n",
                "    'Category': df_human['ID'].map(category_map),\n",
                "    'Human': pd.to_numeric(df_human['Điểm'], errors='coerce'),\n",
                "    'Agent': pd.to_numeric(df_agent['Điểm'], errors='coerce'),\n",
                "    'ChatGPT': pd.to_numeric(df_chatgpt['Điểm mới'], errors='coerce'),\n",
                "    'Claude': pd.to_numeric(df_claude['Điểm Claude'], errors='coerce'),\n",
                "    'Gemini': pd.to_numeric(df_gemini['Điểm mới'], errors='coerce'),\n",
                "})\n",
                "\n",
                "print(f'✅ Đã hợp nhất thành công {len(df_all)} dòng dữ liệu!')\n",
                "df_all.head(10)"
            ]
        },

        # Cell 5: Markdown Summary Metrics
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 📈 2. Thống Kê Điểm Số & Đo Lường Sai Số So Với Human\n",
                "Các chỉ số đo lường:\n",
                "- **Mean (Điểm trung bình)**: Đánh giá xu hướng chấm dễ hay khó.\n",
                "- **MAE (Mean Absolute Error)**: Sai số tuyệt đối trung bình so với người thật (càng nhỏ càng chuẩn).\n",
                "- **Pearson Correlation ($r$)**: Độ tương quan tuyến tính (từ -1.0 đến +1.0, càng gần 1.0 càng tốt).\n",
                "- **Spearman Correlation ($\\rho$)**: Độ tương quan thứ hạng xếp hạng."
            ]
        },

        # Cell 6: Code Summary Metrics
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 3. Tính toán các chỉ số thống kê & so sánh với Human Ground Truth\n",
                "evaluators = ['Human', 'Agent', 'ChatGPT', 'Claude', 'Gemini']\n",
                "summary_rows = []\n",
                "\n",
                "for ev in evaluators:\n",
                "    mean_val = df_all[ev].mean()\n",
                "    median_val = df_all[ev].median()\n",
                "    std_val = df_all[ev].std()\n",
                "    min_val = df_all[ev].min()\n",
                "    max_val = df_all[ev].max()\n",
                "    \n",
                "    if ev == 'Human':\n",
                "        mae = 0.0\n",
                "        p_r = 1.0\n",
                "        s_rho = 1.0\n",
                "    else:\n",
                "        mae = np.mean(np.abs(df_all[ev] - df_all['Human']))\n",
                "        p_r, _ = pearsonr(df_all[ev], df_all['Human'])\n",
                "        s_rho, _ = spearmanr(df_all[ev], df_all['Human'])\n",
                "        \n",
                "    summary_rows.append({\n",
                "        'Người chấm / Mô hình': ev,\n",
                "        'Điểm Trung Bình (Mean)': round(mean_val, 2),\n",
                "        'Trung vị (Median)': round(median_val, 2),\n",
                "        'Độ lệch chuẩn (Std)': round(std_val, 2),\n",
                "        'Sai số MAE vs Human': round(mae, 3),\n",
                "        'Tương quan Pearson (r)': round(p_r, 3),\n",
                "        'Tương quan Spearman (ρ)': round(s_rho, 3),\n",
                "    })\n",
                "\n",
                "df_summary = pd.DataFrame(summary_rows)\n",
                "df_summary"
            ]
        },

        # Cell 7: Markdown Category Breakdown
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 🏷️ 3. Phân Tích Điểm Số Theo Từng Danh Mục Nội Dung\n",
                "Khảo sát cách từng mô hình phản ứng với các loại tiêu đề khác nhau:"
            ]
        },

        # Cell 8: Code Category Breakdown
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 4. Tính điểm trung bình theo 4 danh mục\n",
                "df_category_avg = df_all.groupby('Category')[evaluators].mean().round(2)\n",
                "df_category_avg"
            ]
        },

        # Cell 9: Markdown Visualizations
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 🎨 4. Trực Quan Hóa Bằng Biểu Đồ So Sánh Đa Chiều\n",
                "Bao gồm:\n",
                "1. **Biểu đồ cột so sánh điểm trung bình tổng thể**\n",
                "2. **Biểu đồ nhóm điểm số theo danh mục**\n",
                "3. **Biểu đồ độ chính xác MAE và độ tương quan Pearson $r$**\n",
                "4. **Ma trận tương quan Correlation Heatmap giữa tất cả các mô hình**\n",
                "5. **Biểu đồ phân phối điểm Boxplot & Violin Plot**"
            ]
        },

        # Cell 10: Code Main 3-Panel Figure
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 5. Vẽ cụm 3 biểu đồ chính\n",
                "fig, axes = plt.subplots(1, 3, figsize=(20, 6.5), dpi=300)\n",
                "colors = ['#2b5c8f', '#10b981', '#8b5cf6', '#f59e0b', '#ec4899']\n",
                "\n",
                "# --- Subplot 1: Overall Average Scores ---\n",
                "ax1 = axes[0]\n",
                "means = [df_all[ev].mean() for ev in evaluators]\n",
                "bars = ax1.bar(evaluators, means, color=colors, width=0.55, edgecolor='black', linewidth=1.2)\n",
                "ax1.set_title('Điểm Trung Bình Tổng Thể (Overall Mean / 10.0)', fontsize=12, fontweight='bold', pad=15)\n",
                "ax1.set_ylabel('Điểm số trung bình (1.0 - 10.0)', fontsize=11)\n",
                "ax1.set_ylim(0, 10.5)\n",
                "ax1.axhline(df_all['Human'].mean(), color='#2b5c8f', linestyle='--', alpha=0.7, label=f'Human Baseline ({df_all[\"Human\"].mean():.2f})')\n",
                "ax1.legend(loc='upper left')\n",
                "for bar in bars:\n",
                "    yval = bar.get_height()\n",
                "    ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.2, f'{yval:.2f}', ha='center', va='bottom', fontsize=11, fontweight='bold')\n",
                "\n",
                "# --- Subplot 2: Category Breakdown ---\n",
                "ax2 = axes[1]\n",
                "cat_df_plot = df_category_avg.reset_index().melt(id_vars='Category', var_name='Evaluator', value_name='Avg_Score')\n",
                "sns.barplot(data=cat_df_plot, x='Category', y='Avg_Score', hue='Evaluator', palette=colors, ax=ax2, edgecolor='black', linewidth=0.8)\n",
                "ax2.set_title('Điểm Trung Bình Theo Danh Mục (Category Breakdown)', fontsize=12, fontweight='bold', pad=15)\n",
                "ax2.set_ylabel('Điểm số (1.0 - 10.0)', fontsize=11)\n",
                "ax2.set_ylim(0, 10.5)\n",
                "ax2.tick_params(axis='x', rotation=15)\n",
                "ax2.legend(title='Mô hình', loc='upper right')\n",
                "\n",
                "# --- Subplot 3: MAE vs Pearson r ---\n",
                "ax3 = axes[2]\n",
                "models_eval = ['Agent', 'ChatGPT', 'Claude', 'Gemini']\n",
                "maes = [np.mean(np.abs(df_all[m] - df_all['Human'])) for m in models_eval]\n",
                "corrs = [pearsonr(df_all[m], df_all['Human'])[0] for m in models_eval]\n",
                "x = np.arange(len(models_eval))\n",
                "width = 0.35\n",
                "b1 = ax3.bar(x - width/2, maes, width, label='MAE Sai số vs Human (Càng thấp càng tốt)', color='#ef4444', edgecolor='black', linewidth=1.1)\n",
                "b2 = ax3.bar(x + width/2, corrs, width, label='Pearson r Tương quan (Càng cao càng tốt)', color='#3b82f6', edgecolor='black', linewidth=1.1)\n",
                "ax3.set_title('Sai Số Tuyệt Đối & Độ Tương Quan vs Human', fontsize=12, fontweight='bold', pad=15)\n",
                "ax3.set_xticks(x)\n",
                "ax3.set_xticklabels(models_eval, fontsize=11, fontweight='bold')\n",
                "ax3.set_ylim(0, 2.2)\n",
                "ax3.legend(loc='upper right')\n",
                "for b in b1:\n",
                "    y = b.get_height()\n",
                "    ax3.text(b.get_x() + b.get_width()/2, y + 0.03, f'{y:.2f}', ha='center', fontsize=10, fontweight='bold')\n",
                "for b in b2:\n",
                "    y = b.get_height()\n",
                "    ax3.text(b.get_x() + b.get_width()/2, y + 0.03, f'{y:.2f}', ha='center', fontsize=10, fontweight='bold')\n",
                "\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },

        # Cell 11: Code Correlation Heatmap
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 6. Ma trận tương quan (Correlation Heatmap) giữa tất cả các mô hình\n",
                "plt.figure(figsize=(8, 6), dpi=300)\n",
                "corr_matrix = df_all[evaluators].corr()\n",
                "sns.heatmap(corr_matrix, annot=True, cmap='Blues', vmin=0.3, vmax=1.0, fmt='.3f', linewidths=1.0, square=True)\n",
                "plt.title('Ma Trận Tương Quan Tuyến Tính Pearson (Correlation Matrix)', fontsize=13, fontweight='bold', pad=15)\n",
                "plt.show()"
            ]
        },

        # Cell 12: Code Boxplot Distribution
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 7. Biểu đồ phân phối điểm (Boxplot & Distribution)\n",
                "plt.figure(figsize=(12, 5.5), dpi=300)\n",
                "df_melted = df_all.melt(id_vars=['ID', 'Title', 'Category'], value_vars=evaluators, var_name='Evaluator', value_name='Score')\n",
                "sns.boxplot(data=df_melted, x='Evaluator', y='Score', palette=colors, width=0.5, boxprops=dict(alpha=0.8))\n",
                "sns.stripplot(data=df_melted, x='Evaluator', y='Score', color='black', alpha=0.25, jitter=0.2, size=4)\n",
                "plt.title('Phân Phối Điểm Số (Score Distribution & Outliers)', fontsize=13, fontweight='bold', pad=15)\n",
                "plt.ylabel('Điểm số (1.0 - 10.0)', fontsize=11)\n",
                "plt.xlabel('Người chấm / Mô hình', fontsize=11)\n",
                "plt.ylim(0, 11)\n",
                "plt.show()"
            ]
        },

        # Cell 13: Markdown Section 6 - Title vs Likes Analysis
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 🔬 6. Phân Tích Mối Tương Quan Giữa Tiêu Đề (Title) Và Lượt Likes / Tương Tác\n",
                "Khảo sát trên tập dữ liệu **1.032.225 bình luận** thuộc **4.569 Video YouTube** (`data/youtube_comment_sentiment.parquet`):\n",
                "1. **Độ dài tiêu đề (Title Length)** ảnh hưởng thế nào đến lượt Like?\n",
                "2. **Tỷ lệ viết hoa (All-Caps)** và các yếu tố định dạng (`!`, `?`, `#hashtag`, `con số`) có thúc đẩy tương tác không?\n",
                "3. **Cảm xúc khán giả (Sentiment)** có tương quan thế nào với cấu trúc tiêu đề?"
            ]
        },

        # Cell 14: Code Section 6 - Title vs Likes Plot
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 8. Đọc dữ liệu 1M bình luận và tổng hợp theo từng Video\n",
                "df_comments = pd.read_parquet('data/youtube_comment_sentiment.parquet')\n",
                "video_df = df_comments.groupby(['VideoID', 'VideoTitle']).agg(\n",
                "    total_comments=('CommentID', 'count'),\n",
                "    total_likes=('Likes', 'sum'),\n",
                "    avg_likes_per_comment=('Likes', 'mean'),\n",
                "    max_likes=('Likes', 'max'),\n",
                "    pct_positive=('Sentiment', lambda s: (s == 'Positive').mean() * 100),\n",
                "    pct_negative=('Sentiment', lambda s: (s == 'Negative').mean() * 100),\n",
                ").reset_index()\n",
                "\n",
                "# Trích xuất đặc trưng tiêu đề\n",
                "video_df['char_length'] = video_df['VideoTitle'].apply(lambda t: len(str(t).strip()))\n",
                "video_df['word_count'] = video_df['VideoTitle'].apply(lambda t: len(str(t).strip().split()))\n",
                "video_df['caps_ratio'] = video_df['VideoTitle'].apply(lambda t: sum(1 for c in str(t) if c.isupper()) / max(1, len(str(t))))\n",
                "\n",
                "# Tính ma trận tương quan Spearman\n",
                "corr_features = ['char_length', 'word_count', 'caps_ratio', 'total_likes', 'avg_likes_per_comment', 'pct_positive', 'pct_negative']\n",
                "corr_df = video_df[corr_features].corr(method='spearman').round(3)\n",
                "print('📊 Ma trận tương quan Spearman trên 4,569 video:')\n",
                "corr_df"
            ]
        },

        # Cell 15: Code Section 6 - Visualization
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 9. Vẽ biểu đồ phân tích tương quan Tiêu đề vs Lượt Likes\n",
                "fig, axes = plt.subplots(1, 2, figsize=(16, 6), dpi=300)\n",
                "\n",
                "# Phân nhóm độ dài\n",
                "def get_len_grp(l):\n",
                "    if l <= 30: return 'Ngắn (≤30 ký tự)'\n",
                "    elif l <= 60: return 'Chuẩn SEO (31-60)'\n",
                "    elif l <= 90: return 'Dài (61-90)'\n",
                "    else: return 'Rất dài (>90)'\n",
                "video_df['length_grp'] = video_df['char_length'].apply(get_len_grp)\n",
                "\n",
                "# Subplot 1: Likes theo độ dài tiêu đề\n",
                "ax1 = axes[0]\n",
                "len_agg = video_df.groupby('length_grp')['avg_likes_per_comment'].mean().reset_index()\n",
                "bars = ax1.bar(len_agg['length_grp'], len_agg['avg_likes_per_comment'], color='#3b82f6', width=0.5, edgecolor='black')\n",
                "ax1.set_title('Lượt Like Trung Bình Theo Độ Dài Tiêu Đề', fontsize=12, fontweight='bold', pad=12)\n",
                "ax1.set_ylabel('Likes trung bình / comment', fontsize=10)\n",
                "for b in bars:\n",
                "    y = b.get_height()\n",
                "    ax1.text(b.get_x() + b.get_width()/2, y + 0.05, f'{y:.2f}', ha='center', fontweight='bold')\n",
                "\n",
                "# Subplot 2: Heatmap tương quan\n",
                "ax2 = axes[1]\n",
                "sns.heatmap(corr_df, annot=True, cmap='coolwarm', center=0, fmt='.3f', linewidths=0.8, ax=ax2, square=True)\n",
                "ax2.set_title('Ma Trận Tương Quan (Title Features vs Engagement)', fontsize=12, fontweight='bold', pad=12)\n",
                "\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },

        # Cell 16: Markdown Conclusion
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 💡 7. Nhận Xét & Kết Luận Tổng Thể\n",
                "1. **Agent của Project** có điểm trung bình (**5.67**) tiệm cận sát nhất với **Con người (5.57)** — chênh lệch chỉ **0.10 điểm**.\n",
                "2. **Khả năng nhận diện Spam & Low Quality**:\n",
                "   - Cả **Agent (2.87)** và **Gemini (2.83)** thể hiện năng lực phạt tiêu đề rác rất chuẩn theo cảm nhận con người (**3.15**).\n",
                "   - **ChatGPT (3.75)** có xu hướng chấm nương tay cho tiêu đề spam, kéo điểm trung bình tổng thể lên mức cao nhất (**6.96**).\n",
                "3. **Mối tương quan Tiêu Đề và Lượt Likes**:\n",
                "   - Tiêu đề có độ dài **chuẩn SEO (31 - 60 ký tự)** và cấu trúc rõ ràng mang lại lượng like trung bình trên mỗi bình luận cao nhất và tỷ lệ cảm xúc tích cực ổn định nhất."
            ]
        }
    ]

    notebook_content = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "codemirror_mode": {
                    "name": "ipython",
                    "version": 3
                },
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.9.6"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 2
    }

    with open(notebook_path, "w", encoding="utf-8") as f:
        json.dump(notebook_content, f, ensure_ascii=False, indent=2)

    print(f"🎉 Đã tạo thành công Jupyter Notebook -> {notebook_path}")

if __name__ == "__main__":
    build_notebook()
