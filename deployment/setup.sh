#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# JARVIS — Linux/macOS Setup Script
# Run from the project root: bash deployment/setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

echo ""
echo " ██████╗██╗   ██╗██████╗ ██╗   ██╗███████╗"
echo "██╔════╝╚██╗ ██╔╝██╔══██╗██║   ██║██╔════╝"
echo "██║      ╚████╔╝ ██████╔╝██║   ██║███████╗"
echo "██║       ╚██╔╝  ██╔══██╗██║   ██║╚════██║"
echo "╚██████╗   ██║   ██║  ██║╚██████╔╝███████║"
echo " ╚═════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
echo ""
echo " Cognitive sYstem for Real-time Utility and Services"
echo " Phase 1 — Setup"
echo ""

# ── Move to project root ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
echo "[INFO] Working directory: $PROJECT_ROOT"

# ── Python check ─────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found. Install Python 3.11+ and retry."
    exit 1
fi
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[INFO] Python $PYTHON_VERSION detected"

# ── Virtual environment ───────────────────────────────────────────────────────
if [ ! -d venv ]; then
    echo "[INFO] Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip --quiet

# ── System deps (Debian/Ubuntu) ───────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
    echo "[INFO] Installing system dependencies (requires sudo)..."
    sudo apt-get update -qq
    sudo apt-get install -y --no-install-recommends \
        portaudio19-dev \
        espeak-ng \
        ffmpeg \
        libsndfile1
fi

# ── Python packages ───────────────────────────────────────────────────────────
echo "[INFO] Installing Python dependencies..."
pip install -r requirements.txt

# ── Environment file ─────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    cp config/.env.example .env
    echo "[INFO] Created .env from template — add your CLAUDE_API_KEY if using HYBRID mode"
fi

# ── Log directory ─────────────────────────────────────────────────────────────
mkdir -p logs

# ── Frontend ─────────────────────────────────────────────────────────────────
if command -v npm &>/dev/null; then
    echo "[INFO] Installing frontend dependencies..."
    (cd frontend && npm install)
else
    echo "[WARNING] npm not found — skip frontend install (needs Node.js 18+)"
fi

echo ""
echo "─────────────────────────────────────────────────────"
echo " Setup complete!"
echo ""
echo " To start JARVIS:"
echo ""
echo "   1. Activate venv:    source venv/bin/activate"
echo "   2. Start Ollama:     ollama serve           (new terminal)"
echo "   3. Start backend:    python -m backend.core.cyrus_engine"
echo "   4. Start frontend:   cd frontend && npm run dev"
echo ""
echo ' Then say "Hola JARVIS" into your microphone.'
echo "─────────────────────────────────────────────────────"
