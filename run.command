#!/bin/bash
# ==============================================================================
# run.command — Double-Click 1-Click Launcher for macOS
# ==============================================================================

# 1. Chuyển đến thư mục chứa file script
cd "$(dirname "$0")" || exit 1

# Vô hiệu hóa file rác AppleDouble trên drive mạng/ngoài
export COPYFILE_DISABLE=1
find . -name "._*" -delete 2>/dev/null || true

echo "========================================================================"
echo "      🚀 AI LIVESTREAM FINDER & AGENT EVALUATOR (macOS Launcher)"
echo "========================================================================"
echo ""

# 2. Kiểm tra Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ [LỖI] Không tìm thấy python3 trên máy tính của bạn!"
    echo "   Vui lòng tải và cài đặt Python 3 từ: https://www.python.org/downloads/"
    echo ""
    read -p "Nhấn Enter để thoát..."
    exit 1
fi

# 3. Chọn thư mục môi trường ảo
VENV_DIR=".venv_mac"
if [ ! -d "$VENV_DIR" ] && [ -d ".venv" ]; then
    VENV_DIR=".venv"
fi

# Tạo môi trường ảo nếu chưa có
if [ ! -d "$VENV_DIR" ]; then
    echo "⚙️ [THÔNG BÁO] Đang khởi tạo môi trường ảo $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

# 4. Kiểm tra và cài đặt thư viện phụ thuộc
if [ ! -f "$VENV_DIR/.installed" ]; then
    echo "📦 [THÔNG BÁO] Đang cài đặt thư viện và trình duyệt Playwright Chromium..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r requirements.txt
    "$VENV_DIR/bin/python" -m playwright install chromium
    touch "$VENV_DIR/.installed"
    echo "✅ [HOÀN TẤT] Đã cài đặt xong tất cả thư viện cần thiết!"
    echo ""
fi

# 5. Kiểm tra file .env
if [ ! -f ".env" ]; then
    echo "⚠️ [CẢNH BÁO] Chưa có file .env. Đang tạo file mẫu..."
    cat <<EOT > .env
GEMINI_API_KEY=
GROQ_API_KEY=
OPENAI_API_KEY=
YOUTUBE_API_KEY=
BROWSER_PROFILE_DIR=data/browser_profile
EOT
    echo "📝 [HƯỚNG DẪN] Vui lòng điền API Key vào file .env nếu cần dùng thêm LLM ngoài!"
    echo ""
fi

# 6. Khởi chạy Streamlit Dashboard
echo "========================================================================"
echo "🎯 Đang khởi chạy giao diện Web Dashboard trên trình duyệt..."
echo "========================================================================"
echo ""

# Tự động mở trình duyệt sau 1.5 giây
(sleep 1.5 && open "http://localhost:8501/" 2>/dev/null) &

# Chạy ứng dụng Streamlit
"$VENV_DIR/bin/streamlit" run dashboard/streamlit_app.py

echo ""
read -p "Nhấn Enter để đóng cửa sổ..."
