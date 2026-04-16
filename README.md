# C.Y.R.U.S — Cognitive sYstem for Real-time Utility & Services

> A local-first, voice-driven AI assistant for your homelab. JARVIS-style neural hologram UI, Spanish voice, Piper TTS, semantic memory.

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

Say **"Hola C.Y.R.U.S"** to activate.

> **Note:** The microphone only activates once the web UI is open and connected. Running the backend alone keeps the mic silent.

---

## Architecture

```
Browser UI (React + Three.js)
        ↕  WebSocket :8765
┌─────────────────────────────────┐
│  CYRUSEngine                    │
│  ┌──────────┐  ┌─────────────┐  │
│  │ AudioIn  │  │  EventBus   │  │
│  │ PyAudio  │  │  (async)    │  │
│  │ VAD+ASR  │  └─────────────┘  │
│  └────┬─────┘         ↑         │
│       │        ┌──────┴──────┐  │
│  Whisper ASR   │ WebSocket   │  │
│       │        │ Server      │  │
│  TriggerDetect └─────────────┘  │
│       │                         │
│  LLMManager (Ollama / Claude)   │
│       │  dual output            │
│  DISPLAY text ──→ WebSocket UI  │
│  SPEECH text  ──→ TTSManager    │
│                   Piper → WAV   │
│                   Kokoro fallbk │
│                   Edge-TTS fbk  │
│       ↓                         │
│  AudioOutput (speakers)         │
│  MemoryManager                  │
│   Qdrant (vectors) + SQLite     │
└─────────────────────────────────┘
```

---

## Features

| Feature | Status |
|---------|--------|
| Wake word detection (fuzzy) | ✅ |
| Whisper ASR (faster-whisper) | ✅ |
| Ollama LLM (Phi-3, Mistral, etc.) | ✅ |
| Claude API fallback | ✅ |
| Piper TTS (es_MX, offline, fast) | ✅ |
| Kokoro TTS fallback | ✅ |
| Edge-TTS fallback | ✅ |
| Dual DISPLAY/SPEECH output | ✅ |
| Semantic memory (Qdrant + SQLite) | ✅ |
| Neural mesh hologram (Three.js) | ✅ |
| Real system stats (CPU/GPU/VRAM) | ✅ |
| Voice enrollment (custom wake words) | ✅ |
| Control panel (config, logs, history) | ✅ |
| Camera/vision pipeline | 🔧 optional |
| Home Assistant integration | 📋 Phase 4 |

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
- TTS speed slider wired to backend in real time
- LLM model name editable inline (sends `set_llm_model` command)
- Test TTS button
- Conversation history with markdown rendering
- Voice enrollment wizard (records 5 samples, registers wake word variants)
- Wake word chip management (add / remove)

---

## Voice Pipeline

```
raw LLM output
      │
      ├─ VOZ: marker present?
      │     YES → display = text above marker (markdown OK)
      │            speech  = text after marker  (clean prose)
      │     NO  → both = same text
      │
      └─ prepare_speech()
            clean_for_tts()      ← strip markdown symbols
            normalize_for_speech() ← expand abbreviations, fix punctuation
                  ↓
            PiperTTS.synthesise()  ← offline, es_MX-claude-high
```

TTS fallback chain: **Piper → Kokoro → Edge-TTS**

---

## Configuration

`config/config.yaml` — main settings

Key fields:

```yaml
system:
  mode: LOCAL          # LOCAL | HYBRID

trigger:
  wake_words: ["hola cyrus", "oye cyrus", "hey cyrus"]

local:
  llm:
    model: phi3:latest
  tts:
    provider: piper
    speed: 0.92
    piper_model: models/tts/piper/es_MX-claude-high.onnx

memory:
  enabled: true        # requires Qdrant running locally
  qdrant:
    host: localhost
    port: 6333
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
| `HYBRID` | Ollama → Claude API | Fallback to cloud |

---

## Requirements

- Python 3.11+, Node 18+
- Ollama (`ollama serve`)
- CUDA GPU recommended (RTX 2070S / 8 GB VRAM tested)
- USB microphone + speakers
- Optional: Qdrant (memory), pynvml (GPU stats)

```bash
pip install -r requirements.txt
cd frontend && npm install
```

---

## Tests

```bash
pytest tests/ -v
CYRUS_RUN_SLOW_TESTS=1 pytest tests/ -v   # includes model-load tests
```

---

## Project Structure

```
backend/
  core/          — engine, config, state, event bus
  modules/
    audio/       — mic input, VAD, Whisper ASR, speaker output
    nlp/         — wake-word trigger detector
    llm/         — Ollama client, Claude client, LLM manager
    tts/         — Piper, Kokoro, Edge-TTS, TTS manager
    memory/      — embedder, Qdrant store, SQLite DB, memory manager
    vision/      — camera, face detector, YOLO, Frigate (optional)
  api/           — WebSocket server
  utils/         — logger, text cleaner, helpers

frontend/src/
  views/         — AgentView (hologram), ControlView (panel)
  components/    — ParticleNetwork (Three.js), AudioVisualizer
  hooks/         — useWebSocket, useAudioAnalyser
  store/         — Zustand state (useCYRUSStore)
  utils/         — WebSocket client (ws-client.ts)

config/
  config.yaml    — main configuration
  soul.md        — C.Y.R.U.S personality / system prompt
  prompts.yaml   — LLM prompt templates

models/
  tts/piper/     — es_MX-claude-high.onnx (gitignored, ~61 MB)
```

---

## Roadmap

- **Phase 4** — Home Assistant integration (lights, sensors, automations)
- **Phase 5** — Proactive alerts (Frigate events, calendar reminders)
- **Phase 6** — Multi-room audio / wake word on mobile

---

*C.Y.R.U.S — Personal Homelab AI | Lima, PE | Ricardo*
