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
    while time.monotonic() - start < timeout:
        if http_ok(url):
            elapsed = int(time.monotonic() - start)
            print(f" {OK}OK{RESET} ({elapsed}s)")
            return True
        print(".", end="", flush=True)
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

# ── CLI flags ─────────────────────────────────────────────────────────────────
def parse_flags(argv: list[str]) -> dict:
    flags = {
        "tts": True, "asr": False, "vision": False,
        "embedder": False, "frontend": True, "install_only": False,
        "force_install": False,
    }
    if not argv:
        return flags
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
