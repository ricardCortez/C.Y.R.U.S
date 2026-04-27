# JARVIS v1.1 — Mejoras Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar launcher inteligente, audio pipeline mejorado (eco + noise gate + speaker gate), y ParticleNetwork visual completo con presets configurables.

**Architecture:** Tres sub-proyectos independientes en secuencia. Launcher = Python stdlib puro. Audio = migración PyAudio→sounddevice con capas de filtrado. Visual = reestructura Three.js con geometría de 3 capas + sistema de presets en store global.

**Tech Stack:** Python 3.11 stdlib (launcher), sounddevice + WebRTC VAD (audio), Three.js + GLSL + Zustand (visual).

---

## ═══════════════════════════════════════
## SUB-PROYECTO 1 — Launcher inteligente
## ═══════════════════════════════════════

### Task 1.1: Preparar archivos base y .gitignore

**Files:**
- Modify: `.gitignore`
- Create: `launch.bat`

- [ ] **Step 1: Agregar `.jarvis_launcher_state` al .gitignore**

```bash
echo .jarvis_launcher_state >> .gitignore
```

- [ ] **Step 2: Crear `launch.bat`**

Contenido exacto de `launch.bat`:
```bat
@echo off
cd /d "%~dp0"
python launch.py %*
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore launch.bat
git commit -m "chore: add launch.bat wrapper and gitignore launcher state"
```

---

### Task 1.2: Crear `launch.py` — núcleo (colores, hashing, estado)

**Files:**
- Create: `launch.py`

- [ ] **Step 1: Crear `launch.py` con helpers de color, hash y estado**

```python
#!/usr/bin/env python3
"""JARVIS — Smart Launcher.

Installs deps, starts services in order, waits for all to be healthy,
then opens the browser. Uses only Python stdlib — no venv required to run.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / ".jarvis_launcher_state"

# ── ANSI colors (Windows 10+ supports them) ──────────────────────────────────
def _ansi(code: str) -> str:
    return f"\033[{code}m"

OK    = _ansi("32")   # green
WARN  = _ansi("33")   # yellow
ERR   = _ansi("31")   # red
INFO  = _ansi("36")   # cyan
DIM   = _ansi("2")    # dim
BOLD  = _ansi("1")    # bold
RESET = _ansi("0")

def ok(msg: str)   -> None: print(f"  {OK}[✓]{RESET} {msg}")
def warn(msg: str) -> None: print(f"  {WARN}[!]{RESET} {msg}")
def err(msg: str)  -> None: print(f"  {ERR}[✗]{RESET} {msg}")
def info(msg: str) -> None: print(f"  {INFO}[↑]{RESET} {msg}")
def dim(msg: str)  -> None: print(f"  {DIM}    {msg}{RESET}")

def banner() -> None:
    print()
    print(f"  {BOLD}┌─────────────────────────────────────┐{RESET}")
    print(f"  {BOLD}│  JARVIS  —  INICIANDO SISTEMA   │{RESET}")
    print(f"  {BOLD}└─────────────────────────────────────┘{RESET}")
    print()

# ── State (hash cache) ────────────────────────────────────────────────────────
def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}

def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

# ── Health checks ─────────────────────────────────────────────────────────────
def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False

def tcp_ok(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False

def wait_for_http(url: str, label: str, timeout: int = 120) -> bool:
    """Poll url every 2s until it responds or timeout. Returns True on success."""
    print(f"  {INFO}[↑]{RESET} {label:<16}", end="", flush=True)
    start = time.monotonic()
    dots = 0
    while time.monotonic() - start < timeout:
        if http_ok(url):
            elapsed = int(time.monotonic() - start)
            print(f" {OK}OK{RESET} ({elapsed}s)")
            return True
        print(".", end="", flush=True)
        dots += 1
        time.sleep(2)
    print(f" {ERR}TIMEOUT{RESET}")
    return False

def wait_for_tcp(host: str, port: int, label: str, timeout: int = 120) -> bool:
    """Poll TCP port every 2s until open or timeout. Returns True on success."""
    print(f"  {INFO}[↑]{RESET} {label:<16}", end="", flush=True)
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if tcp_ok(host, port):
            elapsed = int(time.monotonic() - start)
            print(f" {OK}OK{RESET} ({elapsed}s)")
            return True
        print(".", end="", flush=True)
        time.sleep(2)
    print(f" {ERR}TIMEOUT{RESET}")
    return False
```

- [ ] **Step 2: Commit parcial**

```bash
git add launch.py
git commit -m "feat(launcher): add core helpers — colors, hashing, health checks"
```

---

### Task 1.3: `launch.py` — verificación de entorno e instalación

**Files:**
- Modify: `launch.py`

- [ ] **Step 1: Agregar funciones de entorno y deps al final de `launch.py`**

```python
# ── Environment checks ────────────────────────────────────────────────────────
def check_python() -> bool:
    v = sys.version_info
    if v < (3, 11):
        err(f"Python {v.major}.{v.minor} detectado — se requiere 3.11+")
        return False
    ok(f"Python {v.major}.{v.minor}.{v.micro}           encontrado")
    return True

def ensure_venv() -> bool:
    venv_activate = ROOT / "venv" / "Scripts" / "activate.bat"
    if not venv_activate.exists():
        warn("Entorno virtual no encontrado — creando...")
        result = subprocess.run(
            ["py", "-3.11", "-m", "venv", "venv"],
            cwd=ROOT, capture_output=True, text=True
        )
        if result.returncode != 0:
            err(f"No se pudo crear venv: {result.stderr.strip()}")
            return False
        ok("Entorno virtual             creado")
    else:
        ok("Entorno virtual             activo")
    return True

def install_python_deps(force: bool = False) -> bool:
    req_file = ROOT / "requirements.txt"
    if not req_file.exists():
        warn("requirements.txt no encontrado — saltando")
        return True

    state = _load_state()
    current_hash = _sha256(req_file)

    if not force and state.get("requirements_hash") == current_hash:
        ok("Deps Python                 sin cambios")
        return True

    print(f"  {WARN}[~]{RESET} Deps Python                 instalando...", flush=True)
    pip = ROOT / "venv" / "Scripts" / "pip.exe"
    result = subprocess.run(
        [str(pip), "install", "-r", str(req_file), "--quiet"],
        cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        err(f"pip install falló:\n{result.stderr[-500:]}")
        return False

    state["requirements_hash"] = current_hash
    _save_state(state)
    ok("Deps Python                 instaladas")
    return True

def install_frontend_deps(force: bool = False) -> bool:
    pkg_file = ROOT / "frontend" / "package.json"
    if not pkg_file.exists():
        warn("frontend/package.json no encontrado — saltando")
        return True

    state = _load_state()
    current_hash = _sha256(pkg_file)

    if not force and state.get("package_json_hash") == current_hash:
        ok("Deps Frontend               sin cambios")
        return True

    print(f"  {WARN}[~]{RESET} Deps Frontend               instalando...", flush=True)
    result = subprocess.run(
        ["npm", "install", "--silent"],
        cwd=ROOT / "frontend", capture_output=True, text=True, shell=True
    )
    if result.returncode != 0:
        err(f"npm install falló:\n{result.stderr[-500:]}")
        return False

    state["package_json_hash"] = current_hash
    _save_state(state)
    ok("Deps Frontend               instaladas")
    return True
```

- [ ] **Step 2: Commit**

```bash
git add launch.py
git commit -m "feat(launcher): add venv check and incremental dep installation"
```

---

### Task 1.4: `launch.py` — kill de puertos y arranque de servicios

**Files:**
- Modify: `launch.py`

- [ ] **Step 1: Agregar kill_port y funciones de arranque**

```python
# ── Kill existing processes ───────────────────────────────────────────────────
def kill_port(port: int, label: str) -> None:
    result = subprocess.run(
        ["netstat", "-ano"], capture_output=True, text=True
    )
    killed = False
    for line in result.stdout.splitlines():
        if f":{port} " in line or f":{port}\t" in line:
            parts = line.strip().split()
            if not parts:
                continue
            pid = parts[-1]
            if pid == "0":
                continue
            kill = subprocess.run(
                ["taskkill", "/pid", pid, "/f"],
                capture_output=True
            )
            if kill.returncode == 0:
                dim(f"kill {label} puerto {port}  PID {pid}")
                killed = True
    if not killed:
        dim(f"     {label} puerto {port}  libre")

def kill_all_ports() -> None:
    print()
    kill_port(8020, "TTS Server   ")
    kill_port(8765, "JARVIS Backend")
    kill_port(3007, "Frontend     ")
    kill_port(8000, "ASR Server   ")
    kill_port(8001, "Vision Server")
    kill_port(8002, "Embedder     ")
    time.sleep(1.5)

# ── Service launchers ─────────────────────────────────────────────────────────
def _python(module: str, env_extra: dict | None = None) -> subprocess.Popen:
    python_exe = ROOT / "venv" / "Scripts" / "python.exe"
    env = os.environ.copy()
    env["COQUI_TOS_AGREED"] = "1"
    if env_extra:
        env.update(env_extra)
    return subprocess.Popen(
        [str(python_exe), "-m", module],
        cwd=ROOT, env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )

def start_tts() -> subprocess.Popen:
    return _python("uvicorn services.tts_server.main:app --host 0.0.0.0 --port 8020".split()[0],
                   # uvicorn needs args passed differently
                  )

def _uvicorn(app: str, port: int) -> subprocess.Popen:
    python_exe = ROOT / "venv" / "Scripts" / "python.exe"
    env = os.environ.copy()
    env["COQUI_TOS_AGREED"] = "1"
    return subprocess.Popen(
        [str(python_exe), "-m", "uvicorn", app,
         "--host", "0.0.0.0", "--port", str(port)],
        cwd=ROOT, env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )

def _backend() -> subprocess.Popen:
    python_exe = ROOT / "venv" / "Scripts" / "python.exe"
    env = os.environ.copy()
    env["COQUI_TOS_AGREED"] = "1"
    return subprocess.Popen(
        [str(python_exe), "-m", "backend.core.cyrus_engine"],
        cwd=ROOT, env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )

def _frontend() -> subprocess.Popen:
    return subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=ROOT / "frontend",
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        shell=True
    )
```

- [ ] **Step 2: Commit**

```bash
git add launch.py
git commit -m "feat(launcher): add port kill and service launcher helpers"
```

---

### Task 1.5: `launch.py` — main() y tabla de estado final

**Files:**
- Modify: `launch.py`

- [ ] **Step 1: Agregar función `main()` al final de `launch.py`**

```python
# ── CLI flags ─────────────────────────────────────────────────────────────────
def parse_flags(argv: list[str]) -> dict:
    flags = {
        "tts": True, "asr": False, "vision": False,
        "embedder": False, "frontend": True, "install_only": False,
        "force_install": False,
    }
    if not argv:
        return flags
    # Reset service defaults when explicit flags given
    has_service_flag = any(
        a in ("all", "tts", "asr", "vision", "embedder", "noui")
        for a in argv
    )
    if has_service_flag:
        flags["tts"] = False
        flags["frontend"] = True

    for arg in argv:
        if arg == "all":
            flags.update(tts=True, asr=True, vision=True, embedder=True)
        elif arg == "tts":       flags["tts"] = True
        elif arg == "asr":       flags["asr"] = True
        elif arg == "vision":    flags["vision"] = True
        elif arg == "embedder":  flags["embedder"] = True
        elif arg == "noui":      flags["frontend"] = False
        elif arg == "install-only": flags["install_only"] = True
        elif arg == "reinstall": flags["force_install"] = True
    return flags

# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    # Enable ANSI on Windows
    os.system("")

    flags = parse_flags(sys.argv[1:])
    banner()

    # 1. Environment
    if not check_python():
        return 1
    if not ensure_venv():
        return 1

    # 2. Dependencies
    force = flags["force_install"]
    if not install_python_deps(force=force):
        return 1
    if flags["frontend"] and not install_frontend_deps(force=force):
        return 1

    if flags["install_only"]:
        ok("Instalación completada.")
        return 0

    # 3. Kill existing
    print(f"\n  {DIM}Liberando puertos...{RESET}")
    kill_all_ports()

    # 4. Start services
    print()
    procs: list[subprocess.Popen] = []
    failed = False

    if flags["tts"]:
        procs.append(_uvicorn("services.tts_server.main:app", 8020))
        if not wait_for_http("http://localhost:8020/health", "TTS Server  :8020"):
            warn("TTS no respondió — el backend puede funcionar sin él")

    if flags["asr"]:
        procs.append(_uvicorn("services.asr_server.main:app", 8000))
        if not wait_for_http("http://localhost:8000/health", "ASR Server  :8000"):
            warn("ASR no respondió")

    if flags["vision"]:
        procs.append(_uvicorn("services.vision_server.main:app", 8001))
        if not wait_for_http("http://localhost:8001/health", "Vision      :8001"):
            warn("Vision no respondió")

    if flags["embedder"]:
        procs.append(_uvicorn("services.embedder_server.main:app", 8002))
        if not wait_for_http("http://localhost:8002/health", "Embedder    :8002"):
            warn("Embedder no respondió")

    # Backend always required
    procs.append(_backend())
    if not wait_for_tcp("localhost", 8765, "Backend     :8765"):
        err("Backend no arrancó — abortando")
        return 1

    if flags["frontend"]:
        procs.append(_frontend())
        if not wait_for_http("http://localhost:3007", "Frontend    :3007"):
            warn("Frontend no respondió")

    # 5. Summary
    print()
    print(f"  {DIM}{'─' * 38}{RESET}")
    print(f"  {OK}{BOLD}Sistema listo → abriendo navegador...{RESET}")
    print(f"  {DIM}{'─' * 38}{RESET}")
    print()

    if flags["frontend"]:
        time.sleep(1)
        webbrowser.open("http://localhost:3007")

    print(f"  {DIM}Presiona Ctrl+C en las consolas de servicio para detener.{RESET}\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Probar el launcher (sin reiniciar servicios reales)**

```bash
python launch.py install-only
```
Resultado esperado: imprime banner, verifica Python, activa venv, chequea hashes, sale con `[✓] Instalación completada.`

- [ ] **Step 3: Commit**

```bash
git add launch.py
git commit -m "feat(launcher): complete smart launcher with health-wait and browser open"
```

---

## ═══════════════════════════════════════
## SUB-PROYECTO 2 — Audio Pipeline mejorado
## ═══════════════════════════════════════

### Task 2.1: Config — agregar parámetros de audio nuevos

**Files:**
- Modify: `config/config.yaml`

- [ ] **Step 1: Agregar parámetros bajo `audio.input`**

En `config/config.yaml`, en la sección `audio.input`, agregar las 3 líneas nuevas:

```yaml
audio:
  input:
    device: Cloud Flight S Chat
    sample_rate: 16000
    chunk_size: 1024
    channels: 1
    format: int16
    silence_threshold: 400
    silence_duration: 1.5
    noise_gate_factor: 3.5          # umbral = noise_floor × factor
    noise_calibration_secs: 2.0     # segundos de grabación para calibrar
    speaker_gate_enabled: true      # false = deshabilitar verificación aunque haya perfil
```

- [ ] **Step 2: Actualizar `config_manager.py` para leer los nuevos campos**

Buscar la clase/dataclass de audio input en `backend/core/config_manager.py` y agregar los 3 campos:

```python
# Dentro del dataclass / SimpleNamespace de AudioInputConfig:
noise_gate_factor: float = 3.5
noise_calibration_secs: float = 2.0
speaker_gate_enabled: bool = True
```

Verificar con:
```bash
cd D:\Archivos\Desarrollo\JARVIS
venv\Scripts\python -c "from backend.core.config_manager import load_config; c = load_config(); print(c.audio.input.noise_gate_factor)"
```
Resultado esperado: `3.5`

- [ ] **Step 3: Commit**

```bash
git add config/config.yaml backend/core/config_manager.py
git commit -m "feat(audio): add noise gate and speaker gate config params"
```

---

### Task 2.2: Migrar `AudioInput` de PyAudio a sounddevice

**Files:**
- Modify: `backend/modules/audio/audio_input.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Eliminar PyAudio de requirements.txt**

En `requirements.txt`, eliminar la línea:
```
PyAudio==0.2.14
```
`sounddevice==0.4.6` ya está en el archivo — no agregar de nuevo.

- [ ] **Step 2: Reemplazar el `__init__` de `AudioInput`**

Reemplazar el bloque de imports y `__init__` completo:

```python
"""
JARVIS — Microphone capture with VAD, noise gate, and speaker gate.

Uses sounddevice (WASAPI shared mode on Windows) to eliminate mic monitoring
echo. Adds adaptive noise floor calibration and optional speaker verification.
"""
from __future__ import annotations

import io
import threading
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

from backend.modules.audio.vad_detector import VADDetector
from backend.utils.exceptions import AudioInputError
from backend.utils.logger import get_logger

logger = get_logger("jarvis.audio.input")

_SpeakerProfile = None


class AudioInput:
    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        channels: int = 1,
        silence_duration: float = 1.5,
        silence_threshold: int = 400,
        device_name: str = "default",
        noise_gate_factor: float = 3.5,
        noise_calibration_secs: float = 2.0,
        speaker_gate_enabled: bool = True,
    ) -> None:
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size
        self._channels = channels
        self._silence_frames = int(sample_rate / chunk_size * silence_duration)
        self._silence_threshold = silence_threshold
        self._device_name = device_name
        self._noise_gate_factor = noise_gate_factor
        self._noise_calibration_secs = noise_calibration_secs
        self._speaker_gate_enabled = speaker_gate_enabled

        self._device_index: Optional[int] = None
        self._vad = VADDetector(sample_rate=sample_rate, aggressiveness=3)
        self._stop_flag = threading.Event()
        self._muted_until: float = 0.0
        self._voice_profile = None

        # Noise gate — calibrated at open()
        self._noise_floor: float = 0.0
        self._last_speech_at: float = 0.0   # for auto-recalibration
        self._RECALIB_IDLE_SECS: float = 300.0  # 5 min

    # ── WASAPI settings helper ────────────────────────────────────────────
    @staticmethod
    def _wasapi_settings() -> Optional[object]:
        try:
            return sd.WasapiSettings(exclusive=False, auto_convert=True)
        except Exception:
            return None   # non-Windows or PortAudio without WASAPI
```

- [ ] **Step 3: Reemplazar `open()`, `close()`, y `_resolve_device()`**

```python
    def open(self) -> None:
        self._device_index = self._resolve_device()
        logger.info(f"[JARVIS] AudioInput: opened device index={self._device_index}")
        self._calibrate_noise_floor()

    def close(self) -> None:
        logger.info("[JARVIS] AudioInput: closed")

    def __enter__(self) -> "AudioInput":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _resolve_device(self) -> Optional[int]:
        if self._device_name in ("default", ""):
            return None
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if (self._device_name.lower() in dev["name"].lower()
                    and dev["max_input_channels"] > 0):
                logger.info(f"[JARVIS] AudioInput: matched '{dev['name']}' at index {i}")
                return i
        logger.warning(
            f"[JARVIS] AudioInput: device '{self._device_name}' not found; using default"
        )
        return None

    def list_devices(self) -> list[dict]:
        return [
            {"index": i, "name": d["name"]}
            for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0
        ]
```

- [ ] **Step 4: Agregar calibración de noise floor**

```python
    def _calibrate_noise_floor(self, duration: Optional[float] = None) -> None:
        secs = duration or self._noise_calibration_secs
        n_frames = int(self._sample_rate * secs)
        logger.info(f"[JARVIS] AudioInput: calibrating noise floor ({secs:.1f}s)…")
        try:
            wasapi = self._wasapi_settings()
            kwargs: dict = dict(
                samplerate=self._sample_rate,
                channels=self._channels,
                dtype="int16",
                blocksize=self._chunk_size,
                device=self._device_index,
            )
            if wasapi is not None:
                kwargs["extra_settings"] = wasapi
            with sd.InputStream(**kwargs) as stream:
                data, _ = stream.read(n_frames)
            pcm = data.tobytes()
            self._noise_floor = self._rms(pcm)
            logger.info(f"[JARVIS] AudioInput: noise floor = {self._noise_floor:.1f} RMS")
        except Exception as exc:
            logger.warning(f"[JARVIS] AudioInput: calibration failed ({exc}) — using config threshold")
            self._noise_floor = 0.0

    @property
    def _effective_threshold(self) -> float:
        """Dynamic threshold = max(config, noise_floor × gate_factor)."""
        gate = self._noise_floor * self._noise_gate_factor
        return max(self._silence_threshold, gate)
```

- [ ] **Step 5: Reemplazar `_record_sync` usando sounddevice**

```python
    def request_stop(self) -> None:
        self._stop_flag.set()

    def mute_for(self, seconds: float) -> None:
        self._muted_until = time.monotonic() + seconds
        logger.debug(f"[JARVIS] AudioInput: muted for {seconds:.1f}s")

    def set_voice_profile(self, profile: object) -> None:
        self._voice_profile = profile
        logger.info("[JARVIS] AudioInput: voice profile attached")

    def verify_speaker(self, pcm: bytes) -> bool:
        """Returns True if pcm matches enrolled voice, or no profile exists."""
        if not self._speaker_gate_enabled or self._voice_profile is None:
            return True
        return self._voice_profile.is_match(pcm)

    async def record_utterance(self) -> bytes:
        if True:  # always open (no persistent pa object)
            pass
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._record_sync)

    def _record_sync(self) -> bytes:
        # Auto-recalibrate if idle too long
        now = time.monotonic()
        if (self._last_speech_at > 0
                and now - self._last_speech_at > self._RECALIB_IDLE_SECS):
            self._calibrate_noise_floor(duration=1.0)
            self._last_speech_at = now  # reset so we don't loop

        threshold = self._effective_threshold
        wasapi = self._wasapi_settings()
        kwargs: dict = dict(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
            blocksize=self._chunk_size,
            device=self._device_index,
        )
        if wasapi is not None:
            kwargs["extra_settings"] = wasapi

        try:
            stream = sd.InputStream(**kwargs)
            stream.start()
        except Exception as exc:
            raise AudioInputError(f"[JARVIS] Cannot open microphone: {exc}") from exc

        logger.debug("[JARVIS] AudioInput: listening for speech…")
        self._vad.reset()
        self._stop_flag.clear()
        frames: list[bytes] = []
        silence_count = 0
        speech_started = False
        pre_roll: list[bytes] = []
        max_pre_roll = int(self._sample_rate / self._chunk_size * 0.3)

        try:
            while True:
                if self._stop_flag.is_set():
                    self._stop_flag.clear()
                    break

                raw, overflowed = stream.read(self._chunk_size)
                data = raw.tobytes()
                is_speech = self._vad.feed(data)
                rms = self._rms(data)

                if not speech_started:
                    pre_roll.append(data)
                    if len(pre_roll) > max_pre_roll:
                        pre_roll.pop(0)

                if time.monotonic() < self._muted_until:
                    continue

                if is_speech and rms > threshold:
                    if not speech_started:
                        speech_started = True
                        frames.extend(pre_roll)
                        self._last_speech_at = time.monotonic()
                        logger.debug("[JARVIS] AudioInput: speech onset")
                    silence_count = 0
                    frames.append(data)
                elif speech_started:
                    frames.append(data)
                    silence_count += 1
                    if silence_count >= self._silence_frames:
                        break
        finally:
            stream.stop()
            stream.close()

        return b"".join(frames)

    @staticmethod
    def _rms(pcm: bytes) -> float:
        arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        if arr.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(arr ** 2)))

    def pcm_to_wav(self, pcm: bytes) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm)
        return buf.getvalue()
```

- [ ] **Step 6: Reemplazar `_detect_onset_sync` usando sounddevice**

```python
    async def detect_speech_onset(self, timeout: float = 30.0) -> bool:
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._detect_onset_sync),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return False

    def _detect_onset_sync(self) -> bool:
        barge_rms = self._effective_threshold * 2.0
        CONSECUTIVE_REQUIRED = 4
        consecutive = 0
        collected: list[bytes] = []
        vad = VADDetector(sample_rate=self._sample_rate, aggressiveness=3, speech_ratio=0.85)

        wasapi = self._wasapi_settings()
        kwargs: dict = dict(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
            blocksize=self._chunk_size,
            device=self._device_index,
        )
        if wasapi is not None:
            kwargs["extra_settings"] = wasapi

        try:
            stream = sd.InputStream(**kwargs)
            stream.start()
        except Exception as exc:
            logger.warning(f"[JARVIS] AudioInput: barge-in stream failed: {exc}")
            return False

        try:
            while True:
                if self._stop_flag.is_set():
                    return False
                raw, _ = stream.read(self._chunk_size)
                data = raw.tobytes()

                if time.monotonic() < self._muted_until:
                    consecutive = 0
                    collected.clear()
                    continue

                is_speech = vad.feed(data)
                rms = self._rms(data)

                if is_speech and rms > barge_rms:
                    consecutive += 1
                    collected.append(data)
                    if consecutive >= CONSECUTIVE_REQUIRED:
                        if self._voice_profile is not None:
                            if not self._voice_profile.is_match(b"".join(collected)):
                                consecutive = 0
                                collected.clear()
                                vad.reset()
                                continue
                        return True
                else:
                    if consecutive > 0:
                        consecutive -= 1
                    if consecutive == 0:
                        collected.clear()
        finally:
            stream.stop()
            stream.close()
```

- [ ] **Step 7: Verificar que el módulo importa sin errores**

```bash
venv\Scripts\python -c "from backend.modules.audio.audio_input import AudioInput; print('OK')"
```
Resultado esperado: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/modules/audio/audio_input.py requirements.txt
git commit -m "feat(audio): migrate AudioInput to sounddevice WASAPI, add noise gate and speaker verification"
```

---

### Task 2.3: Conectar parámetros nuevos en el engine y speaker gate en pipeline

**Files:**
- Modify: `backend/core/cyrus_engine.py`

- [ ] **Step 1: Pasar nuevos params al constructor de AudioInput**

En `cyrus_engine.py`, en el bloque `__init__` donde se crea `self._audio_in`, agregar los 3 nuevos parámetros:

```python
        ai_cfg = self._cfg.audio.input
        self._audio_in = AudioInput(
            sample_rate=ai_cfg.sample_rate,
            chunk_size=ai_cfg.chunk_size,
            channels=ai_cfg.channels,
            silence_duration=ai_cfg.silence_duration,
            silence_threshold=ai_cfg.silence_threshold,
            device_name=ai_cfg.device,
            noise_gate_factor=getattr(ai_cfg, "noise_gate_factor", 3.5),
            noise_calibration_secs=getattr(ai_cfg, "noise_calibration_secs", 2.0),
            speaker_gate_enabled=getattr(ai_cfg, "speaker_gate_enabled", True),
        )
```

- [ ] **Step 2: Agregar speaker gate en `_process_one_turn` justo antes del ASR**

En `_process_one_turn`, después del bloque `if not pcm: return` y antes de la sección `# 2. Transcribe`, insertar:

```python
        # Speaker gate — discard if voice doesn't match enrolled profile
        if not self._audio_in.verify_speaker(pcm):
            logger.debug("[JARVIS] Speaker gate: voice mismatch — discarding utterance")
            await self._state.set_status(SystemStatus.LISTENING)
            await asyncio.sleep(0.05)
            return
```

- [ ] **Step 3: Verificar arranque del backend**

```bash
venv\Scripts\python -m backend.core.cyrus_engine &
# Esperar 5 segundos y verificar en logs:
# "[JARVIS] AudioInput: calibrating noise floor"
# "[JARVIS] AudioInput: noise floor = XX.X RMS"
```

- [ ] **Step 4: Commit**

```bash
git add backend/core/cyrus_engine.py
git commit -m "feat(audio): wire noise gate params and speaker gate into engine pipeline"
```

---

## ═══════════════════════════════════════
## SUB-PROYECTO 3 — ParticleNetwork Visual
## ═══════════════════════════════════════

### Task 3.1: Crear tipos de presets y actualizar el store

**Files:**
- Create: `frontend/src/types/presets.ts`
- Modify: `frontend/src/store/useJARVISStore.ts`

- [ ] **Step 1: Crear `frontend/src/types/presets.ts`**

```typescript
// frontend/src/types/presets.ts

export type VisualPresetId = 'neural' | 'holographic' | 'cyber' | 'organic' | 'monochrome'

export interface PresetPalette {
  node:       [number, number, number]   // RGB 0–1
  connection: [number, number, number]
  pulse:      [number, number, number]
  nucleus:    [number, number, number]   // núcleo interno
}

export interface PresetConfig {
  id:              VisualPresetId
  name:            string
  palette:         PresetPalette
  rotSpeedMult:    number   // multiplier over per-state base speed
  pulseDensity:    number   // multiplier over per-state spawn rate
  glowIntensity:   number   // 0.0–2.0
  connectionWidth: number   // multiplier over base line width
  gridOverlay:     boolean  // subtle grid lines (holographic style)
}

export const PRESETS: Record<VisualPresetId, PresetConfig> = {
  neural: {
    id: 'neural', name: 'Neural',
    palette: {
      node:       [0.75, 0.90, 1.00],
      connection: [0.30, 0.70, 1.00],
      pulse:      [0.00, 1.00, 0.85],
      nucleus:    [0.50, 0.80, 1.00],
    },
    rotSpeedMult: 1.0, pulseDensity: 1.0,
    glowIntensity: 1.0, connectionWidth: 1.0, gridOverlay: false,
  },
  holographic: {
    id: 'holographic', name: 'Holographic',
    palette: {
      node:       [0.20, 1.00, 0.60],
      connection: [0.00, 0.80, 0.50],
      pulse:      [0.60, 1.00, 0.80],
      nucleus:    [0.10, 0.90, 0.55],
    },
    rotSpeedMult: 0.9, pulseDensity: 0.8,
    glowIntensity: 1.4, connectionWidth: 0.8, gridOverlay: true,
  },
  cyber: {
    id: 'cyber', name: 'Cyber',
    palette: {
      node:       [1.00, 0.55, 0.10],
      connection: [0.90, 0.35, 0.05],
      pulse:      [1.00, 0.80, 0.00],
      nucleus:    [1.00, 0.30, 0.00],
    },
    rotSpeedMult: 1.5, pulseDensity: 1.8,
    glowIntensity: 1.6, connectionWidth: 1.4, gridOverlay: false,
  },
  organic: {
    id: 'organic', name: 'Organic',
    palette: {
      node:       [0.75, 0.55, 1.00],
      connection: [0.55, 0.35, 0.90],
      pulse:      [0.90, 0.70, 1.00],
      nucleus:    [0.65, 0.40, 0.95],
    },
    rotSpeedMult: 0.6, pulseDensity: 0.7,
    glowIntensity: 0.8, connectionWidth: 0.7, gridOverlay: false,
  },
  monochrome: {
    id: 'monochrome', name: 'Mono',
    palette: {
      node:       [1.00, 1.00, 1.00],
      connection: [0.70, 0.70, 0.70],
      pulse:      [1.00, 1.00, 1.00],
      nucleus:    [0.85, 0.85, 0.85],
    },
    rotSpeedMult: 1.0, pulseDensity: 1.0,
    glowIntensity: 1.2, connectionWidth: 1.0, gridOverlay: false,
  },
}
```

- [ ] **Step 2: Agregar `visualPreset` al store en `useJARVISStore.ts`**

En la interface `JARVISStore`, agregar después de `orbSpeed`:
```typescript
  visualPreset: VisualPresetId
  setVisualPreset: (p: VisualPresetId) => void
```

En el import al inicio del archivo agregar:
```typescript
import type { VisualPresetId } from '../types/presets'
```

En el objeto de estado inicial, agregar:
```typescript
  visualPreset: 'neural' as VisualPresetId,
```

En las acciones, agregar:
```typescript
  setVisualPreset: (p) => set({ visualPreset: p }),
```

- [ ] **Step 3: Verificar que TypeScript compila**

```bash
cd frontend && npx tsc --noEmit
```
Resultado esperado: sin errores.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/presets.ts frontend/src/store/useJARVISStore.ts
git commit -m "feat(visual): add VisualPreset types and store integration"
```

---

### Task 3.2: Reescribir `ParticleNetwork.tsx` — geometría de 3 capas

**Files:**
- Modify: `frontend/src/components/ParticleNetwork.tsx`

> Esta tarea reemplaza completamente el archivo. Hacerlo en un solo paso para evitar estado intermedio roto.

- [ ] **Step 1: Reemplazar el archivo completo con la nueva implementación**

```typescript
// frontend/src/components/ParticleNetwork.tsx
//
// JARVIS — Neural Network Visualizer v2
// — 3-layer volumetric geometry (cortex / gray matter / nucleus)
// — 3 connection types (local / hemispheric / long axon)
// — WebGL shaders with volumetric glow and pulse gradients
// — 5 visual presets with smooth transitions
// — Dramatic per-state behaviors

import { useEffect, useRef }                          from 'react'
import * as THREE                                      from 'three'
import { useJARVISStore, SystemState }                  from '../store/useJARVISStore'
import { AudioAnalyserHandle }                         from '../hooks/useAudioAnalyser'
import { PRESETS, PresetConfig, VisualPresetId }       from '../types/presets'

// ── Constants ─────────────────────────────────────────────────────────────────

const TOTAL_NODES  = 400
const MAX_PULSES   = 200
const LERP_FRAMES  = 60

const LAYERS = [
  { fraction: 0.40, radius: 100, label: 'cortex'  },
  { fraction: 0.35, radius: 72,  label: 'gray'    },
  { fraction: 0.25, radius: 45,  label: 'nucleus' },
]

// Connection type weights
const CONN_LOCAL = 0.80
const CONN_HEMI  = 0.15
// CONN_AXON = 0.05 (remainder)

const TARGET_CONNECTIONS = 1800

// ── Per-state parameters ──────────────────────────────────────────────────────

interface StateParams {
  rotSpeed:   number
  connAngle:  number
  brightness: number
  pulseAmt:   number
  spawnRate:  number
  cascadeMode: 'nucleus' | 'cortex' | 'radial' | 'random' | 'erratic'
}

const STATE_PARAMS: Record<SystemState, StateParams> = {
  offline:      { rotSpeed: 0.0006, connAngle: 0.60, brightness: 0.40, pulseAmt: 0,    spawnRate: 0.003, cascadeMode: 'random'   },
  connected:    { rotSpeed: 0.0010, connAngle: 0.70, brightness: 0.60, pulseAmt: 0,    spawnRate: 0.008, cascadeMode: 'random'   },
  idle:         { rotSpeed: 0.0012, connAngle: 0.72, brightness: 0.65, pulseAmt: 0.15, spawnRate: 0.020, cascadeMode: 'nucleus'  },
  listening:    { rotSpeed: 0.0022, connAngle: 0.88, brightness: 1.10, pulseAmt: 0.60, spawnRate: 0.060, cascadeMode: 'cortex'   },
  transcribing: { rotSpeed: 0.0028, connAngle: 0.90, brightness: 1.15, pulseAmt: 0.50, spawnRate: 0.070, cascadeMode: 'cortex'   },
  thinking:     { rotSpeed: 0.0048, connAngle: 0.94, brightness: 1.40, pulseAmt: 0.70, spawnRate: 0.130, cascadeMode: 'nucleus'  },
  speaking:     { rotSpeed: 0.0032, connAngle: 0.92, brightness: 1.25, pulseAmt: 0.80, spawnRate: 0.090, cascadeMode: 'radial'   },
  error:        { rotSpeed: 0.0030, connAngle: 0.65, brightness: 1.00, pulseAmt: 0.30, spawnRate: 0.030, cascadeMode: 'erratic'  },
}

// ── GLSL — Nodes (volumetric glow) ───────────────────────────────────────────

const NODE_VERT = /* glsl */`
  attribute float aSize;
  attribute float aGlow;
  attribute float aLayer;     // 0=cortex, 1=gray, 2=nucleus
  varying   float vGlow;
  varying   float vDepth;
  varying   float vLayer;
  void main() {
    vGlow  = aGlow;
    vLayer = aLayer;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vDepth  = clamp((-mv.z - 30.0) / 320.0, 0.0, 1.0);
    float depthFade = 1.0 - vDepth * 0.6;
    gl_PointSize = aSize * (380.0 / -mv.z) * (1.0 + aGlow * 2.5) * depthFade;
    gl_Position  = projectionMatrix * mv;
  }
`

const NODE_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform vec3  uNucleusColor;
  uniform float uBright;
  varying float vGlow;
  varying float vDepth;
  varying float vLayer;

  void main() {
    vec2  uv   = gl_PointCoord - 0.5;
    float d    = length(uv);
    if (d > 0.5) discard;

    // Core + halo (volumetric glow)
    float core  = 1.0 - smoothstep(0.0, 0.18, d);
    float halo  = (1.0 - smoothstep(0.15, 0.50, d)) * 0.5;
    float shape = core + halo * (0.5 + vGlow);

    float depthFade = 1.0 - vDepth * 0.55;
    float alpha     = shape * uBright * (0.6 + vGlow * 1.4) * depthFade;

    // Nucleus nodes tinted differently
    vec3  col = mix(uColor, uNucleusColor, step(1.5, vLayer));
    gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0));
  }
`

// ── GLSL — Connections (gradient pulse) ──────────────────────────────────────

const EDGE_VERT = /* glsl */`
  attribute float aT;         // 0.0 at start node, 1.0 at end node
  attribute float aConnType;  // 0=local, 1=hemi, 2=axon
  attribute float aBaseAlpha;
  varying   float vT;
  varying   float vConnType;
  varying   float vBaseAlpha;
  varying   float vDepth;
  void main() {
    vT         = aT;
    vConnType  = aConnType;
    vBaseAlpha = aBaseAlpha;
    vec4 mv    = modelViewMatrix * vec4(position, 1.0);
    vDepth     = clamp((-mv.z - 30.0) / 320.0, 0.0, 1.0);
    gl_Position = projectionMatrix * mv;
  }
`

const EDGE_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform vec3  uPulseColor;
  uniform float uBright;
  uniform float uPulsePos;    // -1 = no pulse on this connection
  uniform float uPulseWidth;
  varying float vT;
  varying float vConnType;
  varying float vBaseAlpha;
  varying float vDepth;

  void main() {
    float depthFade = 1.0 - vDepth * 0.65;

    float pulse = 0.0;
    if (uPulsePos >= 0.0) {
      float dist = abs(vT - uPulsePos);
      pulse = smoothstep(uPulseWidth, 0.0, dist);
    }

    float typeBoost = (vConnType > 0.5) ? 1.4 : 1.0;  // hemi + axon brighter
    float alpha = (vBaseAlpha + pulse * 0.7) * uBright * depthFade * typeBoost;
    vec3  col   = mix(uColor, uPulseColor, pulse * 0.8);
    gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0));
  }
`

// ── GLSL — Grid overlay (holographic preset) ──────────────────────────────────

const GRID_VERT = /* glsl */`
  void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`
const GRID_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform float uAlpha;
  void main() { gl_FragColor = vec4(uColor, uAlpha * 0.12); }
`

// ── Types ─────────────────────────────────────────────────────────────────────

interface NodeData {
  x: number; y: number; z: number
  layer: number    // 0=cortex,1=gray,2=nucleus
  hemisphere: number   // 0 or 1 (split by x sign)
}

interface ConnectionData {
  a: number; b: number
  type: number   // 0=local, 1=hemi, 2=axon
  baseAlpha: number
}

interface Pulse {
  connIdx: number
  t: number       // 0→1 position along connection
  speed: number
  active: boolean
}

// ── Geometry builders ─────────────────────────────────────────────────────────

function buildNodes(): NodeData[] {
  const nodes: NodeData[] = []
  for (const [li, layer] of LAYERS.entries()) {
    const count = Math.floor(TOTAL_NODES * layer.fraction)
    // Fibonacci sphere for uniform coverage
    const goldenAngle = Math.PI * (1 + Math.sqrt(5))
    for (let i = 0; i < count; i++) {
      const theta  = Math.acos(1 - 2 * (i + 0.5) / count)
      const phi    = goldenAngle * (i + 0.5)
      const jitter = 1 + (Math.random() - 0.5) * 0.16
      const r      = layer.radius * jitter
      const x = Math.sin(theta) * Math.cos(phi) * r
      const y = Math.cos(theta) * r
      const z = Math.sin(theta) * Math.sin(phi) * r
      nodes.push({ x, y, z, layer: li, hemisphere: x >= 0 ? 0 : 1 })
    }
  }
  return nodes
}

function buildConnections(nodes: NodeData[]): ConnectionData[] {
  const N = nodes.length
  const conns: ConnectionData[] = []
  const localTarget = Math.floor(TARGET_CONNECTIONS * CONN_LOCAL)
  const hemiTarget  = Math.floor(TARGET_CONNECTIONS * CONN_HEMI)
  const axonTarget  = TARGET_CONNECTIONS - localTarget - hemiTarget

  const dist2 = (a: NodeData, b: NodeData) =>
    (a.x-b.x)**2 + (a.y-b.y)**2 + (a.z-b.z)**2

  // LOCAL — same layer, nearby
  let attempts = 0
  while (conns.length < localTarget && attempts < localTarget * 8) {
    attempts++
    const a = Math.floor(Math.random() * N)
    const b = Math.floor(Math.random() * N)
    if (a === b) continue
    if (nodes[a].layer !== nodes[b].layer) continue
    const d2 = dist2(nodes[a], nodes[b])
    const maxD2 = (50)**2
    if (d2 > maxD2) continue
    conns.push({ a, b, type: 0, baseAlpha: 0.30 + Math.random() * 0.15 })
  }

  // HEMISPHERIC — opposite hemisphere, same or adjacent layer
  attempts = 0
  const hemiStart = conns.length
  while (conns.length - hemiStart < hemiTarget && attempts < hemiTarget * 8) {
    attempts++
    const a = Math.floor(Math.random() * N)
    const b = Math.floor(Math.random() * N)
    if (a === b) continue
    if (nodes[a].hemisphere === nodes[b].hemisphere) continue
    const layerDiff = Math.abs(nodes[a].layer - nodes[b].layer)
    if (layerDiff > 1) continue
    conns.push({ a, b, type: 1, baseAlpha: 0.45 + Math.random() * 0.20 })
  }

  // LONG AXON — different layers (cortex↔nucleus skips gray)
  attempts = 0
  const axonStart = conns.length
  while (conns.length - axonStart < axonTarget && attempts < axonTarget * 8) {
    attempts++
    const a = Math.floor(Math.random() * N)
    const b = Math.floor(Math.random() * N)
    if (a === b) continue
    if (Math.abs(nodes[a].layer - nodes[b].layer) < 2) continue
    conns.push({ a, b, type: 2, baseAlpha: 0.18 + Math.random() * 0.10 })
  }

  return conns
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props { analyser?: AudioAnalyserHandle }

export function ParticleNetwork({ analyser }: Props) {
  const mountRef     = useRef<HTMLDivElement>(null)
  const systemState  = useJARVISStore(s => s.systemState)
  const bloomIntensity = useJARVISStore(s => s.bloomIntensity)
  const visualPreset = useJARVISStore(s => s.visualPreset)

  const stateRef     = useRef(systemState)
  const bloomRef     = useRef(bloomIntensity)
  const presetRef    = useRef<VisualPresetId>(visualPreset)
  const analyserRef  = useRef(analyser)

  useEffect(() => { stateRef.current  = systemState   }, [systemState])
  useEffect(() => { bloomRef.current  = bloomIntensity }, [bloomIntensity])
  useEffect(() => { presetRef.current = visualPreset  }, [visualPreset])
  useEffect(() => { analyserRef.current = analyser    }, [analyser])

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const W = mount.clientWidth  || window.innerWidth
    const H = mount.clientHeight || window.innerHeight

    const scene    = new THREE.Scene()
    const camera   = new THREE.PerspectiveCamera(60, W / H, 0.1, 2000)
    camera.position.set(0, 0, 280)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(W, H)
    renderer.setClearColor(0x000000, 0)
    renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;'
    mount.appendChild(renderer.domElement)

    // ── Build geometry ────────────────────────────────────────────────────
    const nodeData = buildNodes()
    const connData = buildConnections(nodeData)
    const N = nodeData.length
    const C = connData.length

    // ── Node buffers ──────────────────────────────────────────────────────
    const positions  = new Float32Array(N * 3)
    const sizes      = new Float32Array(N)
    const glows      = new Float32Array(N)
    const baseGlow   = new Float32Array(N)
    const nodeLayer  = new Float32Array(N)
    const nodeFlash  = new Float32Array(N)

    for (let i = 0; i < N; i++) {
      const nd = nodeData[i]
      positions[i*3]   = nd.x
      positions[i*3+1] = nd.y
      positions[i*3+2] = nd.z
      nodeLayer[i]     = nd.layer
      const isHub     = Math.random() < (nd.layer === 2 ? 0.30 : 0.12)
      const layerSize = nd.layer === 2 ? 1.6 : nd.layer === 1 ? 1.2 : 1.0
      sizes[i]        = (isHub ? 7.0 + Math.random() * 4.0 : 2.5 + Math.random() * 2.5) * layerSize
      baseGlow[i]     = isHub ? 0.7 + Math.random() * 0.3 : 0.05
      glows[i]        = baseGlow[i]
    }

    const ptGeo = new THREE.BufferGeometry()
    ptGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const sizeAttr  = new THREE.BufferAttribute(sizes, 1);  sizeAttr.setUsage(THREE.DynamicDrawUsage)
    const glowAttr  = new THREE.BufferAttribute(glows, 1);  glowAttr.setUsage(THREE.DynamicDrawUsage)
    const layerAttr = new THREE.BufferAttribute(nodeLayer, 1)
    ptGeo.setAttribute('aSize', sizeAttr)
    ptGeo.setAttribute('aGlow', glowAttr)
    ptGeo.setAttribute('aLayer', layerAttr)

    const ptMat = new THREE.ShaderMaterial({
      vertexShader: NODE_VERT, fragmentShader: NODE_FRAG,
      uniforms: {
        uColor:       { value: new THREE.Color(0.75, 0.90, 1.0) },
        uNucleusColor:{ value: new THREE.Color(0.50, 0.80, 1.0) },
        uBright:      { value: 0.9 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const points = new THREE.Points(ptGeo, ptMat)
    scene.add(points)

    // ── Connection buffers ────────────────────────────────────────────────
    // Each connection = 2 vertices. We store per-vertex attributes.
    const edgePositions = new Float32Array(C * 2 * 3)
    const edgeT         = new Float32Array(C * 2)
    const edgeType      = new Float32Array(C * 2)
    const edgeAlpha     = new Float32Array(C * 2)

    for (let ci = 0; ci < C; ci++) {
      const { a, b, type, baseAlpha } = connData[ci]
      const na = nodeData[a], nb = nodeData[b]
      const vi = ci * 6
      edgePositions[vi]   = na.x; edgePositions[vi+1] = na.y; edgePositions[vi+2] = na.z
      edgePositions[vi+3] = nb.x; edgePositions[vi+4] = nb.y; edgePositions[vi+5] = nb.z
      edgeT[ci*2]     = 0.0;  edgeT[ci*2+1]     = 1.0
      edgeType[ci*2]  = type; edgeType[ci*2+1]  = type
      edgeAlpha[ci*2] = baseAlpha; edgeAlpha[ci*2+1] = baseAlpha
    }

    const edgeGeo = new THREE.BufferGeometry()
    edgeGeo.setAttribute('position', new THREE.BufferAttribute(edgePositions, 3))
    edgeGeo.setAttribute('aT',        new THREE.BufferAttribute(edgeT, 1))
    edgeGeo.setAttribute('aConnType', new THREE.BufferAttribute(edgeType, 1))
    edgeGeo.setAttribute('aBaseAlpha',new THREE.BufferAttribute(edgeAlpha, 1))

    // We create one LineSegments object — pulses are driven by uniform per draw call.
    // For individual pulse positions we use instanced approach: one material per active pulse
    // group would be complex; instead we encode pulses into a texture (simpler: per-conn float).
    // Practical approach: update a Float32Array of pulse positions per connection each frame.
    const pulsePosAttr = new Float32Array(C * 2).fill(-1.0)
    const pulsePosBuffer = new THREE.BufferAttribute(pulsePosAttr, 1)
    pulsePosBuffer.setUsage(THREE.DynamicDrawUsage)
    edgeGeo.setAttribute('aPulsePos', pulsePosBuffer)

    const edgeMat = new THREE.ShaderMaterial({
      vertexShader: `
        attribute float aT;
        attribute float aConnType;
        attribute float aBaseAlpha;
        attribute float aPulsePos;
        varying float vT;
        varying float vConnType;
        varying float vBaseAlpha;
        varying float vPulsePos;
        varying float vDepth;
        void main() {
          vT = aT; vConnType = aConnType; vBaseAlpha = aBaseAlpha; vPulsePos = aPulsePos;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vDepth = clamp((-mv.z - 30.0) / 320.0, 0.0, 1.0);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: `
        uniform vec3  uColor;
        uniform vec3  uPulseColor;
        uniform float uBright;
        uniform float uPulseWidth;
        varying float vT;
        varying float vConnType;
        varying float vBaseAlpha;
        varying float vPulsePos;
        varying float vDepth;
        void main() {
          float depthFade = 1.0 - vDepth * 0.60;
          float pulse = 0.0;
          if (vPulsePos >= 0.0) {
            float dist = abs(vT - vPulsePos);
            pulse = smoothstep(uPulseWidth, 0.0, dist);
          }
          float typeBoost = (vConnType > 0.5) ? 1.35 : 1.0;
          float alpha = (vBaseAlpha + pulse * 0.65) * uBright * depthFade * typeBoost;
          vec3  col   = mix(uColor, uPulseColor, pulse * 0.8);
          gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0));
        }
      `,
      uniforms: {
        uColor:      { value: new THREE.Color(0.30, 0.70, 1.0) },
        uPulseColor: { value: new THREE.Color(0.00, 1.00, 0.85) },
        uBright:     { value: 0.85 },
        uPulseWidth: { value: 0.08 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const lines = new THREE.LineSegments(edgeGeo, edgeMat)
    scene.add(lines)

    // ── Grid overlay (holographic) ────────────────────────────────────────
    const gridSize = 220
    const gridStep = 22
    const gridPoints: number[] = []
    for (let x = -gridSize; x <= gridSize; x += gridStep) {
      gridPoints.push(x, -gridSize, -60, x, gridSize, -60)
    }
    for (let y = -gridSize; y <= gridSize; y += gridStep) {
      gridPoints.push(-gridSize, y, -60, gridSize, y, -60)
    }
    const gridGeo = new THREE.BufferGeometry()
    gridGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(gridPoints), 3))
    const gridMat = new THREE.ShaderMaterial({
      vertexShader: GRID_VERT, fragmentShader: GRID_FRAG,
      uniforms: {
        uColor: { value: new THREE.Color(0.20, 1.00, 0.60) },
        uAlpha: { value: 0.0 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const gridLines = new THREE.LineSegments(gridGeo, gridMat)
    scene.add(gridLines)

    // ── Pulse state ───────────────────────────────────────────────────────
    const pulses: Pulse[] = Array.from({ length: MAX_PULSES }, () => ({
      connIdx: 0, t: 0, speed: 0, active: false
    }))

    // connToPulseT: maps connection index → current pulse T (−1 if none)
    const connToPulseT = new Float32Array(C).fill(-1.0)

    function spawnPulse(state: SystemState, preset: PresetConfig): void {
      const sp = STATE_PARAMS[state]
      const p  = pulses.find(p => !p.active)
      if (!p) return

      let ci: number
      const cascadeMode = sp.cascadeMode
      if (cascadeMode === 'nucleus') {
        // Prefer axon (type=2) or hemi (type=1) from nucleus layer
        const candidates = connData
          .map((c, i) => ({ c, i }))
          .filter(({ c }) => nodeData[c.a].layer === 2 || nodeData[c.b].layer === 2)
        ci = candidates.length
          ? candidates[Math.floor(Math.random() * candidates.length)].i
          : Math.floor(Math.random() * C)
      } else if (cascadeMode === 'cortex') {
        const candidates = connData
          .map((c, i) => ({ c, i }))
          .filter(({ c }) => nodeData[c.a].layer === 0 || nodeData[c.b].layer === 0)
        ci = candidates.length
          ? candidates[Math.floor(Math.random() * candidates.length)].i
          : Math.floor(Math.random() * C)
      } else if (cascadeMode === 'erratic') {
        ci = Math.floor(Math.random() * C)
      } else {
        ci = Math.floor(Math.random() * C)
      }

      p.connIdx = ci
      p.t       = 0
      p.speed   = (0.008 + Math.random() * 0.012) * preset.pulseDensity
      p.active  = true
    }

    // ── Preset lerp state ─────────────────────────────────────────────────
    let currentPalette = { ...PRESETS['neural'].palette }
    let targetPresetId = presetRef.current
    let lerpT = 1.0  // 1.0 = fully at target

    function lerp3(a: [number,number,number], b: [number,number,number], t: number): [number,number,number] {
      return [a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, a[2]+(b[2]-a[2])*t]
    }

    // ── Animation loop ────────────────────────────────────────────────────
    let frame = 0
    let rafId = 0

    function animate(): void {
      rafId = requestAnimationFrame(animate)
      frame++

      const state   = stateRef.current
      const sp      = STATE_PARAMS[state]
      const bloom   = bloomRef.current
      const pid     = presetRef.current

      // Preset transition
      if (pid !== targetPresetId) {
        targetPresetId = pid
        lerpT = 0.0
      }
      if (lerpT < 1.0) {
        lerpT = Math.min(1.0, lerpT + 1.0 / LERP_FRAMES)
      }
      const preset   = PRESETS[targetPresetId]
      const prevPreset = PRESETS[
        Object.keys(PRESETS).find(k => k !== targetPresetId) as VisualPresetId ?? 'neural'
      ]
      // Simple lerp: lerp from current cached palette to target
      const nodePal  = lerp3(currentPalette.node,       preset.palette.node,       lerpT)
      const connPal  = lerp3(currentPalette.connection, preset.palette.connection, lerpT)
      const pulsePal = lerp3(currentPalette.pulse,      preset.palette.pulse,      lerpT)
      const nuclPal  = lerp3(currentPalette.nucleus,    preset.palette.nucleus,    lerpT)
      if (lerpT >= 1.0) currentPalette = { ...preset.palette }

      // Update uniforms
      ptMat.uniforms.uColor.value.setRGB(...nodePal)
      ptMat.uniforms.uNucleusColor.value.setRGB(...nuclPal)
      ptMat.uniforms.uBright.value = sp.brightness * bloom * preset.glowIntensity
      edgeMat.uniforms.uColor.value.setRGB(...connPal)
      edgeMat.uniforms.uPulseColor.value.setRGB(...pulsePal)
      edgeMat.uniforms.uBright.value = sp.brightness * bloom * preset.glowIntensity
      gridMat.uniforms.uColor.value.setRGB(...connPal)
      gridMat.uniforms.uAlpha.value = preset.gridOverlay ? 1.0 : 0.0

      // Rotate
      const rotSpeed = sp.rotSpeed * preset.rotSpeedMult
      points.rotation.y += rotSpeed
      lines.rotation.y  += rotSpeed
      gridLines.rotation.y = points.rotation.y * 0.15

      // Spawn pulses
      if (Math.random() < sp.spawnRate * preset.pulseDensity) {
        spawnPulse(state, preset)
      }
      // Extra idle nucleus pulses — the brain never sleeps
      if (state === 'idle' && Math.random() < 0.008) {
        spawnPulse('idle', preset)
      }

      // Advance pulses + update connToPulseT
      connToPulseT.fill(-1.0)
      const glowArr = glowAttr.array as Float32Array
      // Decay all node glows
      for (let i = 0; i < N; i++) {
        nodeFlash[i] = Math.max(0, nodeFlash[i] - 0.03)
        glowArr[i]   = baseGlow[i] + nodeFlash[i]
      }

      for (const p of pulses) {
        if (!p.active) continue
        p.t += p.speed
        if (p.t > 1.0) {
          // Flash arrival node
          const arrNode = connData[p.connIdx].b
          nodeFlash[arrNode] = Math.min(1.5, nodeFlash[arrNode] + 0.8)
          p.active = false
          connToPulseT[p.connIdx] = -1.0
          continue
        }
        connToPulseT[p.connIdx] = p.t
      }

      // Write pulse positions into edge attribute (per vertex: same value for both verts)
      const pArr = pulsePosBuffer.array as Float32Array
      for (let ci = 0; ci < C; ci++) {
        pArr[ci*2]   = connToPulseT[ci]
        pArr[ci*2+1] = connToPulseT[ci]
      }
      pulsePosBuffer.needsUpdate = true
      glowAttr.needsUpdate = true

      // Audio reactivity
      if (analyserRef.current) {
        const { getAmplitude } = analyserRef.current
        const amp = getAmplitude()
        if (amp > 0.01) {
          ptMat.uniforms.uBright.value *= (1 + amp * 0.8)
        }
      }

      renderer.render(scene, camera)
    }

    animate()

    // ── Resize ────────────────────────────────────────────────────────────
    const onResize = () => {
      const w = mount.clientWidth || window.innerWidth
      const h = mount.clientHeight || window.innerHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      mount.removeChild(renderer.domElement)
    }
  }, [])  // mount once — state changes via refs

  return <div ref={mountRef} style={{ width: '100%', height: '100%' }} />
}
```

- [ ] **Step 2: Verificar que TypeScript compila sin errores**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ParticleNetwork.tsx
git commit -m "feat(visual): rewrite ParticleNetwork — 3-layer volumetric geometry, 3 connection types, preset system"
```

---

### Task 3.3: Agregar selector de presets en ControlView

**Files:**
- Modify: `frontend/src/views/ControlView.tsx`

- [ ] **Step 1: Agregar import y sección de presets al inicio del archivo**

En los imports de `ControlView.tsx`, agregar:
```typescript
import { PRESETS, VisualPresetId } from '../types/presets'
```

- [ ] **Step 2: Agregar el componente `PresetSelector` antes del `export function ControlView`**

```typescript
function PresetSelector() {
  const visualPreset  = useJARVISStore(s => s.visualPreset)
  const setVisualPreset = useJARVISStore(s => s.setVisualPreset)

  return (
    <div style={{ marginTop: 8 }}>
      <Label>VISUALIZACIÓN — PRESET</Label>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        gap: 6,
        marginTop: 6,
      }}>
        {(Object.values(PRESETS) as typeof PRESETS[VisualPresetId][]).map((p) => {
          const active = visualPreset === p.id
          const [r, g, b] = p.palette.node
          const hex = `rgb(${Math.round(r*255)},${Math.round(g*255)},${Math.round(b*255)})`
          return (
            <button
              key={p.id}
              onClick={() => setVisualPreset(p.id as VisualPresetId)}
              style={{
                background: active
                  ? `rgba(${Math.round(r*255)},${Math.round(g*255)},${Math.round(b*255)},0.18)`
                  : 'rgba(0,16,32,0.6)',
                border: `1px solid ${active ? hex : '#0a2030'}`,
                borderRadius: 6,
                padding: '8px 4px',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 4,
                transition: 'all 0.2s',
              }}
            >
              {/* Mini color preview */}
              <div style={{
                width: 28, height: 28,
                borderRadius: '50%',
                background: `radial-gradient(circle, ${hex} 0%, transparent 70%)`,
                boxShadow: active ? `0 0 10px ${hex}` : 'none',
              }} />
              <span style={{
                fontFamily: 'monospace',
                fontSize: 7,
                letterSpacing: '0.15em',
                color: active ? hex : '#1e3a4a',
                textTransform: 'uppercase',
              }}>
                {p.name}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Agregar `<PresetSelector />` dentro de la pestaña CONFIG de ControlView**

Buscar el JSX de la tab CONFIG (buscar `tab === 'CONFIG'` o similar) y agregar `<PresetSelector />` dentro de un `<Card>` al final de esa sección.

- [ ] **Step 4: Verificar en browser que los presets aparecen y cambian la red visual**

```bash
cd frontend && npm run dev
```
Abrir http://localhost:3007, ir a la vista de control, tab CONFIG, y hacer click en cada preset. La red neuronal debe transicionar suavemente entre paletas.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ControlView.tsx
git commit -m "feat(visual): add preset selector in ControlView with live preview circles"
```

---

## Verificación final

- [ ] **Launcher:** `python launch.py install-only` completa sin errores. `python launch.py` arranca todos los servicios y abre el browser.
- [ ] **Audio:** El backend arranca sin PyAudio, log muestra `noise floor = XX RMS`. El eco del mic está eliminado.
- [ ] **Visual:** La red neuronal muestra 400 nodos en 3 capas visibles. Los 5 presets cambian la paleta con transición suave. El estado `thinking` activa cascada desde el núcleo.

```bash
git log --oneline -10
```
