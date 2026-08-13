#!/usr/bin/env bash
set -e

echo ""
echo "   ___         __       ________      "
echo "  / _ | __ __/ /____  / ___/ (_)____ "
echo " / __ |/ // / __/ _ \/ /__/ / / __/ "
echo "/_/ |_|\_,_/\__/\___/\___/_/_/\__/  "
echo ""
echo " AutoClip Setup Script"
echo " ====================="
echo ""

# ── Check Python ──────────────────────────────────────────────────────────────
echo "[1/4] Checking Python version..."

if ! command -v python3 &>/dev/null; then
    echo ""
    echo " [ERROR] Python 3 not found!"
    echo " Install from: https://python.org/downloads"
    echo " Or via package manager:"
    echo "   macOS:  brew install python"
    echo "   Ubuntu: sudo apt install python3 python3-venv"
    exit 1
fi

PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJOR=$(echo "$PYVER" | cut -d. -f1)
PYMINOR=$(echo "$PYVER" | cut -d. -f2)

if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 10 ]; }; then
    echo " [ERROR] Python 3.10+ required, found $PYVER"
    exit 1
fi

echo " [OK] Python $PYVER found."
echo ""

# ── Create virtual environment ────────────────────────────────────────────────
echo "[2/4] Creating virtual environment in .venv/ ..."

if [ -d ".venv" ]; then
    echo " [INFO] .venv already exists, skipping creation."
else
    python3 -m venv .venv
    echo " [OK] Virtual environment created."
fi
echo ""

# ── Install dependencies ──────────────────────────────────────────────────────
echo "[3/4] Installing dependencies (this may take a few minutes)..."
echo " Installing PyTorch CPU + Whisper + all dependencies..."
echo ""

.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt --quiet

echo " [OK] All dependencies installed."
echo ""

# ── Create launcher ───────────────────────────────────────────────────────────
echo "[4/4] Creating autoclip launcher..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat > autoclip.sh << EOF
#!/usr/bin/env bash
export PYTHONUTF8=1
export PYTHONPATH="$SCRIPT_DIR"
"$SCRIPT_DIR/.venv/bin/python" -m autoclip "\$@"
EOF

chmod +x autoclip.sh

# Optionally create a symlink as 'autoclip' in the project root
if [ ! -f autoclip ] || [ -L autoclip ]; then
    ln -sf autoclip.sh autoclip
    chmod +x autoclip
fi

echo " [OK] Launcher created: ./autoclip"
echo ""

# ── Done ─────────────────────────────────────────────────────────────────────
echo "============================================================"
echo " Setup complete!"
echo ""
echo " To get started, run:"
echo ""
echo "   ./autoclip"
echo ""
echo " Requirements:"
echo "   - FFmpeg  : https://ffmpeg.org/download.html"
echo "     macOS:  brew install ffmpeg"
echo "     Ubuntu: sudo apt install ffmpeg"
echo ""
echo "   - Ollama  : https://ollama.ai  (optional, for AI analysis)"
echo "     then run: ollama pull llama3"
echo ""
echo "============================================================"
echo ""
