# C.Y.R.U.S — Quick Start

> Asume Python 3.11, Node.js 18+ y Ollama ya instalados.
> Para instalación desde cero ver [INSTALLATION.md](INSTALLATION.md).

---

## 1. Entorno Python

```bat
cd D:\Archivos\Desarrollo\C.Y.R.U.S

py -3.11 -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
copy config\.env.example .env
```

---

## 2. Modelo LLM (una sola vez, ~4 GB)

```bat
ollama pull phi3:latest
```

---

## 3. Arrancar todo

### Opción A — Script unificado (recomendado)

Abre **2 terminales**:

**Terminal 1 — Ollama**
```bat
ollama serve
```

**Terminal 2 — Todo lo demás** (mata procesos previos, levanta limpio)
```bat
REM TTS + backend CYRUS  (modo por defecto)
start_services.bat

REM Todo: TTS + ASR + Vision + Embedder + backend + frontend
start_services.bat all

REM Solo los que necesites + backend
start_services.bat tts asr

REM Todo sin frontend
start_services.bat all nofrontend
```

El script abre una ventana CMD por servicio (`CYRUS TTS :8020`, `CYRUS BACKEND :8765`, etc.)  
y hace health-check automático al terminar.

**Apagar todo de golpe:**
```bat
stop_services.bat
```

---

### Opción B — Manual

**Terminal 1 — Ollama**
```bat
ollama serve
```

**Terminal 2 — TTS Server (puerto 8020)**
```bat
venv\Scripts\activate
python -m uvicorn services.tts_server.main:app --host 0.0.0.0 --port 8020
```

**Terminal 3 — Backend CYRUS**
```bat
venv\Scripts\activate
python -m backend.core.cyrus_engine
```

**Terminal 4 — Frontend React**
```bat
cd frontend && npm run dev
```

Abre **http://localhost:3007** en el navegador.

---

## 4. Comandos de línea de comandos

### Ver procesos activos de C.Y.R.U.S
```bat
:: Todos los procesos Python relacionados
tasklist /fi "imagename eq python.exe" /v | findstr /i "cyrus uvicorn ollama"

:: Puertos en uso (8020 TTS, 8000 ASR, 8765 WebSocket, 11434 Ollama)
netstat -ano | findstr "8020 8000 8765 11434 3007"

:: Quién ocupa un puerto específico (ejemplo: 8020)
netstat -ano | findstr ":8020"
for /f "tokens=5" %a in ('netstat -ano ^| findstr ":8020 "') do tasklist /fi "pid eq %a" /fo list | findstr "PID\|Image"
```

### PowerShell (alternativa más legible)
```powershell
# Procesos Python + puerto que usan
Get-Process python | Select-Object Id, Name, CPU, @{n='Mem(MB)';e={[math]::Round($_.WorkingSet64/1MB,1)}}

# Ver qué escucha en cada puerto de CYRUS
@(8020, 8000, 8002, 8765, 11434, 3007) | ForEach-Object {
    $conn = Get-NetTCPConnection -LocalPort $_ -ErrorAction SilentlyContinue
    if ($conn) { "Puerto $_ -> PID $($conn.OwningProcess)" }
    else { "Puerto $_ -> libre" }
}

# Matar un puerto específico (ejemplo: liberar 8020)
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8020).OwningProcess -Force
```

### Salud de los servicios
```bat
:: TTS Server
curl http://localhost:8020/health

:: ASR Server
curl http://localhost:8000/health

:: Embedder Server
curl http://localhost:8002/health

:: Ollama
curl http://localhost:11434/api/version

:: WebSocket backend (verifica que responde)
curl http://localhost:8765
```

### Logs en tiempo real
```bat
:: Backend principal
type logs\cyrus.log

:: Seguir el log en vivo (PowerShell)
Get-Content logs\cyrus.log -Wait -Tail 50
```

---

## 5. Habilitar servicios remotos en config.yaml

```yaml
# config/config.yaml

services:
  tts:
    enabled: true          # usa TTS Server (puerto 8020) en lugar de Kokoro in-process
    host: http://localhost:8020
    language: es
    speaker: ""

  asr:
    enabled: true          # usa ASR Server (puerto 8000) en lugar de Whisper in-process
    host: http://localhost:8000
    language: es

  embedder:
    enabled: false         # habilitar cuando quieras memoria semántica remota
    host: http://localhost:8002

  vision:
    enabled: false         # habilitar con servidor de vision corriendo
    host: http://localhost:8001
```

---

## 6. Algo no funciona

| Problema | Solución |
|----------|----------|
| Sin respuesta de voz | Verifica que TTS Server corre: `curl http://localhost:8020/health` |
| Ollama offline | Corre `ollama serve` en otra terminal |
| Puerto ocupado | `stop_services.bat` — libera los 4 puertos de golpe |
| Whisper lento en CPU | Normal — ASR Server lo resuelve (carga el modelo una sola vez) |
| WebSocket no conecta | Backend no está corriendo — revisa Terminal 2 |
| Frontend no carga | Corre `npm run dev` en `frontend/` |

---

*Para instalación completa desde cero ver [INSTALLATION.md](INSTALLATION.md).*
*Arquitectura de microservicios ver [SERVICES_PLAN.md](SERVICES_PLAN.md).*
