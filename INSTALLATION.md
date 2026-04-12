# C.Y.R.U.S — Installation Guide

**Cognitive sYstem for Real-time Utility & Services — Phase 1**

---

## Prerequisites

### Required

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11.x | Do **not** use 3.12+ (package compatibility) |
| Node.js | 18+ | For the React frontend |
| npm | 9+ | Bundled with Node.js |
| Ollama | latest | Local LLM inference |
| espeak-ng | any | Required by Kokoro TTS |

### Hardware

- Microphone (USB recommended)
- Speaker or headphones
- NVIDIA GPU with CUDA support (for Whisper ASR acceleration)
  - RTX 2070S or better recommended
  - CPU fallback available (slower)

---

## Step 1 — Install System Dependencies

### Python 3.11

Download from [python.org](https://python.org). During installation:
- Check **"Add Python to PATH"**
- Check **"Install for all users"** (optional)

Verify:
```bat
py -3.11 --version
```

### Node.js 18+

Download from [nodejs.org](https://nodejs.org). Choose the LTS release.

Verify:
```bat
node --version
npm --version
```

### Ollama

Download from [ollama.ai](https://ollama.ai). After installation:

```bat
ollama serve
```

Then pull the Mistral model (in a separate terminal):
```bat
ollama pull mistral:latest
```

This downloads ~4GB. Run it once and Ollama caches it permanently.

### espeak-ng (for Kokoro TTS)

Download the Windows installer from the
[espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases).

After installation, ensure it is on your PATH:
```bat
espeak-ng --version
```

---

## Step 2 — Clone / Copy Project Files

If using Git:
```bat
git clone <your-repo-url> C:\C.Y.R.U.S
cd C:\C.Y.R.U.S
```

Or extract the project archive to `C:\C.Y.R.U.S`.

---

## Step 3 — Backend Setup

Run the automated setup script **from the project root**:

```bat
deployment\setup.bat
```

This script:
1. Creates a Python 3.11 virtual environment (`venv/`)
2. Installs all Python dependencies from `requirements.txt`
3. Copies `.env` from the template
4. Creates the `logs/` directory
5. Installs frontend Node.js dependencies

### Manual setup (alternative)

```bat
:: Create venv with Python 3.11
py -3.11 -m venv venv

:: Activate
venv\Scripts\activate

:: Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Step 4 — Configure Environment

Copy the environment template:
```bat
copy config\.env.example .env
```

Edit `.env` and fill in your values:

```dotenv
# Required only for HYBRID mode (API fallback)
CLAUDE_API_KEY=sk-ant-...

# Optional — override defaults
CYRUS_LOG_LEVEL=INFO
OLLAMA_HOST=http://localhost:11434
```

> **Note:** In `LOCAL` mode (default), no API keys are required.
> C.Y.R.U.S runs 100% offline.

---

## Step 5 — Frontend Setup

```bat
cd frontend
npm install
cd ..
```

---

## Step 6 — Verify Installation

Run the test suite to confirm everything is working:

```bat
venv\Scripts\activate
pytest tests/ -v
```

Expected output:
```
46 passed, 6 skipped
```

The 6 skipped tests require actual hardware (GPU, microphone) and are normal.

---

## Step 7 — Start C.Y.R.U.S

You need **3 terminals**:

### Terminal 1 — Ollama (if not already running)
```bat
ollama serve
```

### Terminal 2 — Backend
```bat
venv\Scripts\activate
python -m backend.core.cyrus_engine
```

You should see:
```
[C.Y.R.U.S] COGNITIVE SYSTEM v1.0 — STARTING
[C.Y.R.U.S] Mode: LOCAL
[C.Y.R.U.S] Loading Whisper ASR model…
[C.Y.R.U.S] Checking Ollama availability…
[C.Y.R.U.S] Ollama is online
[C.Y.R.U.S] Starting… Say 'Hola C.Y.R.U.S' or 'Hey C.Y.R.U.S'
```

### Terminal 3 — Frontend
```bat
cd frontend
npm run dev
```

Open your browser at **http://localhost:5173**

---

## Troubleshooting

### PyAudio fails to install
```
error: Microsoft Visual C++ 14.0 is required
```
Install [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).

### webrtcvad fails to install
Same solution as PyAudio — requires C++ Build Tools.

### Ollama not responding
```
[C.Y.R.U.S] Ollama not responding — API fallback will be used
```
- Ensure `ollama serve` is running in another terminal
- Check `http://localhost:11434` is accessible
- In `config/config.yaml`, `mode` can be set to `HYBRID` to use Claude API as fallback

### Whisper loads on CPU (slow)
- CUDA is not available or GPU VRAM is insufficient
- In `config/config.yaml`, change `asr.device` to `"cpu"` explicitly
- CPU inference is ~5× slower but still functional

### kokoro not installed / TTS silent
```
[C.Y.R.U.S] kokoro package not installed; local TTS unavailable
```
Install espeak-ng first, then:
```bat
pip install kokoro
```

### edge-tts fallback not available
```
[C.Y.R.U.S] edge-tts not installed; API TTS fallback unavailable
```
```bat
pip install edge-tts
```
edge-tts is free and requires no API key — it uses Microsoft Azure TTS via the browser API.

---

## GPU Memory Reference (RTX 2070S)

| State | VRAM used |
|-------|-----------|
| Idle (Ollama daemon) | ~2.0 GB |
| Whisper TINY active | +1.5 GB |
| Mistral 7B inference | +2.5 GB |
| **Peak** | **~4.0 GB** |

Safe margin: 4 GB remaining out of 8 GB total.

---

## Project Structure

```
C.Y.R.U.S/
├── backend/           Python backend (audio, ASR, LLM, TTS, WebSocket)
├── frontend/          React frontend (hologram UI, transcript)
├── config/            YAML configuration + soul.md personality
├── deployment/        Docker Compose, Dockerfiles, setup scripts
├── tests/             pytest test suite
├── logs/              Runtime logs (auto-created)
└── venv/              Python virtual environment (auto-created)
```

---

*For a 5-minute quick start, see [QUICK_START.md](QUICK_START.md).*
