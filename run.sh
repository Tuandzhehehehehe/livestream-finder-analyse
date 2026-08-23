#!/usr/bin/env bash
cd "$(dirname "$0")"
export COPYFILE_DISABLE=1
find .venv_mac -name "._*" -delete 2>/dev/null || true

echo "========================================================="
echo "      HE THONG TIM KIEM VA DANH GIA LIVESTREAM (macOS)"
echo "========================================================="
echo ""

# 1. Kiem tra Python
if ! command -v python3 &> /dev/null; then
    echo "[LOI] Khong tim thay python3 tren Mac cua ban!"
    exit 1
fi

VENV_DIR=".venv_mac"

# 2. Kiem tra va tao moi truong ao .venv_mac
if [ ! -d "$VENV_DIR" ]; then
    echo "[THONG BAO] Dang tao moi truong ao $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

# 3. Kiem tra & cai dat requirements
if [ ! -f "$VENV_DIR/.installed" ]; then
    echo "[THONG BAO] Dang cai dat thu vien va Playwright Chromium..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r requirements.txt
    "$VENV_DIR/bin/python" -m playwright install chromium
    touch "$VENV_DIR/.installed"
    echo "[THANH CONG] Da cai dat xong tat ca thu vien!"
    echo ""
fi

# 4. Kiem tra file .env
if [ ! -f ".env" ]; then
    echo "[CANH BAO] Dang tao file .env mau..."
    cat <<EOT > .env
GEMINI_API_KEY=
GROQ_API_KEY=
OPENAI_API_KEY=
YOUTUBE_API_KEY=
BROWSER_PROFILE_DIR=data/browser_profile
EOT
    echo "[HUONG DAN] Vui long mo file .env va dien API Key truoc khi su dung!"
    echo ""
fi

# 5. Khoi chay Streamlit
echo "[THANH CONG] Dang khoi chay giao dien Web Dashboard..."
open "http://localhost:8501/" 2>/dev/null || true
"$VENV_DIR/bin/streamlit" run dashboard/streamlit_app.py
