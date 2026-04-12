# C.Y.R.U.S — Quick Start (5 minutes)

> Assumes Python 3.11, Node.js 18+, and Ollama are already installed.
> For fresh installs see [INSTALLATION.md](INSTALLATION.md).

---

## 1. Set up the environment (1 min)

```bat
cd C:\C.Y.R.U.S

:: Create venv with Python 3.11
py -3.11 -m venv venv
venv\Scripts\activate

:: Install Python dependencies
pip install -r requirements.txt

:: Copy environment template
copy config\.env.example .env
```

---

## 2. Pull the LLM model (3 min, one-time)

```bat
ollama pull mistral:latest
```

---

## 3. Start everything

Open **3 terminals** in `C:\C.Y.R.U.S`:

**Terminal 1 — Ollama**
```bat
ollama serve
```

**Terminal 2 — Backend**
```bat
venv\Scripts\activate
python -m backend.core.cyrus_engine
```

**Terminal 3 — Frontend**
```bat
cd frontend
npm install
npm run dev
```

---

## 4. Open the UI

Go to **http://localhost:5173** in your browser.

---

## 5. Talk to C.Y.R.U.S

Say one of these wake words into your microphone:

- **"Hola C.Y.R.U.S, ¿qué hora es?"**
- **"Hey Cyrus, what time is it?"**
- **"Oye Cyrus, enciende las luces"**

You should hear a response in British English within ~2–4 seconds.

---

## What to expect

```
[C.Y.R.U.S] COGNITIVE SYSTEM v1.0 — STARTING
[C.Y.R.U.S] Mode: LOCAL
[C.Y.R.U.S] Loading Whisper ASR model…
[C.Y.R.U.S] Ollama is online
[C.Y.R.U.S] Starting… Say 'Hola C.Y.R.U.S' or 'Hey C.Y.R.U.S'
[C.Y.R.U.S] Transcript: 'Hola C.Y.R.U.S, ¿qué hora es?' [es]
[C.Y.R.U.S] Trigger detected: 'hola cyrus'
[C.Y.R.U.S] Response: 'It's currently 14:35. How else may I assist you?'
```

---

## Something not working?

| Problem | Fix |
|---------|-----|
| No audio response | Install `espeak-ng` then `pip install kokoro` |
| Ollama offline warning | Run `ollama serve` in a terminal |
| Whisper loading on CPU | Normal if no CUDA — just slower (~2s extra) |
| Port 5173 not found | Run `npm run dev` in the `frontend/` folder |
| Tests failing | Run `pytest tests/ -v` to see details |

Full details in [INSTALLATION.md](INSTALLATION.md).
