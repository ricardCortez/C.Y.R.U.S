# C.Y.R.U.S — Cognitive sYstem for Real-time Utility & Services

> A local-first, voice-driven AI assistant for your homelab. JARVIS-style neural hologram UI, Spanish voice, Piper TTS, semantic memory, and multi-provider LLM support.

---

## Quick Start

```bat
# 1. Activate environment
venv\Scripts\activate

# 2. Start Ollama
ollama serve

# 3. Start backend
python -m backend.core.cyrus_engine

# 4. Start frontend (separate terminal)
cd frontend && npm run dev
# → http://localhost:5173
```

Say **"Hola CYRUS"** or **"Hey Jarvis"** to activate.

> **Note:** The microphone only activates once the web UI is open and connected. Running the backend alone keeps the mic silent.

---

## Architecture

```
Browser UI (React + Three.js)
        ↕  WebSocket :8765
┌─────────────────────────────────────┐
│  CYRUSEngine                        │
│  ┌──────────┐  ┌─────────────────┐  │
│  │ AudioIn  │  │   EventBus      │  │
│  │ WASAPI   │  │   (async)       │  │
│  │ VAD+Gate │  └─────────────────┘  │
│  └────┬─────┘           ↑           │
│       │          ┌──────┴───────┐   │
│  Whisper ASR     │  WebSocket   │   │
│       │          │  Server      │   │
│  TriggerDetect   └──────────────┘   │
│       │                             │
│  LLMManager                        │
│   ├─ Ollama (local)                 │
│   ├─ OpenAI / ChatGPT               │
│   ├─ Anthropic (Claude)             │
│   ├─ Groq (Llama / Mixtral)         │
│   └─ Google Gemini                  │
│       │  dual output                │
│  DISPLAY text ──→ WebSocket UI      │
│  SPEECH text  ──→ TTSManager        │
│                   Piper → WAV       │
│                   Kokoro fallback   │
│                   Edge-TTS fallback │
│       ↓                             │
│  AudioOutput (speakers)             │
│  MemoryManager                      │
│   Qdrant (vectors) + SQLite         │
└─────────────────────────────────────┘
```

---

## Features

| Feature | Status |
|---------|--------|
| Wake word detection (fuzzy) | ✅ |
| Echo cancellation (state gate + mute window) | ✅ |
| Whisper ASR (faster-whisper) | ✅ |
| Ollama LLM (local, any model) | ✅ |
| OpenAI API (GPT-4o, GPT-4o-mini, etc.) | ✅ |
| Anthropic API (Claude Opus/Sonnet/Haiku) | ✅ |
| Groq API (Llama 3.3, Mixtral, Gemma) | ✅ |
| Google Gemini API | ✅ |
| LLM provider selector in UI (LOCAL / API) | ✅ |
| API connectivity test from UI | ✅ |
| Piper TTS (es_MX, offline, fast) | ✅ |
| Kokoro TTS fallback | ✅ |
| Edge-TTS fallback | ✅ |
| Dual DISPLAY/SPEECH output | ✅ |
| Semantic memory (Qdrant + SQLite) | ✅ |
| Neural mesh hologram (Three.js) | ✅ |
| Real system stats (CPU/GPU/VRAM) | ✅ |
| Speaker recognition (ECAPA-TDNN) | ✅ |
| Voice enrollment (custom wake words) | ✅ |
| Control panel (config, logs, history) | ✅ |
| Home Assistant integration | ✅ |
| Task planner (voice commands) | ✅ |
| Camera/vision pipeline | 🔧 optional |

---

## UI

Two views accessible via the web frontend:

| View | Route | Key |
|------|-------|-----|
| Agent (hologram) | `/` | — |
| Control panel | `/control` | `Ctrl+,` |

Navigate back from control panel with `ESC`.

### Agent View
- Three.js neural mesh reacts to system state (idle / listening / thinking / speaking)
- 3 orbital scanning rings (JARVIS-style halo) with state-reactive opacity
- AudioVisualizer FFT bar at the bottom
- Thinking dots during LLM inference
- Response text fades in/out with blur transition
- 30-second idle hint shows wake word
- TTS backend badge (Piper / Kokoro / Edge-TTS)

### Control Panel
- Live CPU / RAM / VRAM / GPU temperature from backend (psutil + pynvml)
- System log with color-coded levels (info / warn / error / ok)
- **MOTOR LLM panel** — toggle LOCAL (Ollama) / API, select provider, enter key, test connectivity
- TTS speed slider wired to backend in real time
- Test TTS button
- Conversation history with markdown rendering
- Voice enrollment wizard (records samples, registers wake word variants)
- Wake word chip management (add / remove)

---

## Voice Pipeline

```
Mic (always on, low power)
      │
      ├─ SLEEPING: wake word only (transcript gate)
      │     wake word detected ↓
      ├─ LISTENING: VAD captures utterance
      │     silence detected ↓
      ├─ State gate: discard if SPEAKING / PROCESSING / mute active
      │     ↓
      ├─ Whisper ASR transcription
      │     ↓
      ├─ LLMManager.generate()
      │     ↓
      └─ TTSManager → mute_for(duration + echo_tail) → AudioOutput
```

**Echo cancellation layers:**
1. `mute_for(duration + 5s)` — mic muted for full TTS playback
2. State gate — audio discarded if engine is SPEAKING/PROCESSING
3. `echo_tail_secs: 3.0` — extra silence after playback ends
4. `strict_wake_word` (optional) — always require wake word even in active session

**TTS fallback chain:** Piper → Kokoro → Edge-TTS

---

## LLM Providers

Switch providers at runtime from the **CONFIG** tab — no restart needed.

| Provider | Models | Key env var |
|---|---|---|
| Ollama (local) | Any pulled model | — |
| OpenAI | gpt-4o, gpt-4o-mini, gpt-4-turbo | `OPENAI_API_KEY` |
| Anthropic | claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5 | `CLAUDE_API_KEY` |
| Groq | llama-3.3-70b, mixtral-8x7b, gemma2-9b | `GROQ_API_KEY` |
| Gemini | gemini-2.0-flash, gemini-1.5-pro | `GEMINI_API_KEY` |

Config in `config.yaml`:

```yaml
api:
  llm:
    provider: ollama       # ollama | openai | anthropic | groq | gemini
    model: gpt-4o-mini
    api_key: ${OPENAI_API_KEY}
```

---

## Configuration

`config/config.yaml` — main settings

Key fields:

```yaml
system:
  mode: LOCAL          # LOCAL | HYBRID

trigger:
  wake_words: ["hola jarvis", "oye jarvis", "hey jarvis", "cyrus"]
  strict_wake_word: false   # true = always require wake word

audio:
  input:
    echo_tail_secs: 3.0     # mic mute after TTS (increase for desktop speakers)

local:
  llm:
    model: qwen3:8b
  tts:
    provider: piper
    speed: 0.92
    piper_model: models/tts/piper/es_MX-ald-medium.onnx

memory:
  enabled: false       # requires Qdrant running locally
```

---

## Memory (Phase 3)

Requires a local Qdrant instance:

```bash
docker run -d -p 6333:6333 qdrant/qdrant
```

Each conversation turn is:
1. Embedded with `sentence-transformers/all-MiniLM-L6-v2`
2. Stored in Qdrant (vector search) + SQLite (full text)
3. Top-K relevant memories retrieved per turn for LLM context

---

## Modes

| Mode | LLM | Notes |
|------|-----|-------|
| `LOCAL` | Ollama only | Fully offline |
| `HYBRID` | Ollama → active API provider | Fallback to cloud if Ollama fails |

---

## Requirements

- Python 3.11+, Node 18+
- Ollama (`ollama serve`) — for local mode
- CUDA GPU recommended (RTX 2070S / 8 GB VRAM tested); CPU mode works
- USB microphone + speakers

```bash
pip install -r requirements.txt
cd frontend && npm install
```

Optional API packages (auto-installed via requirements.txt):
```bash
pip install openai>=1.0.0 google-generativeai>=0.8.0
```

---

## Tests

```bash
pytest tests/ -v
JARVIS_RUN_SLOW_TESTS=1 pytest tests/ -v   # includes model-load tests
```

---

## Project Structure

```
backend/
  core/          — engine, config, state, event bus
  modules/
    audio/       — mic input (WASAPI), VAD, echo gate, Whisper ASR, speaker output
    nlp/         — wake-word trigger detector
    llm/         — ollama_client, claude_client, openai_client, groq_client,
                   gemini_client, llm_manager (multi-provider runtime switching)
    tts/         — Piper, Kokoro, Edge-TTS, TTS manager
    memory/      — embedder, Qdrant store, SQLite DB, memory manager
    vision/      — camera, face detector, YOLO, Frigate (optional)
    home_assistant/ — HA REST client, device controller
    planner/     — task planner with voice commands
  api/           — WebSocket server
  utils/         — logger, text cleaner, helpers

frontend/src/
  views/         — AgentView (hologram), ControlView (panel + LLM selector)
  hooks/         — useWebSocket, useAudioAnalyser
  store/         — Zustand state (useJARVISStore) — llmConfig, llmTestResult
  utils/         — WebSocket client (ws-client.ts)

config/
  config.yaml    — main configuration
  soul.md        — CYRUS personality / system prompt
  prompts.yaml   — LLM prompt templates

models/
  tts/piper/     — es_MX-ald-medium.onnx (gitignored)
  speaker/ecapa/ — ECAPA-TDNN speaker recognition model (gitignored)
```

---

## Roadmap

- **Phase 5** — Proactive alerts (Frigate events, calendar reminders)
- **Phase 6** — Multi-room audio / wake word on mobile
- **Phase 7** — XTTS v2 voice cloning (reference WAV)

---

*C.Y.R.U.S — Personal Homelab AI | Lima, PE | Ricardo*
