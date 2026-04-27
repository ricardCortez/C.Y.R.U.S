# JARVIS Phases 4–7 — Implementation Plans Summary

> Each phase has its own detailed plan file. This document is the roadmap overview.
> **For agentic workers:** Start each phase only after the previous one passes all tests.

---

## Phase 4 — Home Assistant Integration

**Goal:** "Turn on lights" → Philips Hue activates via Home Assistant REST API.

**Files to create:**
- `backend/modules/home_assistant/__init__.py`
- `backend/modules/home_assistant/ha_client.py` — HA REST API wrapper
- `backend/modules/home_assistant/device_controller.py` — device state + control
- `backend/modules/home_assistant/skill_interpreter.py` — NL intent → HA action
- `config/home_assistant.yaml` — entity mappings
- `tests/test_ha.py`

**Key tasks:**
1. `HAClient` — async httpx wrapper for `http://192.168.1.50:8123/api/`
   - `get_states()` → all entity states
   - `call_service(domain, service, entity_id, **kwargs)` → trigger actions
   - `get_entity(entity_id)` → single entity state
2. `DeviceController` — maps friendly names to entity IDs
   - `turn_on(device_name)` / `turn_off(device_name)` / `set_brightness(device, pct)`
   - Entity map loaded from `config/home_assistant.yaml`
3. `SkillInterpreter` — regex + LLM mini-classifier
   - Parses: "turn on/off [device]", "set [device] to [value]%", "what is [device] status"
   - Returns `HAAction(service, entity_id, params)`
4. Wire into `JARVISEngine._process_one_turn()`:
   - After LLM response, check if `SkillInterpreter` detects an HA intent
   - Execute the HA action
   - Append result to TTS response: "Done. Lights are now on."

**config/home_assistant.yaml template:**
```yaml
ha:
  host: "http://192.168.1.50:8123"
  token: "${HA_TOKEN}"

devices:
  "living room lights":
    entity_id: "light.living_room"
    domain: "light"
  "bedroom lights":
    entity_id: "light.bedroom"
    domain: "light"
  "thermostat":
    entity_id: "climate.main"
    domain: "climate"
  "tv":
    entity_id: "media_player.living_room_tv"
    domain: "media_player"
```

**Requirements to add:**
```
homeassistant==0.2.5   # or just use httpx directly
```

**Success criteria:**
- `pytest tests/test_ha.py -v` → all pass (mocked HA)
- "Hola JARVIS, enciende las luces del salón" → lights turn on
- "JARVIS, pon la temperatura a 22 grados" → thermostat set to 22°C
- Success rate > 95% for mapped devices

**Commit message:**
```
feat(ha): Phase 4 complete — Home Assistant device control
```

---

## Phase 5 — Advanced Hologram UI (Three.js)

**Goal:** Iron Man JARVIS-style 3D holographic interface at 60 FPS.

**Files to create/modify:**
- `frontend/src/components/HologramView3D.tsx` — Three.js sphere + rings
- `frontend/src/components/SystemMonitor.tsx` — CPU/GPU/memory metrics
- `frontend/src/hooks/useSystemMetrics.ts` — poll backend for metrics
- `backend/api/metrics_endpoint.py` — HTTP endpoint for system metrics
- Modify `frontend/src/App.tsx` — replace CSS hologram with 3D version
- Modify `frontend/package.json` — add three, @react-three/fiber, @react-three/drei

**Three.js hologram design:**
- Central glowing sphere with pulsing shader material
- 3 orbital rings at different inclinations (animated rotation)
- Particle field background (starfield effect)
- Color state machine: idle=blue, listening=green, thinking=amber, speaking=cyan, error=red
- `<Canvas>` from React Three Fiber wrapping all 3D elements
- Falls back to CSS version if WebGL unavailable

**System metrics:**
- Backend exposes `GET /metrics` → `{cpu_pct, ram_pct, gpu_vram_used_gb, gpu_vram_total_gb, uptime_s}`
- Frontend polls every 5s via useSystemMetrics hook
- SystemMonitor shows circular gauges + uptime counter

**Dependencies to add:**
```json
"three": "^0.166.0",
"@react-three/fiber": "^8.17.0",
"@react-three/drei": "^9.109.0"
```

**Key tasks:**
1. Add `psutil` + `gputil` to backend, create `/metrics` HTTP endpoint
2. Create `useSystemMetrics` hook (polls `/metrics` every 5s)
3. Create `SystemMonitor` component (4 gauges: CPU, RAM, VRAM used/total)
4. Create `HologramView3D` component
5. Create WebGL fallback detection
6. Replace `HologramView` with `HologramView3D` in `App.tsx`
7. Add Three.js deps to `package.json`

**Requirements to add:**
```
psutil==6.0.0
gputil==1.4.0
```

**Success criteria:**
- `npm run build` succeeds (no TypeScript errors)
- 60 FPS in Chrome/Firefox on dev machine
- Hologram color changes correctly with system state
- System metrics update every 5 seconds
- Works on 1080p + 1440p resolutions

**Commit message:**
```
feat(ui): Phase 5 complete — Three.js hologram UI + system metrics
```

---

## Phase 6 — Testing & Optimization

**Goal:** 70%+ code coverage, stable < 3s latency, no memory leaks over 24h.

**Files to create:**
- `tests/integration/test_audio_pipeline.py` — audio → ASR → trigger integration
- `tests/integration/test_llm_pipeline.py` — trigger → LLM → TTS integration
- `tests/integration/test_end_to_end.py` — full pipeline mock test
- `tests/conftest.py` — shared fixtures
- `scripts/benchmark.py` — latency benchmarking script
- `scripts/stress_test.py` — 100-turn stress test

**Key tasks:**

1. **conftest.py fixtures**
   - `mock_audio_utterance` — 2-second PCM silence fixture
   - `mock_whisper_response` — fixture returning `("hola jarvis que hora es", "es")`
   - `mock_ollama_response` — fixture returning `"It is 14:35."`
   - `mock_kokoro_audio` — fixture returning minimal WAV bytes

2. **Integration test: audio pipeline**
   ```python
   async def test_audio_to_trigger(mock_audio, mock_whisper):
       # AudioInput → WhisperASR → TriggerDetector
       # Verify: trigger fires correctly on "hola jarvis"
   ```

3. **Integration test: LLM pipeline**
   ```python
   async def test_trigger_to_response(mock_ollama):
       # TriggerDetector → LLMManager → TTSManager
       # Verify: response is non-empty string < 500 chars
   ```

4. **End-to-end test**
   ```python
   async def test_full_turn(mock_everything):
       # Inject utterance → verify LLM response + TTS bytes produced
       # Verify: WebSocket emits "transcript", "response" events
   ```

5. **Latency benchmark** (`scripts/benchmark.py`)
   - Runs 20 simulated turns
   - Measures: ASR time, LLM time, TTS time, total
   - Reports: mean, p50, p95, p99

6. **Coverage report**
   ```bat
   pytest tests/ --cov=backend --cov-report=html --cov-report=term-missing
   ```
   Target: 70%+ overall

7. **Memory leak check**
   - Run backend for 100 turns
   - Monitor RSS with psutil
   - Assert RSS growth < 100 MB

**Requirements to add:**
```
pytest-benchmark==4.0.0
memory-profiler==0.61.0
```

**Success criteria:**
- `pytest tests/ --cov=backend` → 70%+ coverage
- `python scripts/benchmark.py` → p95 latency < 3s
- 100-turn stress test: no crashes, RSS growth < 100MB
- All 5 test files (audio/whisper/trigger/llm/tts) still pass

**Commit message:**
```
feat(testing): Phase 6 complete — 70%+ coverage, latency benchmarks
```

---

## Phase 7 — Deployment & Monitoring

**Goal:** Production-ready deployment: Docker Compose prod, systemd service, Prometheus metrics, Grafana dashboards, 99.5%+ uptime.

**Files to create:**
- `deployment/docker-compose.prod.yml` — production variant
- `deployment/Dockerfile.frontend` — multi-stage React build
- `deployment/systemd/cyrus.service` — systemd unit file
- `deployment/nginx.conf` — reverse proxy
- `backend/api/prometheus_metrics.py` — Prometheus exporter
- `deployment/grafana/dashboards/cyrus.json` — Grafana dashboard
- `deployment/grafana/provisioning/` — datasources + dashboard config
- `docs/DEPLOYMENT.md` — complete deployment guide
- `docs/TROUBLESHOOTING.md` — common issues

**Key tasks:**

1. **Prometheus metrics endpoint** (`/metrics`)
   - Counters: `cyrus_turns_total`, `cyrus_errors_total`
   - Histograms: `cyrus_asr_duration_seconds`, `cyrus_llm_duration_seconds`, `cyrus_tts_duration_seconds`
   - Gauges: `cyrus_active_connections`, `cyrus_gpu_vram_used_bytes`

2. **Production Docker Compose** (`docker-compose.prod.yml`)
   - Adds: `prometheus` service (port 9090)
   - Adds: `grafana` service (port 3001)
   - Adds: `nginx` reverse proxy (port 80/443)
   - Uses: production-built frontend image
   - Enables: health checks on all services
   - Sets: `restart: always`

3. **Dockerfile.frontend** (multi-stage)
   ```dockerfile
   FROM node:20-alpine AS build
   WORKDIR /app
   COPY frontend/ .
   RUN npm ci && npm run build

   FROM nginx:alpine
   COPY --from=build /app/dist /usr/share/nginx/html
   COPY deployment/nginx.conf /etc/nginx/nginx.conf
   ```

4. **Systemd service** (`cyrus.service`)
   ```ini
   [Unit]
   Description=JARVIS Cognitive System
   After=network.target ollama.service

   [Service]
   Type=simple
   User=cyrus
   WorkingDirectory=/opt/cyrus
   ExecStart=/opt/cyrus/venv/bin/python -m backend.core.cyrus_engine
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

5. **Grafana dashboard panels:**
   - Request rate (turns/min)
   - Error rate (%)
   - Latency breakdown (ASR / LLM / TTS)
   - GPU VRAM usage
   - Active WebSocket connections
   - System uptime

6. **Health check endpoint** (`GET /health`)
   ```json
   {"status": "ok", "ollama": true, "whisper_loaded": true, "tts_ready": true, "uptime_seconds": 3600}
   ```

**Requirements to add:**
```
prometheus-client==0.20.0
```

**Success criteria:**
- `docker-compose -f docker-compose.prod.yml up` → all services start
- `curl http://localhost/health` → `{"status": "ok", ...}`
- `http://localhost:9090` → Prometheus scraping metrics
- `http://localhost:3001` → Grafana dashboard showing live data
- `systemctl start cyrus` → service starts on Linux
- Uptime > 99.5% over 24h test

**Commit message:**
```
feat(deploy): Phase 7 complete — production deployment + monitoring
```

---

## Master Commit Strategy

After each phase:
1. Run `pytest tests/ -v` — must be green
2. Commit with descriptive message
3. Tag the release: `git tag v1.0-phase-N`
4. Push to remote: `git push && git push --tags`

## Final Push to Remote

```bat
:: Add remote (do once)
git remote add origin https://github.com/YOUR_USERNAME/cyrus.git

:: Push all phases
git push -u origin main
git push --tags
```
