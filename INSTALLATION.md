# C.Y.R.U.S — Guía de Instalación

**Cognitive sYstem for Real-time Utility & Services**

---

## Requisitos

### Software

| Requisito | Versión | Notas |
|-----------|---------|-------|
| Python | 3.11.x | No usar 3.12+ (compatibilidad de paquetes) |
| Node.js | 18+ | Para el frontend React |
| npm | 9+ | Incluido con Node.js |
| Ollama | latest | Inferencia LLM local |
| espeak-ng | any | Requerido por Kokoro TTS |

### Hardware recomendado

- Micrófono USB
- Altavoces o auriculares
- GPU NVIDIA con CUDA (para Whisper ASR acelerado)
  - RTX 2070S o mejor recomendado
  - Fallback a CPU disponible (más lento)

---

## Paso 1 — Dependencias del sistema

### Python 3.11

Descarga desde [python.org](https://python.org). Durante la instalación:
- Marcar **"Add Python to PATH"**

```bat
py -3.11 --version
```

### Node.js 18+

Descarga desde [nodejs.org](https://nodejs.org). Elegir la versión LTS.

```bat
node --version && npm --version
```

### Ollama

Descarga desde [ollama.ai](https://ollama.ai). Después:

```bat
ollama serve
:: En otra terminal:
ollama pull phi3:latest
```

### espeak-ng (para Kokoro TTS)

Descarga el instalador para Windows desde
[espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases).

```bat
espeak-ng --version
```

---

## Paso 2 — Clonar el repositorio

```bat
git clone <repo-url> D:\Archivos\Desarrollo\C.Y.R.U.S
cd D:\Archivos\Desarrollo\C.Y.R.U.S
```

---

## Paso 3 — Backend Python

```bat
py -3.11 -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Paso 4 — Configuración

```bat
copy config\.env.example .env
```

Edita `.env`:

```dotenv
# Solo necesario para modo HYBRID (fallback a Claude API)
CLAUDE_API_KEY=sk-ant-...
```

En `config/config.yaml` puedes ajustar:
- `local.llm.model` — modelo Ollama a usar
- `local.tts.voice` — voz de Kokoro
- `asr.model` — tamaño de Whisper (tiny/base/small/medium/large)
- `services.*` — habilitar microservicios (ver sección Microservicios)

---

## Paso 5 — Frontend

```bat
cd frontend
npm install
cd ..
```

---

## Paso 6 — Verificar instalación

```bat
venv\Scripts\activate
pytest tests/ -v
```

Salida esperada: `46 passed, 6 skipped` (los 6 skipped requieren hardware real).

---

## Paso 7 — Arrancar C.Y.R.U.S

### Modo mínimo (3 terminales)

```bat
:: Terminal 1
ollama serve

:: Terminal 2
venv\Scripts\activate && python -m backend.core.cyrus_engine

:: Terminal 3
cd frontend && npm run dev
```

### Modo completo con microservicios (5 terminales)

```bat
:: Terminal 1 — LLM
ollama serve

:: Terminal 2 — TTS Server (síntesis remota, mejor latencia)
venv\Scripts\activate
python -m uvicorn services.tts_server.main:app --host 0.0.0.0 --port 8020

:: Terminal 3 — ASR Server (transcripción remota, Whisper cargado una vez)
venv\Scripts\activate
python -m uvicorn services.asr_server.main:app --host 0.0.0.0 --port 8000

:: Terminal 4 — Backend principal
venv\Scripts\activate
python -m backend.core.cyrus_engine

:: Terminal 5 — Frontend
cd frontend && npm run dev
```

Luego habilitar en `config/config.yaml`:
```yaml
services:
  tts:
    enabled: true
    host: http://localhost:8020
  asr:
    enabled: true
    host: http://localhost:8000
```

Abrir **http://localhost:5173**

---

## Microservicios — Arquitectura

C.Y.R.U.S separa los módulos pesados de ML en servicios HTTP independientes.
Cada servicio tiene su propio proceso y puede correr en otra máquina del LAN.

```
C.Y.R.U.S Core (backend principal)
  ├── LLM          → Ollama          :11434  (siempre externo)
  ├── TTS Server   → services/tts    :8020   (Kokoro / Piper / XTTS v2)
  ├── ASR Server   → services/asr    :8000   (faster-whisper)
  ├── Vision Server→ services/vision :8001   (YOLO + DeepFace)
  └── Embedder     → services/embed  :8002   (sentence-transformers)
```

| Servicio | Puerto | Estado | Arranque |
|----------|--------|--------|----------|
| Ollama (LLM) | 11434 | Siempre activo | `ollama serve` |
| TTS Server | 8020 | Recomendado | `services\tts_server\start.bat` |
| ASR Server | 8000 | Recomendado | `services\asr_server\start.bat` |
| Embedder | 8002 | Opcional (memoria) | `services\embedder_server\start.bat` |
| Vision | 8001 | Opcional | `services\vision_server\start.bat` |

Ver detalles en [SERVICES_PLAN.md](SERVICES_PLAN.md).

---

## Comandos de diagnóstico

```bat
:: Ver todos los procesos activos de C.Y.R.U.S
tasklist /fi "imagename eq python.exe" /v

:: Ver puertos en uso
netstat -ano | findstr "8020 8000 8002 8765 11434 5173"

:: Salud de los servicios
curl http://localhost:8020/health
curl http://localhost:8000/health
curl http://localhost:8002/health

:: Matar un puerto (ejemplo 8020)
for /f "tokens=5" %a in ('netstat -ano ^| findstr ":8020 "') do taskkill /pid %a /f
```

```powershell
# PowerShell — estado de todos los puertos CYRUS
@(8020, 8000, 8002, 8765, 11434, 5173) | ForEach-Object {
    $c = Get-NetTCPConnection -LocalPort $_ -ErrorAction SilentlyContinue
    if ($c) { "ACTIVO  :$_ -> PID $($c.OwningProcess)" } else { "libre   :$_" }
}
```

---

## Solución de problemas

### Sin respuesta de voz
- Verifica TTS Server: `curl http://localhost:8020/health`
- Si no corre, arranca `services\tts_server\start.bat`

### Ollama offline
- Corre `ollama serve` en otra terminal
- Verifica: `curl http://localhost:11434/api/version`

### PyAudio / webrtcvad no instalan
```
error: Microsoft Visual C++ 14.0 is required
```
Instala [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).

### Puerto ocupado
```bat
netstat -ano | findstr ":8020"
taskkill /pid <PID> /f
```

### Whisper lento en CPU
- Normal si no hay CUDA. Activa ASR Server para cargar el modelo una sola vez.
- O cambia en `config.yaml`: `asr.device: cpu` y `asr.compute_type: int8`

### XTTS v2 no disponible
- Requiere Visual Studio C++ Build Tools + `pip install xtts-api-server`
- Alternativa: el TTS Server ya usa Kokoro (calidad similar, sin compilación)

---

## Referencia de VRAM (RTX 2070S)

| Estado | VRAM usada |
|--------|-----------|
| Ollama idle | ~2.0 GB |
| Whisper TINY activo | +1.5 GB |
| phi3 7B inferencia | +2.5 GB |
| **Peak** | **~4.0 GB** |

Margen seguro: 4 GB libres de 8 GB totales.

---

## Estructura del proyecto

```
C.Y.R.U.S/
├── backend/              Backend Python principal
│   ├── api/              WebSocket server
│   ├── core/             Engine + config + state
│   └── modules/          audio, asr, llm, tts, vision, memory
├── services/             Microservicios independientes
│   ├── tts_server/       TTS HTTP API (puerto 8020)
│   ├── asr_server/       ASR HTTP API (puerto 8000)
│   ├── vision_server/    Vision HTTP API (puerto 8001)
│   └── embedder_server/  Embedder HTTP API (puerto 8002)
├── frontend/             React + Three.js (UI holográfica)
├── config/               config.yaml, soul.md, prompts.yaml
├── data/                 Faces DB, conversaciones SQLite
├── models/               Modelos TTS (Piper .onnx)
├── logs/                 Logs de runtime (auto-creado)
├── tests/                Suite pytest
├── SERVICES_PLAN.md      Arquitectura de microservicios
├── QUICK_START.md        Arranque rápido
└── INSTALLATION.md       Esta guía
```

---

*Para arranque rápido ver [QUICK_START.md](QUICK_START.md).*
*Arquitectura de servicios ver [SERVICES_PLAN.md](SERVICES_PLAN.md).*
