# JARVIS — Microservices Architecture Plan

Objetivo: sacar los módulos pesados de ML del proceso principal y correrlos como
servicios HTTP independientes. El agente los llama por API — igual que ya llama a
Ollama. Cada servicio tiene su propio entorno Python, sus propias dependencias y
puede correr en otra máquina del LAN (Proxmox, HA, etc.).

```
┌──────────────────────────────────────────────────────┐
│                   JARVIS CORE                     │
│  AudioInput → ASR → LLM → TTS → AudioOutput         │
│       ↑ clients (HTTP/WS)                            │
└──┬───────┬──────┬──────┬──────────────────────────── ┘
   │       │      │      │
   ▼       ▼      ▼      ▼
 [TTS]  [ASR]  [VIS]  [EMB]   ← servicios independientes
  :8020  :8000  :8001  :8002
```

---

## Fase 1 — TTS Server ✅ COMPLETADO + EN PRODUCCION (2026-04-16)

**Servicio:** `xtts-api-server`
**Puerto:** `8020`
**Config:** `services.tts.enabled: true`

### Servidor propio (activo)
```bash
# Desde la raíz del proyecto — usa Kokoro (ya instalado)
python -m uvicorn services.tts_server.main:app --host 0.0.0.0 --port 8020
# o doble-click en services/tts_server/start.bat
```
> **Nota XTTS v2:** el servidor soporta XTTS v2 opcionalmente.
> Requiere Visual Studio C++ Build Tools + `pip install xtts-api-server`.

### Integración en JARVIS
- Nuevo backend: `backend/modules/tts/remote_tts.py` (`RemoteTTS`)
- Cadena TTS: Piper → **RemoteTTS** → XTTS (in-process) → Kokoro → Edge-TTS
- `set_tts_engine "remote-tts"` para forzar desde frontend

### Config
```yaml
services:
  tts:
    enabled: false
    host: http://localhost:8020
    language: es
    speaker: ""       # nombre del speaker o ruta a WAV de referencia
    timeout: 60
```

---

## Fase 2 — ASR Server ✅ IMPLEMENTADO (2026-04-16)

**Servicio:** `faster-whisper-server` (compatible OpenAI `/v1/audio/transcriptions`)
**Puerto:** `8000`
**Config:** `services.asr.enabled: true`

### Servidor propio (activo)
```bash
# faster-whisper ya instalado — servidor custom en services/asr_server/
python -m uvicorn services.asr_server.main:app --host 0.0.0.0 --port 8000
# o doble-click en services/asr_server/start.bat
```

### Integración planeada
- Nuevo cliente: `backend/modules/asr/remote_asr.py` (`RemoteASR`)
- Interface: `POST /v1/audio/transcriptions` (multipart WAV)
- Cuando habilitado reemplaza `WhisperASR` in-process
- Ventaja: Whisper cargado una vez, no bloquea el loop del engine

### Config
```yaml
services:
  asr:
    enabled: false
    host: http://localhost:8000
    model: large-v3    # modelo que corre el servidor
    language: es
    timeout: 30
```

---

## Fase 3 — Vision Server ✅ IMPLEMENTADO (2026-04-16)

**Servicio:** FastAPI custom con YOLO + DeepFace
**Puerto:** `8001`
**Config:** `services.vision.enabled: true`

### Integración planeada
- Servidor: `services/vision_server/main.py`
- Endpoint: `POST /analyze` → `{frame_b64}` → `{objects, faces}`
- Nuevo cliente: `backend/modules/vision/remote_vision.py` (`RemoteVision`)
- Reemplaza `VisionManager` in-process cuando habilitado
- Compatible con fuente Frigate (el servidor llama a Frigate directamente)

### Config
```yaml
services:
  vision:
    enabled: false
    host: http://localhost:8001
    timeout: 10
```

---

## Fase 4 — Embedder Server ✅ IMPLEMENTADO (2026-04-16)

**Servicio:** FastAPI custom con sentence-transformers
**Puerto:** `8002`
**Config:** `services.embedder.enabled: true`

### Integración planeada
- Servidor: `services/embedder_server/main.py`
- Endpoint: `POST /embed` → `{text}` → `{vector}`
- Nuevo cliente: `backend/modules/memory/remote_embedder.py` (`RemoteEmbedder`)
- Reemplaza `Embedder` in-process
- Qdrant ya corre como servicio standalone (Docker)

### Config
```yaml
services:
  embedder:
    enabled: false
    host: http://localhost:8002
    timeout: 10
```

---

## Notas de arquitectura

- Todos los clientes remotos tienen `available` property (lazy health check)
- Fallback automático al módulo in-process si el servidor no responde
- Los servidores corren en envs Python separados → cero conflictos de deps
- Cada servicio puede correr en una VM Proxmox con GPU passthrough
- LLM ya es microservicio (Ollama en `:11434`) — patrón consolidado

## Estado

| Fase | Módulo       | Estado     | Fecha      |
|------|--------------|------------|------------|
| 1    | TTS Server    | ✅ Producción | 2026-04-16 |
| 2    | ASR Server    | ✅ Listo      | 2026-04-16 |
| 3    | Vision Server | ✅ Listo      | 2026-04-16 |
| 4    | Embedder      | ✅ Listo      | 2026-04-16 |
