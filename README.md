# C.Y.R.U.S — Cognitive sYstem for Real-time Utility & Services

> Phase 1: Audio Loop → LLM → TTS

A professional voice-controlled AI assistant for your homelab.
Say **"Hola C.Y.R.U.S"** → speak → hear a British-English response in ~2.4 seconds.

---

## Quick Start (Windows)

```bat
# 1. Run setup
deployment\setup.bat

# 2. Activate venv
venv\Scripts\activate

# 3. Start Ollama (separate terminal)
ollama serve

# 4. Start C.Y.R.U.S backend
python -m backend.core.cyrus_engine

# 5. Start frontend (separate terminal)
cd frontend
npm run dev
# → open http://localhost:3000
```

Then say: **"Hola C.Y.R.U.S, ¿qué hora es?"**

---

## Architecture (Phase 1)

```
Microphone → VAD → Whisper TINY → TriggerDetector
                                         ↓
                              LLMManager (Ollama / Claude)
                                         ↓
                              TTSManager (Kokoro / Edge-TTS)
                                         ↓
                                      Speaker
                                         ↓
                              WebSocket → React UI
```

## Wake Words

| Phrase | Language |
|--------|----------|
| "Hola C.Y.R.U.S" | Spanish |
| "Oye C.Y.R.U.S" | Spanish |
| "Hey C.Y.R.U.S" | English |
| "C.Y.R.U.S" | Any |

## Modes

| Mode | LLM | TTS |
|------|-----|-----|
| `LOCAL` | Ollama + Mistral 7B | Kokoro → Edge-TTS |
| `HYBRID` | Ollama → Claude API | Kokoro → Edge-TTS |

Set in `config/config.yaml` → `system.mode`.

## Requirements

- Python 3.11+
- Node.js 18+ (frontend only)
- Ollama running locally (`ollama serve`)
- CUDA GPU recommended (RTX 2070S tested)
- USB Microphone + Speaker

## Tests

```bash
pytest tests/ -v                          # fast tests (no models)
CYRUS_RUN_SLOW_TESTS=1 pytest tests/ -v  # includes model-load tests
```

## Project Structure

```
backend/
  core/          — engine, config, state, event bus
  modules/
    audio/       — mic input, VAD, Whisper ASR, speaker output
    nlp/         — wake-word trigger detector
    llm/         — Ollama client, Claude client, LLM manager
    tts/         — Kokoro, Edge-TTS, TTS manager
  api/           — WebSocket server
  utils/         — logger, exceptions, helpers

frontend/src/
  components/    — HologramView, TranscriptPanel, DebugPanel
  hooks/         — useWebSocket
  store/         — Zustand state
  utils/         — WebSocket client

config/
  config.yaml    — main configuration
  soul.md        — C.Y.R.U.S personality
  prompts.yaml   — LLM prompt templates
```

---

*C.Y.R.U.S Phase 1 — Personal Automation | © Ricardo*
