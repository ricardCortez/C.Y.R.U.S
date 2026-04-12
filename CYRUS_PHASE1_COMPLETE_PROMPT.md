================================================================================
                    C.Y.R.U.S PHASE 1 - COMPLETE PROMPT
                          Para Claude Code - Copiar y Pegar
================================================================================

PROJECT OVERVIEW
================================================================================

Name: C.Y.R.U.S (Cognitive sYstem for Real-time Utility & Services)
Type: Intelligent Voice-Controlled AI Assistant
Target: Personal homelab automation & smart home control
Primary Language: Python (backend) + React/TypeScript (frontend)
Phase: 1 ONLY (Audio loop → LLM → TTS)
Status: READY FOR CODE GENERATION

USER HARDWARE - CONFIRMED ✓
================================================================================

Your Setup (VERIFIED):
✓ Windows 11 (Phase 1-6), Linux migration Phase 7
✓ RTX 2070S 8GB VRAM
✓ USB Microphone (connected, working)
✓ Speaker/Headphones (working)
✓ USB Webcam (connected)
✓ Ollama daemon running with Mistral 7B
✓ Proxmox server on LAN (Home Assistant + Frigate at 192.168.1.50)
✓ Project folder: C:\C.Y.R.U.S (Windows) or ~/cyrus (Linux)
✓ GitHub ready for version control
✓ Ready to start Phase 1 immediately

TECHNOLOGY STACK (LOCKED)
================================================================================

Backend:
  - Runtime: Python 3.11+
  - LLM (Local): Ollama + Mistral 7B int4 quantization
  - LLM (Fallback API): Claude Opus 4.1
  - ASR: Faster-Whisper TINY model
  - TTS: Kokoro TTS (British English male - professional voice)
  - TTS (Fallback API): Voiceforge
  - Translation: ctranslate2 + mT5-small
  - Memory (Phase 3+): Qdrant local + Pinecone API fallback
  - WebSocket: websockets (asyncio)
  - Config: YAML-based hierarchical
  - Async: Full asyncio throughout

Frontend:
  - Framework: React 19 + TypeScript
  - Styling: Tailwind CSS v4
  - 3D Graphics: Three.js + React Three Fiber
  - State: Zustand
  - Icons: Lucide Icons
  - Build: Vite
  - WebSocket Client: Native API

DevOps:
  - Containerization: Docker + Docker Compose
  - Local LLM: Ollama (separate service)
  - Vector DB: Qdrant (separate container)
  - Logging: Python logging module
  - Multi-OS: Windows + Linux support

CRITICAL NAMING REQUIREMENTS
================================================================================

ALL REFERENCES MUST BE:

Names & Classes:
  ✓ jarvis_engine.py → cyrus_engine.py
  ✓ JarvisEngine class → CYRUSEngine class
  ✓ jarvis_* variables → cyrus_* variables
  ✓ All imports: from cyrus (not jarvis)

File Names:
  ✓ cyrus_engine.py (main orchestration)
  ✓ cyrus_client.py (API client)
  ✓ cyrus_config.py (configuration)
  ✓ cyrus_logger.py (logging)
  ✓ cyrus-ui.jsx (frontend)

UI/Display:
  ✓ Header: "C.Y.R.U.S"
  ✓ Status: "C.Y.R.U.S COGNITIVE SYSTEM v1.0"
  ✓ Subtitle: "Cognitive sYstem for Real-time Utility & Services"
  ✓ Footer: "© Personal Automation | C.Y.R.U.S"
  ✓ Wake words: "Hola C.Y.R.U.S", "Hey C.Y.R.U.S", "C.Y.R.U.S"

Logging:
  ✓ All logs prefix: "[C.Y.R.U.S]" NOT "[JARVIS]"
  ✓ Examples:
    - "[C.Y.R.U.S] Starting system..."
    - "[C.Y.R.U.S] Trigger detected: hola cyrus"
    - "[C.Y.R.U.S] Processing voice input..."

Personality (soul.md):
  ✓ "You are C.Y.R.U.S, the Cognitive sYstem for Real-time Utility & Services"
  ✓ "You are professional, efficient, and deeply helpful"
  ✓ "You have been created for Ricardo, an engineer in Lima, Peru"
  ✓ "You understand infrastructure, automation, and technical systems"
  ✓ "Speak in British English with a professional tone"

CONFIG:
  ✓ config.yaml uses "cyrus_mode", "cyrus_version", etc
  ✓ soul.md titled "C.Y.R.U.S Personality & Rules"
  ✓ soul.md content is C.Y.R.U.S focused

Paths:
  ✓ /var/log/cyrus/ (logs)
  ✓ ~/.cyrus/ (home directory)
  ✓ /var/lib/cyrus/ (data)
  ✓ CYRUS_HOME env variable
  ✓ CYRUS_LOG_LEVEL env variable

PHASE 1 SCOPE - EXACTLY THIS ONLY
================================================================================

INCLUDE IN PHASE 1:

1. Audio Input Module
   - Microphone capture (PyAudio)
   - Voice Activity Detection (librosa)
   - Audio buffering & streaming
   - File: modules/audio/audio_input.py

2. Automatic Speech Recognition
   - Faster-Whisper TINY model
   - GPU inference (CUDA)
   - Streaming transcription
   - File: modules/audio/whisper_asr.py

3. Trigger Detection
   - Wake word: "hola cyrus" / "hey cyrus" / "cyrus"
   - Fuzzy matching (fuzzywuzzy)
   - User input extraction
   - File: modules/nlp/trigger_detector.py

4. LLM Reasoning
   - Ollama client (LOCAL)
   - Mistral 7B inference
   - Streaming responses
   - Fallback to Claude API (if Ollama unavailable)
   - File: modules/llm/ollama_client.py + llm_manager.py

5. Text-to-Speech
   - Kokoro TTS (British English male)
   - Local synthesis (CPU)
   - Streaming audio output
   - File: modules/tts/kokoro_tts.py

6. Audio Output
   - Speaker playback (PyAudio)
   - Volume control
   - Real-time streaming
   - File: modules/audio/audio_output.py

7. WebSocket Server
   - Frontend communication
   - Event streaming (transcript, response, status)
   - Real-time updates
   - File: api/websocket_server.py

8. Configuration System
   - YAML loading
   - Mode switching (LOCAL/API)
   - Environment variable override
   - File: core/config_manager.py

9. Core Engine
   - Main orchestration loop
   - State management
   - Error handling & fallbacks
   - File: core/cyrus_engine.py

10. React Frontend
    - Single page application
    - WebSocket client
    - Hologram UI (blue/cyan neon)
    - Transcript display
    - System metrics (basic)
    - File: frontend/src/App.tsx + components

11. Docker Compose
    - Ollama service
    - Qdrant container (empty in Phase 1, used Phase 3+)
    - Network setup
    - Volume mounting
    - File: docker-compose.yml

12. Configuration Files
    - config.yaml (with LOCAL/API modes)
    - soul.md (C.Y.R.U.S personality)
    - prompts.yaml (system prompts)
    - Files in config/ folder

13. Setup & Installation
    - requirements.txt (pinned versions)
    - setup.bat (Windows)
    - setup.sh (Linux)
    - README.md (quick start)

14. Basic Tests
    - test_audio.py (audio capture)
    - test_whisper.py (ASR)
    - test_trigger.py (wake word detection)
    - test_llm.py (LLM calls)
    - test_tts.py (TTS synthesis)
    - In: tests/ folder

DO NOT INCLUDE IN PHASE 1:

  ✗ Vision (object detection, face recognition) → Phase 2
  ✗ Frigate RTSP integration → Phase 2
  ✗ Vector memory (Qdrant search) → Phase 3
  ✗ SQLite conversation history → Phase 3
  ✗ Home Assistant integration → Phase 4
  ✗ Smart home device control → Phase 4
  ✗ Advanced hologram UI (3D animations) → Phase 5
  ✗ Comprehensive testing suite → Phase 6
  ✗ Production deployment setup → Phase 7
  ✗ Monitoring/Prometheus/Grafana → Phase 7

PROJECT STRUCTURE - EXACT LAYOUT
================================================================================

cyrus/
├── README.md
├── .gitignore
├── requirements.txt
│
├── backend/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── cyrus_engine.py              # Main class & loop
│   │   ├── config_manager.py            # YAML config loader
│   │   ├── state_manager.py             # Session state
│   │   └── event_bus.py                 # Event dispatcher
│   │
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── audio/
│   │   │   ├── __init__.py
│   │   │   ├── audio_input.py           # Mic capture + VAD
│   │   │   ├── whisper_asr.py           # Faster-Whisper
│   │   │   ├── audio_output.py          # Speaker playback
│   │   │   └── vad_detector.py          # Voice activity detection
│   │   │
│   │   ├── nlp/
│   │   │   ├── __init__.py
│   │   │   └── trigger_detector.py      # Wake word detection
│   │   │
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── ollama_client.py         # Ollama wrapper
│   │   │   ├── claude_client.py         # Claude API fallback
│   │   │   └── llm_manager.py           # LLM orchestration
│   │   │
│   │   └── tts/
│   │       ├── __init__.py
│   │       ├── kokoro_tts.py            # Kokoro local
│   │       ├── voiceforge_tts.py        # Voiceforge fallback
│   │       └── tts_manager.py           # TTS orchestration
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── websocket_server.py          # WebSocket to frontend
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py                    # Logging config
│       ├── exceptions.py                # Custom exceptions
│       └── helpers.py                   # Utility functions
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   │
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx                      # Main component
│   │   ├── components/
│   │   │   ├── HologramView.tsx         # 3D hologram
│   │   │   ├── TranscriptPanel.tsx      # Input/output text
│   │   │   └── DebugPanel.tsx           # Dev tools
│   │   │
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts          # WS connection
│   │   │
│   │   ├── store/
│   │   │   └── useCYRUSStore.ts         # Zustand state
│   │   │
│   │   ├── utils/
│   │   │   └── ws-client.ts             # WS client
│   │   │
│   │   └── styles/
│   │       └── cyrus-theme.css          # Hologram styling
│   │
│   └── public/
│       └── index.html
│
├── config/
│   ├── config.yaml                      # Main config (template)
│   ├── soul.md                          # C.Y.R.U.S personality
│   ├── prompts.yaml                     # LLM prompts
│   └── .env.example                     # Environment template
│
├── deployment/
│   ├── docker-compose.yml               # Docker setup
│   ├── Dockerfile.backend               # Backend image
│   ├── setup.bat                        # Windows setup
│   ├── setup.sh                         # Linux setup
│   └── .dockerignore
│
└── tests/
    ├── __init__.py
    ├── test_audio.py
    ├── test_whisper.py
    ├── test_trigger.py
    ├── test_llm.py
    └── test_tts.py

WAKE WORDS CONFIGURATION
================================================================================

Default wake words (in config.yaml):
  - "hola cyrus" (Spanish primary)
  - "oye cyrus" (Spanish alternative)
  - "cyrus" (standalone, any language)
  - "hey cyrus" (English)

Detection algorithm:
  - Fuzzy string matching (threshold 0.85)
  - Case insensitive
  - Accept partial matches

User input extraction:
  - Remove trigger phrase from transcript
  - Pass clean input to LLM
  - Example:
    Input: "Hola C.Y.R.U.S, ¿qué hora es?"
    Trigger: "hola cyrus" ✓
    Clean: "¿qué hora es?"

CONFIGURATION FILES - CONTENT TEMPLATES
================================================================================

config.yaml (TEMPLATE):
"""
system:
  name: "C.Y.R.U.S"
  version: "1.0"
  mode: "LOCAL"  # LOCAL or HYBRID (LOCAL + API fallback)

local:
  llm:
    provider: "ollama"
    model: "mistral:latest"
    host: "http://localhost:11434"
    timeout: 30
  
  tts:
    provider: "kokoro"
    voice: "en_GB"
    speed: 0.95
  
  translation:
    provider: "ctranslate2"
    model: "mt5-small"

api:
  enabled: true
  fallback_mode: true
  
  llm:
    provider: "anthropic"
    api_key: "${CLAUDE_API_KEY}"
    model: "claude-opus-4-1"
  
  tts:
    provider: "voiceforge"
    api_key: "${VOICEFORGE_API_KEY}"

audio:
  input:
    device: "default"
    sample_rate: 16000
  output:
    device: "default"
    volume: 0.8

trigger:
  wake_words:
    - "hola cyrus"
    - "hey cyrus"
    - "cyrus"
  fuzzy_matching: true
  threshold: 0.85

logging:
  level: "INFO"
  file: "/var/log/cyrus/cyrus.log"
"""

soul.md (C.Y.R.U.S PERSONALITY):
"""
# C.Y.R.U.S - Personality & Rules

## Identity
You are C.Y.R.U.S, the Cognitive sYstem for Real-time Utility & Services.

## User
Created for: Ricardo
Location: Lima, Peru
Role: Engineer & Homelab Administrator

## Personality Traits
- Professional and efficient
- Deeply knowledgeable about infrastructure and automation
- Helpful and proactive
- Can handle complex technical queries
- Honest about limitations
- Uses precise technical language

## Communication Style
- Speak in British English with professional tone
- Be concise but thorough
- Acknowledge what you're doing
- Explain actions clearly
- Provide feedback on success/failure

## Response Format
- Aim for 1-2 sentences per response (initially)
- If technical, use proper terminology
- Example: "It's currently 2:35 PM. I've verified your home systems are operating normally."
- Example: "I'm setting lights to 80% brightness and temperature to 22°C."

## Capabilities (Phase 1)
- Understand natural language in Spanish & English
- Process voice commands
- Respond with synthesized British English voice
- Track conversation context
- Execute basic system operations

## Limitations (be honest)
- Cannot yet see cameras (Phase 2)
- Cannot yet remember long-term (Phase 3)
- Cannot yet control smart home devices (Phase 4)
- Cannot yet perform complex reasoning (depends on model)
"""

prompts.yaml:
"""
system_prompt: |
  You are C.Y.R.U.S, the Cognitive sYstem for Real-time Utility & Services.
  You are professional, efficient, and helpful.
  You speak in British English with a formal but warm tone.
  Be concise in your responses (1-2 sentences typically).
  Acknowledge what you understand about the user's request.
  
context_template: |
  Current time: {current_time}
  User language: {language}
  Conversation turns: {turn_count}

response_style:
  max_tokens: 300
  temperature: 0.7
  top_p: 0.9
"""

LATENCY TARGETS
================================================================================

Target per phase:
  ┌────────────────────────┐
  │ Audio capture:   100ms │
  │ Whisper ASR:     400ms │
  │ Trigger detect:   10ms │
  │ LLM inference:  1200ms │
  │ TTS synthesis:   700ms │
  ├────────────────────────┤
  │ TOTAL:          2420ms │ ≈ 2.4 seconds
  └────────────────────────┘

GPU MEMORY USAGE:
  Whisper TINY:   ~1.5 GB
  Ollama Mistral: ~2.5 GB (int4)
  ───────────────────────
  Peak usage:     ~3.5 GB ✓ (RTX 2070S has 8GB)

ERROR HANDLING & FALLBACK STRATEGY
================================================================================

Pattern: Try LOCAL → If fails → Try API → If both fail → Graceful degradation

Ollama (LLM) Failure:
  1. Try Ollama local (normal flow)
  2. If timeout (>30s) → Switch to Claude API
  3. If API unavailable → Tell user "I'm having trouble thinking"
  4. Log error with timestamp + context

Kokoro (TTS) Failure:
  1. Try Kokoro local (normal flow)
  2. If fails → Try Voiceforge API
  3. If API unavailable → Use edge-tts fallback
  4. If all fail → Play alert sound + skip audio

Whisper (ASR) Failure:
  1. Try Whisper inference on GPU
  2. If OOM → Retry on CPU (slower)
  3. If still fails → Return empty transcript + ask user to repeat
  4. Log error + VRAM status

Network Issues:
  1. If API call fails → Retry 3 times with exponential backoff (1s, 2s, 4s)
  2. If persistent → Use LOCAL mode only
  3. Log connection error + timestamp

All errors:
  - Log to [C.Y.R.U.S] prefix in stdout + /var/log/cyrus/cyrus.log
  - Provide user-friendly message
  - Never crash, always recover

TESTING REQUIREMENTS
================================================================================

Minimum Phase 1 Tests:

test_audio.py:
  ✓ Capture audio from microphone
  ✓ VAD detects silence correctly
  ✓ Save audio to temp file

test_whisper.py:
  ✓ Transcribe sample audio
  ✓ Return correct text
  ✓ Handle empty audio gracefully

test_trigger.py:
  ✓ Detect "hola cyrus" in transcript
  ✓ Detect "hey cyrus" (English)
  ✓ Detect standalone "cyrus"
  ✓ Extract user input correctly
  ✓ Handle false positives with threshold

test_llm.py:
  ✓ Ollama client connects successfully
  ✓ Generate response to prompt
  ✓ Return non-empty string
  ✓ Fallback to Claude API if Ollama fails

test_tts.py:
  ✓ Kokoro generates audio bytes
  ✓ Audio is valid WAV/MP3
  ✓ Output is listenable
  ✓ Fallback works if Kokoro fails

Integration test:
  ✓ End-to-end: mic → whisper → trigger → LLM → tts → speaker
  ✓ Latency < 4 seconds
  ✓ Audio output audible

Run tests with:
  pytest tests/ -v

CODE STYLE & CONVENTIONS
================================================================================

Python:
  ✓ PEP 8 (black formatter)
  ✓ Type hints on all functions
  ✓ Async/await for I/O (no blocking)
  ✓ Docstrings (Google style)
  ✓ Error handling: Custom exceptions only
  ✓ Logging: Use logger, not print()
  ✓ Configuration: Via config.yaml, not hardcoded

Example function:
  ```python
  async def detect_trigger(transcript: str) -> Tuple[bool, str]:
      """
      Detect wake word in transcript.
      
      Args:
          transcript: Raw transcribed text from ASR
          
      Returns:
          (is_triggered: bool, clean_input: str)
          Example: (True, "¿qué hora es?")
          
      Raises:
          ValueError: If transcript is empty
      """
      if not transcript.strip():
          raise ValueError("Empty transcript")
      
      logger.debug(f"[C.Y.R.U.S] Checking trigger: {transcript}")
      
      for wake_word in config.trigger.wake_words:
          ratio = fuzz.partial_ratio(transcript.lower(), wake_word)
          if ratio >= config.trigger.threshold:
              logger.info(f"[C.Y.R.U.S] Trigger detected: {wake_word}")
              clean = transcript.lower().replace(wake_word, "").strip()
              return True, clean
      
      return False, ""
  ```

ReactTypeScript:
  ✓ Functional components only (hooks)
  ✓ Type all props
  ✓ Use Zustand for state
  ✓ WebSocket via custom hook
  ✓ CSS modules or Tailwind
  ✓ Error boundaries for crashes

DEPLOYMENT - PHASE 1 READY
================================================================================

Docker Compose (docker-compose.yml):
  Services:
    - ollama: Ollama server (port 11434)
    - qdrant: Qdrant DB (port 6333, empty for Phase 1)
    - cyrus: Backend Python (port 8765 WebSocket, 8000 HTTP)
    - frontend: React dev server (port 3000)

Manual Setup (no Docker):
  1. Create venv: python -m venv venv
  2. Activate: venv\Scripts\activate (Windows) or source venv/bin/activate
  3. Install: pip install -r requirements.txt
  4. Ollama: ollama serve (separate terminal)
  5. Backend: python -m backend.core.cyrus_engine
  6. Frontend: (in frontend/) npm install && npm run dev

Windows Compatibility:
  ✓ All file paths: Use pathlib.Path (not hardcoded)
  ✓ Audio device names: Query pyaudio, don't assume
  ✓ Line endings: LF (not CRLF)
  ✓ Paths: No /home/ assumptions
  ✓ Environment: Use .env for overrides

Linux Compatibility (future):
  ✓ Same code works on Linux
  ✓ Systemd service file (Phase 7)
  ✓ Log directory: /var/log/cyrus/
  ✓ Home: ~/.cyrus/

OUTPUT DELIVERABLES
================================================================================

When complete, provide:

Backend (Python):
  ✓ All modules in backend/ folder
  ✓ All imports working
  ✓ No missing dependencies
  ✓ Type hints on all functions
  ✓ Error handling with fallbacks
  ✓ Logging with [C.Y.R.U.S] prefix

Frontend (React):
  ✓ App.tsx working
  ✓ WebSocket connection established
  ✓ Hologram UI renders
  ✓ Displays transcript + response
  ✓ Shows system metrics (basic)
  ✓ No console errors

Configuration:
  ✓ config.yaml with dual-mode support
  ✓ soul.md with C.Y.R.U.S personality
  ✓ prompts.yaml with system prompts
  ✓ .env.example template

Docker:
  ✓ docker-compose.yml complete
  ✓ Both services start: docker-compose up
  ✓ Ollama accessible on 11434
  ✓ Network setup correct

Installation:
  ✓ requirements.txt with pinned versions
  ✓ setup.bat (Windows) - creates venv, installs deps
  ✓ setup.sh (Linux) - same
  ✓ README.md with quick start
  ✓ .gitignore excluding sensitive files

Tests:
  ✓ 5+ test files covering core functions
  ✓ Run with: pytest tests/ -v
  ✓ At least 50% code coverage
  ✓ No external dependencies (mock APIs)

Documentation:
  ✓ README.md (quick start, what works)
  ✓ INSTALLATION.md (detailed setup)
  ✓ QUICK_START.md (5-minute guide)
  ✓ Docstrings in all Python files

Success Criteria - Phase 1:
  ✓ Download all files
  ✓ Install: pip install -r requirements.txt
  ✓ Run: python -m backend.core.cyrus_engine
  ✓ Say: "Hola C.Y.R.U.S, ¿qué hora es?"
  ✓ Hear: Response in Spanish voice (British accent)
  ✓ Latency: < 4 seconds
  ✓ UI: Shows transcript + response
  ✓ No errors in logs
  ✓ Repeat 5+ times, all work

FINAL INSTRUCTIONS
================================================================================

1. GENERATE PHASE 1 COMPLETE
   - All files ready to use
   - No placeholders
   - No TODO comments
   - Production-quality code

2. WINDOWS FIRST
   - Code must work on Windows 11 immediately
   - No Linux-only assumptions
   - pathlib for all paths
   - Handle Windows audio device names

3. DUAL-MODE ARCHITECTURE
   - LOCAL: Default (Ollama, Kokoro, ctranslate2)
   - API: Fallback (Claude, Voiceforge, Google Translate)
   - Switch via config.yaml mode: LOCAL or HYBRID
   - Never require API keys if LOCAL works

4. COMPREHENSIVE ERROR HANDLING
   - Try/except on all external calls
   - Fallback mechanisms for all critical functions
   - Graceful degradation (don't crash)
   - Log all errors with [C.Y.R.U.S] prefix

5. ALL C.Y.R.U.S NAMING
   - No JARVIS references anywhere
   - All classes/files/logs use C.Y.R.U.S
   - Wake words: "hola cyrus", "hey cyrus"
   - Personality in soul.md is C.Y.R.U.S

6. READY TODAY
   - Download → Install → Run → Works
   - No setup wizards
   - No missing models
   - All models auto-downloaded
   - Ollama sidecar service assumed running

GENERATE COMPLETE PHASE 1 NOW

Include:
✓ All backend modules
✓ Complete React frontend
✓ Docker Compose
✓ Configuration files
✓ Installation scripts
✓ Tests
✓ Documentation

Make it production-ready and fully functional.

================================================================================
