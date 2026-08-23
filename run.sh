#!/usr/bin/env bash
# ==============================================================================
# run.sh — Universal Launcher for macOS & Linux
# ==============================================================================
cd "$(dirname "$0")" || exit 1
export COPYFILE_DISABLE=1
find . -name "._*" -delete 2>/dev/null || true

echo "========================================================="
echo "      🚀 AI LIVESTREAM FINDER & AGENT EVALUATOR"
echo "========================================================="
echo ""

# 1. Kiem tra Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ [LOI] Khong tim thay python3 tren he thong cua ban!"
    echo "   Vui long cai dat Python 3 tu https://www.python.org/downloads/"
    exit 1
fi

VENV_DIR=".venv_mac"
if [ -f ".venv/bin/python3" ] || [ -f ".venv/bin/python" ]; then
    VENV_DIR=".venv"
fi

# 2. Kiem tra va tao moi truong ao
if [ ! -f "$VENV_DIR/bin/python" ] && [ ! -f "$VENV_DIR/bin/python3" ]; then
    echo "⚙️ [THONG BAO] Dang tao moi truong ao $VENV_DIR..."
    rm -rf "$VENV_DIR" 2>/dev/null || true
    python3 -m venv "$VENV_DIR"
fi

# 3. Kiem tra & cai dat requirements
if [ ! -f "$VENV_DIR/.installed" ]; then
    echo "📦 [THONG BAO] Dang cai dat thu vien va Playwright Chromium..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r requirements.txt
    "$VENV_DIR/bin/python" -m playwright install chromium
    touch "$VENV_DIR/.installed"
    echo "✅ [THANH CONG] Da cai dat xong tat ca thu vien!"
    echo ""
fi

# 4. Kiem tra file .env
if [ ! -f ".env" ]; then
    echo "⚠️ [CANH BAO] Dang tao file .env mau..."
    cat <<EOT > .env
GEMINI_API_KEY=
GROQ_API_KEY=
OPENAI_API_KEY=
YOUTUBE_API_KEY=
BROWSER_PROFILE_DIR=data/browser_profile
EOT
    echo "📝 [HUONG DAN] Vui long mo file .env va dien API Key neu can dung LLM ngoai!"
    echo ""
fi

# 5. Khoi chay Streamlit
echo "🎯 [THANH CONG] Dang khoi chay giao dien Web Dashboard..."
(sleep 1.5 && (open "http://localhost:8501/" 2>/dev/null || xdg-open "http://localhost:8501/" 2>/dev/null)) &
"$VENV_DIR/bin/streamlit" run dashboard/streamlit_app.py
