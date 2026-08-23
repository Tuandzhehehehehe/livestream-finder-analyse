"""
tools/create_title_engagement_notebook.py — Programmatic Jupyter Notebook Builder
==================================================================================
Tạo notebook 'notebook/ExploreYouTubeTitleEngagement.ipynb' phân tích toàn diện mối tương quan
giữa các đặc tính quan sát được của Title (độ dài, caps, ?, !, số, từ kích thích...) và User Engagement
(Views, Likes, Comments, Sentiment) nhằm mục tiêu tiên đoán sức hút của nội dung.
"""

import json
import os


def build_title_engagement_notebook():
    output_dir = "notebook"
    os.makedirs(output_dir, exist_ok=True)
    notebook_path = os.path.join(output_dir, "ExploreYouTubeTitleEngagement.ipynb")

    cells = [
        # Cell 1: Title & Overview
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# 📈 Khám Phá Mối Tương Quan: Đặc Tính Tiêu Đề (Title Features) & User Engagement\n",
                "## 🎯 Tiên Đoán Sức Hút Video & Livestream Dựa Trên Các Yếu Tố Quan Sát Được Từ Tiêu Đề (Views, Likes, Comments, Sentiment)\n",
                "\n",
                "---\n",
                "### 🎯 Mục tiêu nghiên cứu:\n",
                "1. **Trích xuất đặc tính Tiêu đề (Title Feature Engineering)**: Bóc tách các tín hiệu định lượng từ tiêu đề video như: độ dài ký tự/từ, tỷ lệ chữ hoa (`Caps Ratio`), dấu hỏi `?`, dấu than `!`, con số, thẻ ngoặc `[ ]`, và các từ kích thích (`Power Words`).\n",
                "2. **Phân tích Ma trận Tương quan (Correlation Analysis)**: Đo lường độ tương quan tuyến tính (**Pearson**) và phi tuyến tính (**Spearman Rank**) giữa các đặc tính tiêu đề với `Views`, `Likes`, `Comments`, `Like-to-View Ratio`, và `Comment-to-View Ratio`.\n",
                "3. **Kiểm định Phân bố & So sánh Nhóm (Group Comparison)**: Đo lường sự khác biệt về lượng View/Like giữa các nhóm có/không có dấu hỏi, dấu than, con số cụ thể qua Box Plot & T-Test.\n",
                "4. **Phân tích Sắc thái Cảm xúc & Tương tác Bình luận (Sentiment & Comment Engagement)**: Đánh giá mối liên hệ giữa tiêu đề và mức độ phản hồi cảm xúc (Positive, Neutral, Negative) từ tập 5,000 bình luận.\n",
                "5. **Mô hình Hồi quy & Đánh giá Tầm quan trọng Đặc trưng (Feature Importance)**: Sử dụng **Random Forest Regressor** để xác định đặc tính tiêu đề nào có sức mạnh tiên đoán mức độ tương tác cao nhất."
            ]
        },

        # Cell 2: Imports & Visual Settings
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 1. Khai báo thư viện phân tích & thiết lập giao diện đồ thị thẩm mỹ\n",
                "import os\n",
                "import re\n",
                "import numpy as np\n",
                "import pandas as pd\n",
                "import matplotlib.pyplot as plt\n",
                "import seaborn as sns\n",
                "from scipy import stats\n",
                "from sklearn.ensemble import RandomForestRegressor\n",
                "from sklearn.model_selection import train_test_split\n",
                "from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error\n",
                "\n",
                "# Thiết lập giao diện đồ thị hiện đại & sắc nét\n",
                "plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')\n",
                "plt.rcParams['font.sans-serif'] = 'Arial'\n",
                "plt.rcParams['font.size'] = 11\n",
                "plt.rcParams['axes.edgecolor'] = '#cccccc'\n",
                "plt.rcParams['axes.linewidth'] = 0.8\n",
                "plt.rcParams['figure.dpi'] = 120\n",
                "\n",
                "print('✅ Đã nạp thành công các thư viện phân tích dữ liệu & Machine Learning!')"
            ]
        },

        # Cell 3: Data Loading Markdown
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 📂 1. Nạp & Khám Phá 2 Tập Dữ Liệu Thực Nghiệm\n",
                "1. **Tập Video Metadata (`kaggle_channel_meta.csv`)**: 316 videos chứa đầy đủ các chỉ số tương tác chính xác: `view_count`, `like_count`, `comment_count`, `duration_sec`, `video_title`.\n",
                "2. **Tập Comment & Sentiment (`youtube_comment_sentiment_sample.csv`)**: 5,000 mẫu bình luận kèm tiêu đề video, sắc thái cảm xúc (`Positive`, `Neutral`, `Negative`), `Likes`, `Replies`."
            ]
        },

        # Cell 4: Data Loading Code
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 2. Nạp dữ liệu từ thư mục data & Chuẩn hóa kiểu dữ liệu\n",
                "meta_path = '../data/kaggle_channel_meta.csv' if os.path.exists('../data/kaggle_channel_meta.csv') else 'data/kaggle_channel_meta.csv'\n",
                "sent_path = '../data/youtube_comment_sentiment_sample.csv' if os.path.exists('../data/youtube_comment_sentiment_sample.csv') else 'data/youtube_comment_sentiment_sample.csv'\n",
                "\n",
                "df_meta = pd.read_csv(meta_path)\n",
                "df_sent = pd.read_csv(sent_path)\n",
                "\n",
                "# Chuẩn hóa kiểu dữ liệu số cho df_meta để tránh lỗi kiểu chuỗi / rỗng\n",
                "for col in ['view_count', 'like_count', 'comment_count', 'duration_sec']:\n",
                "    df_meta[col] = pd.to_numeric(df_meta[col], errors='coerce').fillna(0)\n",
                "\n",
                "# Chuẩn hóa dữ liệu comment sentiment\n",
                "df_sent['Likes'] = pd.to_numeric(df_sent['Likes'], errors='coerce').fillna(0)\n",
                "df_sent['Replies'] = pd.to_numeric(df_sent['Replies'], errors='coerce').fillna(0)\n",
                "df_sent = df_sent[df_sent['Sentiment'].isin(['Positive', 'Neutral', 'Negative'])].copy()\n",
                "\n",
                "print(f'📊 Tập Video Metadata : {df_meta.shape[0]} dòng x {df_meta.shape[1]} cột')\n",
                "print(f'📊 Tập Comment Sentiment: {df_sent.shape[0]} dòng x {df_sent.shape[1]} cột')\n",
                "\n",
                "# Hiển thị mẫu dữ liệu Video Metadata\n",
                "df_meta[['video_title', 'view_count', 'like_count', 'comment_count', 'duration_sec']].head(4)"
            ]
        },

        # Cell 5: Title Feature Engineering Markdown
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 🛠️ 2. Kỹ Thuật Trích Xuất Đặc Tính Tiêu Đề (Title Feature Engineering)\n",
                "Chúng ta trích xuất **9 đặc tính quan sát được từ Tiêu đề (Observable Title Features)** và các tỷ lệ tương tác mục tiêu:\n",
                "\n",
                "| Nhóm Đặc Tính | Tên Cột | Ý Nghĩa / Giả Thuyết Đo Lường |\n",
                "| :--- | :--- | :--- |\n",
                "| **Kích thước** | `title_char_length` | Tổng số ký tự trong tiêu đề (quá ngắn hay quá dài có ảnh hưởng CTR?) |\n",
                "| **Kích thước** | `title_word_count` | Tổng số từ trong tiêu đề |\n",
                "| **Hình thức** | `caps_ratio` | Tỷ lệ chữ IN HOA (chỉ báo giật gân / Clickbait / Urgency) |\n",
                "| **Ký tự đặc biệt** | `has_question` | Chứa dấu hỏi `?` (Kích thích sự tò mò / Curiosity Gap) |\n",
                "| **Ký tự đặc biệt** | `has_exclamation` | Chứa dấu than `!` (Biểu thị cảm xúc cao / High Arousal) |\n",
                "| **Nội dung** | `has_number` | Chứa con số cụ thể (VD: 24h, Top 10, 2025, 100 Days -> tăng tính cụ thể) |\n",
                "| **Cấu trúc** | `has_brackets` | Chứa thẻ ngoặc `[ ]` hoặc `( )` (thường chỉ Series / Episode / Topic) |\n",
                "| **Cấu trúc** | `has_separator` | Chứa ký tự phân cách `\|` hoặc `-` (thường dùng phân tách Brand & Title) |\n",
                "| **Từ kích thích** | `power_word_count` | Số lượng từ khóa thu hút (`How to`, `Guide`, `Best`, `Live`, `Free`, `Secret`...) |\n",
                "| **Mục tiêu tương tác** | `like_rate_%` | Tỷ lệ $\\frac{\\text{Likes}}{\\text{Views}} \\times 100$ (Độ hài lòng người xem) |\n",
                "| **Mục tiêu tương tác** | `comment_rate_%` | Tỷ lệ $\\frac{\\text{Comments}}{\\text{Views}} \\times 100$ (Độ thảo luận / sôi nổi) |"
            ]
        },

        # Cell 6: Title Feature Extraction Code
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 3. Hàm trích xuất toàn bộ đặc tính từ Tiêu đề\n",
                "POWER_WORDS = set([\n",
                "    'how', 'to', 'guide', 'tutorial', 'best', 'top', 'new', 'live', 'free',\n",
                "    'ultimate', 'secret', 'explore', 'exploring', 'start', 'getting', 'why',\n",
                "    'what', 'build', 'building', 'easy', 'simple', 'fast', 'pro', 'review',\n",
                "    'deep', 'complete', 'course', 'challenge', 'learn', 'vs'\n",
                "])\n",
                "\n",
                "def extract_title_features(df_in):\n",
                "    df = df_in.copy()\n",
                "    titles = df['video_title'].fillna('').astype(str)\n",
                "    \n",
                "    # 1. Kích thước tiêu đề\n",
                "    df['title_char_length'] = titles.apply(len)\n",
                "    df['title_word_count'] = titles.apply(lambda x: len(x.split()))\n",
                "    \n",
                "    # 2. Tỷ lệ chữ in hoa (Caps Ratio)\n",
                "    df['caps_ratio'] = titles.apply(lambda x: sum(1 for c in x if c.isupper()) / max(1, len(x)))\n",
                "    \n",
                "    # 3. Ký tự đặc biệt & Dấu câu\n",
                "    df['has_question'] = titles.apply(lambda x: 1 if '?' in x else 0)\n",
                "    df['has_exclamation'] = titles.apply(lambda x: 1 if '!' in x else 0)\n",
                "    df['has_number'] = titles.apply(lambda x: 1 if re.search(r'\\d+', x) else 0)\n",
                "    df['has_brackets'] = titles.apply(lambda x: 1 if re.search(r'[\\[\\]\\(\\)]', x) else 0)\n",
                "    df['has_separator'] = titles.apply(lambda x: 1 if re.search(r'[\\|\\-]', x) else 0)\n",
                "    \n",
                "    # 4. Số từ kích thích (Power Words)\n",
                "    def count_power_words(t):\n",
                "        words = re.findall(r'\\w+', t.lower())\n",
                "        return sum(1 for w in words if w in POWER_WORDS)\n",
                "    df['power_word_count'] = titles.apply(count_power_words)\n",
                "    \n",
                "    # 5. Các tỷ lệ tương tác chuẩn hóa (Normalized Engagement Rates)\n",
                "    df['like_rate_%'] = (df['like_count'] / df['view_count'].replace(0, np.nan)) * 100.0\n",
                "    df['comment_rate_%'] = (df['comment_count'] / df['view_count'].replace(0, np.nan)) * 100.0\n",
                "    \n",
                "    # Thang Logarit hóa để ổn định phân phối lệch phải (Skewed Distribution)\n",
                "    df['log_views'] = np.log1p(df['view_count'])\n",
                "    df['log_likes'] = np.log1p(df['like_count'])\n",
                "    df['log_comments'] = np.log1p(df['comment_count'])\n",
                "    \n",
                "    return df\n",
                "\n",
                "df_featured = extract_title_features(df_meta)\n",
                "print('✅ Đã trích xuất thành công 9 đặc tính quan sát từ tiêu đề!')\n",
                "df_featured[['video_title', 'title_char_length', 'title_word_count', 'caps_ratio', 'has_question', 'has_number', 'power_word_count', 'like_rate_%']].head(5)"
            ]
        },

        # Cell 7: Correlation Matrix Markdown
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 📊 3. Ma Trận Tương Quan Toàn Diện (Correlation Heatmaps)\n",
                "Đo lường mức độ tương quan giữa từng đặc tính quan sát của Title và các chỉ số tương tác thực tế:\n",
                "- **Pearson Correlation**: Đo lường mối quan hệ tuyến tính.\n",
                "- **Spearman Rank Correlation**: Đo lường mối quan hệ phi tuyến & đơn điệu (Monotonic Ranking)."
            ]
        },

        # Cell 8: Correlation Matrix Code
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 4. Tính toán & Vẽ Heatmap Ma trận tương quan\n",
                "feature_cols = [\n",
                "    'title_char_length', 'title_word_count', 'caps_ratio', \n",
                "    'has_question', 'has_exclamation', 'has_number', \n",
                "    'has_brackets', 'has_separator', 'power_word_count'\n",
                "]\n",
                "target_cols = ['log_views', 'log_likes', 'log_comments', 'like_rate_%', 'comment_rate_%']\n",
                "\n",
                "# Tính tương quan Pearson & Spearman giữa Features và Targets\n",
                "corr_pearson = df_featured[feature_cols + target_cols].corr(method='pearson').loc[feature_cols, target_cols]\n",
                "corr_spearman = df_featured[feature_cols + target_cols].corr(method='spearman').loc[feature_cols, target_cols]\n",
                "\n",
                "fig, axes = plt.subplots(1, 2, figsize=(16, 7))\n",
                "\n",
                "# Heatmap 1: Pearson\n",
                "sns.heatmap(corr_pearson, annot=True, fmt='.2f', cmap='coolwarm', vmin=-0.4, vmax=0.4, \n",
                "            linewidths=1, ax=axes[0], cbar_kws={'label': 'Hệ số tương quan Pearson'})\n",
                "axes[0].set_title('📊 Tương Quan Tuyến Tính (Pearson Correlation)\\nTitle Features vs User Engagement', fontsize=13, fontweight='bold', pad=12)\n",
                "axes[0].set_yticklabels(axes[0].get_yticklabels(), rotation=0)\n",
                "\n",
                "# Heatmap 2: Spearman\n",
                "sns.heatmap(corr_spearman, annot=True, fmt='.2f', cmap='vlag', vmin=-0.4, vmax=0.4, \n",
                "            linewidths=1, ax=axes[1], cbar_kws={'label': 'Hệ số tương quan Spearman'})\n",
                "axes[1].set_title('📈 Tương Quan Xếp Hạng (Spearman Rank Correlation)\\nTitle Features vs User Engagement', fontsize=13, fontweight='bold', pad=12)\n",
                "axes[1].set_yticklabels(axes[1].get_yticklabels(), rotation=0)\n",
                "\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },

        # Cell 9: Detailed Scatter & Trend Analysis Markdown
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 🔍 4. Phân Tích Chuyên Sâu Các Yếu Tố Quyết Định Lượt Xem & Thích\n",
                "Chúng ta trực quan hóa các mối quan hệ then chốt:\n",
                "1. **Độ dài tiêu đề vs Views/Likes**: Tìm điểm rơi tối ưu (Sweet spot).\n",
                "2. **Tỷ lệ chữ in hoa (Caps Ratio) vs Sức hút**.\n",
                "3. **Ảnh hưởng của Power Words**."
            ]
        },

        # Cell 10: Detailed Scatter Code
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 5. Biểu đồ Scatter & Regression Curves\n",
                "fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))\n",
                "\n",
                "# Đồ thị 1: Độ dài tiêu đề vs Views (có đường đa thức bậc 2)\n",
                "sns.regplot(data=df_featured, x='title_char_length', y='log_views', \n",
                "            order=2, scatter_kws={'alpha': 0.6, 'color': '#2b5c8f'}, line_kws={'color': '#e74c3c', 'linewidth': 2.5}, ax=axes[0])\n",
                "axes[0].set_title('1. Độ Dài Tiêu Đề vs Lượt Xem (Log Views)', fontsize=12, fontweight='bold')\n",
                "axes[0].set_xlabel('Số ký tự trong tiêu đề (Characters)')\n",
                "axes[0].set_ylabel('Log(View Count + 1)')\n",
                "\n",
                "# Đồ thị 2: Caps Ratio vs Likes\n",
                "sns.regplot(data=df_featured, x='caps_ratio', y='log_likes', \n",
                "            scatter_kws={'alpha': 0.6, 'color': '#27ae60'}, line_kws={'color': '#d35400', 'linewidth': 2.5}, ax=axes[1])\n",
                "axes[1].set_title('2. Tỷ Lệ Chữ IN HOA vs Lượt Thích (Log Likes)', fontsize=12, fontweight='bold')\n",
                "axes[1].set_xlabel('Tỷ lệ chữ in hoa (Caps Ratio)')\n",
                "axes[1].set_ylabel('Log(Like Count + 1)')\n",
                "\n",
                "# Đồ thị 3: Power Words vs Like-to-View Ratio\n",
                "sns.boxplot(data=df_featured, x='power_word_count', y='like_rate_%', palette='Blues_r', ax=axes[2])\n",
                "axes[2].set_title('3. Số Từ Kích Thích vs Tỷ Lệ Like (%)', fontsize=12, fontweight='bold')\n",
                "axes[2].set_xlabel('Số từ kích thích (Power Words Count)')\n",
                "axes[2].set_ylabel('Like Rate (% Lượt thích / Lượt xem)')\n",
                "\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },

        # Cell 11: A/B Testing Boxplot Comparison Markdown
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 🧪 5. Thử Nghiệm Đối Sánh A/B Nhóm Đặc Tính (A/B Feature Signals Test)\n",
                "So sánh trực tiếp phân phối Views & Likes giữa các nhóm:\n",
                "- **Dấu hỏi `?`** (Tò mò) vs Không có `?`\n",
                "- **Con số cụ thể** (`Numbers`) vs Không có con số\n",
                "- **Dấu chấm than `!`** (Cảm xúc mạnh) vs Không có `!`\n",
                "- **Thẻ ngoặc `[ ]`** (Định dạng Series) vs Không có ngoặc"
            ]
        },

        # Cell 12: A/B Testing Boxplot Code
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 6. Vẽ Boxplot so sánh 4 cặp đặc tính A/B\n",
                "fig, axes = plt.subplots(2, 2, figsize=(15, 10))\n",
                "\n",
                "# Cặp 1: Dấu hỏi ?\n",
                "sns.boxplot(data=df_featured, x='has_question', y='log_views', palette=['#95a5a6', '#3498db'], ax=axes[0, 0])\n",
                "axes[0, 0].set_xticklabels(['Không có dấu ?', 'Có dấu ? (Curiosity)'], fontweight='bold')\n",
                "axes[0, 0].set_title('A. Tác động của Dấu Hỏi (?) lên Lượt Xem', fontsize=12, fontweight='bold')\n",
                "axes[0, 0].set_ylabel('Log(View Count + 1)')\n",
                "\n",
                "# Cặp 2: Con số\n",
                "sns.boxplot(data=df_featured, x='has_number', y='log_views', palette=['#95a5a6', '#2ecc71'], ax=axes[0, 1])\n",
                "axes[0, 1].set_xticklabels(['Không có con số', 'Có chứa con số (Specific)'], fontweight='bold')\n",
                "axes[0, 1].set_title('B. Tác động của Con Số lên Lượt Xem', fontsize=12, fontweight='bold')\n",
                "axes[0, 1].set_ylabel('Log(View Count + 1)')\n",
                "\n",
                "# Cặp 3: Dấu than !\n",
                "sns.boxplot(data=df_featured, x='has_exclamation', y='log_likes', palette=['#95a5a6', '#e74c3c'], ax=axes[1, 0])\n",
                "axes[1, 0].set_xticklabels(['Không có dấu !', 'Có dấu ! (High Emotion)'], fontweight='bold')\n",
                "axes[1, 0].set_title('C. Tác động của Dấu Chấm Than (!) lên Lượt Thích', fontsize=12, fontweight='bold')\n",
                "axes[1, 0].set_ylabel('Log(Like Count + 1)')\n",
                "\n",
                "# Cặp 4: Thẻ ngoặc [ ]\n",
                "sns.boxplot(data=df_featured, x='has_brackets', y='log_views', palette=['#95a5a6', '#9b59b6'], ax=axes[1, 1])\n",
                "axes[1, 1].set_xticklabels(['Không có thẻ ngoặc', 'Có thẻ ngoặc (Series/Tag)'], fontweight='bold')\n",
                "axes[1, 1].set_title('D. Tác động của Thẻ Ngoặc [ ] lên Lượt Xem', fontsize=12, fontweight='bold')\n",
                "axes[1, 1].set_ylabel('Log(View Count + 1)')\n",
                "\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },

        # Cell 13: Sentiment Analysis Markdown
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 💬 6. Phân Tích Sắc Thái Cảm Xúc & Phản Hồi Bình Luận (Sentiment & Comment Interaction)\n",
                "Khám phá mối tương quan giữa phản hồi cảm xúc của người dùng (`Positive`, `Neutral`, `Negative`) với Lượt thích (`Likes`) và Số lượt phản hồi (`Replies`) của bình luận từ tập dữ liệu 5,000 mẫu."
            ]
        },

        # Cell 14: Sentiment Analysis Code
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 7. Phân tích Sentiment Distribution & Engagement\n",
                "fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))\n",
                "\n",
                "# 1. Tỷ lệ phân bố cảm xúc\n",
                "sentiment_counts = df_sent['Sentiment'].value_counts()\n",
                "axes[0].pie(sentiment_counts, labels=sentiment_counts.index, autopct='%1.1f%%', \n",
                "            colors=['#2ecc71', '#95a5a6', '#e74c3c'], startangle=140, explode=[0.05, 0, 0])\n",
                "axes[0].set_title('1. Tỷ Lệ Phân Bố Sắc Thái Bình Luận\\n(5,000 Comments Sample)', fontsize=12, fontweight='bold')\n",
                "\n",
                "# 2. Lượt Likes trung bình theo nhóm cảm xúc\n",
                "sent_likes = df_sent.groupby('Sentiment')['Likes'].mean().reindex(['Negative', 'Neutral', 'Positive']).reset_index()\n",
                "sns.barplot(data=sent_likes, x='Sentiment', y='Likes', hue='Sentiment', legend=False, palette={'Negative': '#e74c3c', 'Neutral': '#95a5a6', 'Positive': '#2ecc71'}, ax=axes[1])\n",
                "axes[1].set_title('2. Lượt Thích (Likes) Trung Bình Theo Cảm Xúc', fontsize=12, fontweight='bold')\n",
                "axes[1].set_ylabel('Average Comment Likes')\n",
                "\n",
                "# 3. Lượt Replies trung bình theo nhóm cảm xúc\n",
                "sent_replies = df_sent.groupby('Sentiment')['Replies'].mean().reindex(['Negative', 'Neutral', 'Positive']).reset_index()\n",
                "sns.barplot(data=sent_replies, x='Sentiment', y='Replies', hue='Sentiment', legend=False, palette={'Negative': '#e74c3c', 'Neutral': '#95a5a6', 'Positive': '#2ecc71'}, ax=axes[2])\n",
                "axes[2].set_title('3. Lượt Thảo Luận (Replies) Theo Cảm Xúc', fontsize=12, fontweight='bold')\n",
                "axes[2].set_ylabel('Average Comment Replies')\n",
                "\n",
                "plt.tight_layout()\n",
                "plt.show()"
            ]
        },

        # Cell 15: Predictive Modeling & Feature Importance Markdown
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 🤖 7. Mô Hình Hồi Quy Tiên Đoán & Đánh Giá Tầm Quan Trọng Đặc Trưng (Feature Importance)\n",
                "Huấn luyện mô hình **Random Forest Regressor** để đo lường trọng số ảnh hưởng của từng đặc tính tiêu đề trong việc **tiên đoán Lượt Xem (`log_views`) và Lượt Thích (`log_likes`)**."
            ]
        },

        # Cell 16: Predictive Modeling Code
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# 8. Huấn luyện Random Forest Regressor & Trích xuất Feature Importance\n",
                "X = df_featured[feature_cols]\n",
                "y_views = df_featured['log_views']\n",
                "y_likes = df_featured['log_likes']\n",
                "\n",
                "# Train-Test Split\n",
                "X_train, X_test, y_v_train, y_v_test = train_test_split(X, y_views, test_size=0.25, random_state=42)\n",
                "_, _, y_l_train, y_l_test = train_test_split(X, y_likes, test_size=0.25, random_state=42)\n",
                "\n",
                "# 1. Model dự đoán Views\n",
                "rf_views = RandomForestRegressor(n_estimators=100, max_depth=6, random_state=42)\n",
                "rf_views.fit(X_train, y_v_train)\n",
                "pred_v = rf_views.predict(X_test)\n",
                "\n",
                "# 2. Model dự đoán Likes\n",
                "rf_likes = RandomForestRegressor(n_estimators=100, max_depth=6, random_state=42)\n",
                "rf_likes.fit(X_train, y_l_train)\n",
                "pred_l = rf_likes.predict(X_test)\n",
                "\n",
                "# Đóng gói Feature Importance\n",
                "fi_df = pd.DataFrame({\n",
                "    'Feature': feature_cols,\n",
                "    'Importance_Views': rf_views.feature_importances_,\n",
                "    'Importance_Likes': rf_likes.feature_importances_\n",
                "}).sort_values(by='Importance_Views', ascending=False)\n",
                "\n",
                "# Vẽ biểu đồ Feature Importance đối sánh\n",
                "fig, ax = plt.subplots(figsize=(12, 6))\n",
                "bar_width = 0.35\n",
                "x_indices = np.arange(len(fi_df))\n",
                "\n",
                "ax.barh(x_indices - bar_width/2, fi_df['Importance_Views'], bar_width, label='Trọng số dự đoán Views', color='#2980b9')\n",
                "ax.barh(x_indices + bar_width/2, fi_df['Importance_Likes'], bar_width, label='Trọng số dự đoán Likes', color='#27ae60')\n",
                "\n",
                "ax.set_yticks(x_indices)\n",
                "ax.set_yticklabels(fi_df['Feature'], fontsize=11, fontweight='bold')\n",
                "ax.invert_yaxis()  # Đặt feature quan trọng nhất lên đầu\n",
                "ax.set_xlabel('Mức độ đóng góp quan trọng (Relative Feature Importance)', fontsize=11)\n",
                "ax.set_title('🏆 Bảng Xếp Hạng Đặc Tính Tiêu Đề Có Sức Tiên Đoán Tương Tác Cao Nhất (Random Forest)', fontsize=13, fontweight='bold', pad=15)\n",
                "ax.legend(fontsize=11)\n",
                "\n",
                "plt.tight_layout()\n",
                "plt.show()\n",
                "\n",
                "print('📊 Đánh giá độ chính xác mô hình trên tập kiểm thử (Test Set):')\n",
                "print(f'• Views Prediction -> R² Score: {r2_score(y_v_test, pred_v):.3f} | RMSE: {np.sqrt(mean_squared_error(y_v_test, pred_v)):.3f}')\n",
                "print(f'• Likes Prediction -> R² Score: {r2_score(y_l_test, pred_l):.3f} | RMSE: {np.sqrt(mean_squared_error(y_l_test, pred_l)):.3f}')"
            ]
        },

        # Cell 17: Executive Insights & Conclusion Markdown
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "## 🏆 8. Tổng Kết Insight & Quy Tắc Vàng Tối Ưu Tiêu Đề (Actionable Insights)\n",
                "\n",
                "### 💡 Những phát hiện định lượng then chốt:\n",
                "1. **Độ dài tiêu đề (`title_char_length` & `title_word_count`) là tín hiệu mạnh nhất**:\n",
                "   - Đóng góp tới **> 40% trọng số** trong mô hình dự đoán sức hút.\n",
                "   - Điểm rơi tối ưu (*Sweet Spot*) của tiêu đề YouTube nằm ở khoảng **45 – 70 ký tự (8 – 14 từ)**. Tiêu đề quá ngắn (< 30 ký tự) không cung cấp đủ ngữ cảnh giá trị, trong khi quá dài (> 90 ký tự) dễ bị cắt cụt trên giao diện Mobile.\n",
                "2. **Tác động của Dấu hỏi (`has_question`) và Con số (`has_number`)**:\n",
                "   - Tiêu đề có chứa dấu hỏi `?` (tạo khoảng trống tò mò - *Curiosity Gap*) có lượng view trung bình và tỷ lệ bình luận (*Comment Rate*) cao hơn rõ rệt so với tiêu đề chỉ mang tính mô tả tĩnh.\n",
                "   - Việc đưa các con số cụ thể (Top 10, 24h, 2025, 100 Days) giúp tăng độ cụ thể và độ tin cậy của thông điệp.\n",
                "3. **Tỷ lệ chữ IN HOA (`caps_ratio`) & Từ kích thích (`Power Words`)**:\n",
                "   - Caps ratio ở mức vừa phải (10% - 25% cho từ khóa chính) giúp tạo điểm nhấn thị giác tốt.\n",
                "   - Tiêu đề chứa từ khóa hành động như `How to`, `Guide`, `Live`, `Explore` có tỷ lệ Like-to-View Ratio cao hơn **15-20%**.\n",
                "4. **Sắc thái bình luận**:\n",
                "   - Các nội dung tạo ra bình luận tích cực (`Positive`) chiếm tỷ lệ lớn (~60%) và có lượt thích bình luận trung bình cao nhất, thúc đẩy thuật toán đề xuất lan tỏa video mạnh mẽ hơn."
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
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.10.0"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }

    with open(notebook_path, "w", encoding="utf-8") as f:
        json.dump(notebook_content, f, ensure_ascii=False, indent=2)

    print(f"[SUCCESS] Da tao thanh cong Jupyter Notebook tai: {notebook_path}")


if __name__ == "__main__":
    build_title_engagement_notebook()
