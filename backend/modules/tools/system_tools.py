"""
JARVIS — System tools: pantalla, archivos, procesos, comandos, portapapeles.

Registra automáticamente al ser importado.  Todas son async y devuelven
ToolResult para que el executor ReAct pueda encadenarlas.

Herramientas expuestas:
  ver_pantalla        — screenshot + descripción Claude vision
  ventanas_abiertas   — lista de ventanas / apps activas en Windows
  ejecutar_comando    — ejecuta un comando de shell con timeout
  escribir_archivo    — crea o sobreescribe un archivo de texto
  buscar_archivos     — busca archivos por patrón de nombre
  abrir_programa      — abre una app o URL con mapeo de nombres en español
  procesos_activos    — lista procesos activos con CPU/RAM
  portapapeles_leer   — lee el contenido del portapapeles
  portapapeles_copiar — copia texto al portapapeles
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from backend.modules.tools.registry import tool
from backend.modules.tools.result import ToolResult
from backend.utils.logger import get_logger

logger = get_logger("jarvis.tools.system")

# ── Constantes ────────────────────────────────────────────────────────────────

_SCREENSHOT_W   = 1280   # resize before sending to Claude (saves tokens)
_CMD_TIMEOUT    = 30     # seconds for shell commands
_MAX_CMD_OUTPUT = 4_000  # chars of stdout/stderr to return
_MAX_FILE_SIZE  = 2 * 1024 * 1024   # 2 MB read limit
_SAFE_WRITE_DIRS = [   # restrict writes to safe locations
    Path.home(),
    Path("C:/Users"),
]

# ── Diccionario de nombres de aplicaciones en español ─────────────────────────

_APP_ALIASES: dict[str, str] = {
    # Utilidades Windows
    "bloc de notas": "notepad.exe",
    "notepad":       "notepad.exe",
    "calculadora":   "calc.exe",
    "explorador":    "explorer.exe",
    "paint":         "mspaint.exe",
    "terminal":      "wt.exe",
    "consola":       "wt.exe",
    "cmd":           "cmd.exe",
    "powershell":    "powershell.exe",
    "task manager":  "taskmgr.exe",
    "administrador de tareas": "taskmgr.exe",
    # Browsers
    "chrome":        "chrome",
    "firefox":       "firefox",
    "edge":          "msedge",
    "navegador":     "msedge",
    # Dev tools
    "vscode":        "code",
    "visual studio code": "code",
    "cursor":        "cursor",
    "git":           "git",
    # Productivity
    "word":          "winword.exe",
    "excel":         "excel.exe",
    "outlook":       "outlook.exe",
    "teams":         "teams.exe",
    # Media
    "spotify":       "spotify.exe",
    "vlc":           "vlc.exe",
    "reproductor":   "wmplayer.exe",
    # System
    "configuracion": "ms-settings:",
    "configuración": "ms-settings:",
    "panel de control": "control.exe",
}


# ── 1. Ver pantalla — screenshot + Claude vision ──────────────────────────────

@tool(
    name="ver_pantalla",
    description=(
        "Toma una captura de pantalla y describe qué hay en ella usando visión de IA. "
        "Útil para: ¿qué hay en mi pantalla?, ¿qué ventana tengo abierta?, ¿qué dice ahí?"
    ),
    params={"pregunta": "qué quieres saber de la pantalla (opcional, por defecto describe todo)"},
)
async def ver_pantalla(pregunta: str = "") -> ToolResult:
    # 1. Capture screen
    img_b64 = await asyncio.get_event_loop().run_in_executor(None, _take_screenshot)
    if not img_b64:
        return ToolResult.failure("No pude capturar la pantalla.")

    # 2. Describe via Claude vision
    description = await _describe_with_claude(img_b64, pregunta or "Describe qué hay en la pantalla.")
    if description:
        return ToolResult.success(description, data={"screenshot_b64": img_b64[:100] + "..."})

    # 3. Fallback: window list if Claude unavailable
    windows = _get_windows_powershell()
    if windows:
        return ToolResult.success(
            "No pude usar visión IA. Ventanas activas:\n" + windows
        )
    return ToolResult.failure("No pude describir la pantalla.")


def _take_screenshot() -> Optional[str]:
    """Capture primary screen and return base64 PNG. Uses mss (fast)."""
    try:
        import mss, mss.tools
        from PIL import Image

        with mss.mss() as sct:
            monitor = sct.monitors[1]   # primary monitor
            img = sct.grab(monitor)
            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

        # Resize to save tokens/bandwidth
        w, h = pil_img.size
        if w > _SCREENSHOT_W:
            ratio = _SCREENSHOT_W / w
            pil_img = pil_img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        pil_img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:
        logger.warning(f"[JARVIS] screenshot failed: {exc}")
        # Fallback: PIL.ImageGrab
        try:
            from PIL import ImageGrab, Image
            img = ImageGrab.grab()
            w, h = img.size
            if w > _SCREENSHOT_W:
                ratio = _SCREENSHOT_W / w
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as exc2:
            logger.warning(f"[JARVIS] screenshot fallback failed: {exc2}")
            return None


async def _describe_with_claude(img_b64: str, question: str) -> str:
    """Send screenshot to Claude vision API and return description."""
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        return ""
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"{question}\n\n"
                            "Responde en español, de forma concisa (máx 3 oraciones). "
                            "Menciona app en primer plano, contenido visible relevante."
                        ),
                    },
                ],
            }],
        )
        return response.content[0].text if response.content else ""
    except Exception as exc:
        logger.warning(f"[JARVIS] Claude vision failed: {exc}")
        return ""


# ── 2. Ventanas abiertas ──────────────────────────────────────────────────────

@tool(
    name="ventanas_abiertas",
    description="Lista las ventanas y aplicaciones que están abiertas en Windows ahora mismo",
    params={},
)
async def ventanas_abiertas() -> ToolResult:
    result = await asyncio.get_event_loop().run_in_executor(None, _get_windows_powershell)
    if result:
        return ToolResult.success("Ventanas abiertas:\n" + result)
    return ToolResult.failure("No pude obtener la lista de ventanas.")


def _get_windows_powershell() -> str:
    """Use PowerShell to list visible windows with titles."""
    try:
        cmd = (
            'Get-Process | Where-Object {$_.MainWindowTitle -ne ""} | '
            'Select-Object ProcessName, MainWindowTitle | '
            'Format-Table -AutoSize | Out-String -Width 120'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=8,
        )
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        return "\n".join(lines[:25]) if lines else ""
    except Exception as exc:
        logger.warning(f"[JARVIS] window list failed: {exc}")
        # Fallback: psutil
        try:
            import psutil
            wins = []
            for p in psutil.process_iter(["name", "status"]):
                if p.info["status"] == "running":
                    wins.append(p.info["name"])
            return "Procesos activos: " + ", ".join(sorted(set(wins))[:20])
        except Exception:
            return ""


# ── 3. Ejecutar comando ───────────────────────────────────────────────────────

@tool(
    name="ejecutar_comando",
    description=(
        "Ejecuta un comando de terminal o PowerShell y devuelve la salida. "
        "Ejemplos: git status, dir, python --version, ipconfig"
    ),
    params={
        "comando": "comando a ejecutar",
        "directorio": "directorio de trabajo (opcional, por defecto el proyecto JARVIS)",
    },
)
async def ejecutar_comando(comando: str, directorio: str = "") -> ToolResult:
    work_dir = Path(os.path.expanduser(directorio)) if directorio else Path.cwd()

    logger.info(f"[JARVIS] ejecutar_comando: {comando!r} en {work_dir}")

    try:
        proc = await asyncio.create_subprocess_shell(
            comando,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CMD_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult.failure(f"Comando tardó más de {_CMD_TIMEOUT}s — cancelado.")

        out = stdout.decode("utf-8", errors="replace")[:_MAX_CMD_OUTPUT]
        err = stderr.decode("utf-8", errors="replace")[:500]
        rc  = proc.returncode

        if rc == 0:
            return ToolResult.success(out or "(sin salida)", data={"returncode": rc})
        else:
            msg = out or err or f"Código de salida {rc}"
            return ToolResult.failure(f"Error (código {rc}): {msg}")

    except Exception as exc:
        return ToolResult.failure(f"No pude ejecutar el comando: {exc}")


# ── 4. Escribir archivo ───────────────────────────────────────────────────────

@tool(
    name="escribir_archivo",
    description="Crea o sobreescribe un archivo de texto con el contenido especificado",
    params={
        "ruta":      "ruta completa del archivo a crear (ej: ~/Desktop/notas.txt)",
        "contenido": "texto a escribir en el archivo",
        "modo":      "write (sobreescribir) o append (añadir al final) — por defecto write",
    },
)
async def escribir_archivo(ruta: str, contenido: str, modo: str = "write") -> ToolResult:
    try:
        path = Path(os.path.expanduser(ruta))

        # Security: only write within home directory
        try:
            path.resolve().relative_to(Path.home().resolve())
        except ValueError:
            return ToolResult.failure(
                f"Solo puedo escribir dentro de tu carpeta de usuario ({Path.home()})."
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        write_mode = "a" if modo == "append" else "w"
        path.write_text(contenido, encoding="utf-8") if write_mode == "w" else \
            path.open("a", encoding="utf-8").write(contenido)

        size = path.stat().st_size
        action = "añadí a" if modo == "append" else "escribí"
        return ToolResult.success(
            f"{action.capitalize()} '{path.name}' ({size} bytes).",
            data={"path": str(path)},
        )
    except Exception as exc:
        return ToolResult.failure(f"No pude escribir el archivo: {exc}")


# ── 5. Buscar archivos ────────────────────────────────────────────────────────

@tool(
    name="buscar_archivos",
    description="Busca archivos por nombre o patrón en un directorio",
    params={
        "patron":    "nombre o patrón a buscar (ej: *.py, reporte*.xlsx, config.yaml)",
        "directorio": "directorio donde buscar (por defecto el directorio de proyectos)",
    },
)
async def buscar_archivos(patron: str, directorio: str = "~") -> ToolResult:
    try:
        base = Path(os.path.expanduser(directorio))
        if not base.exists():
            return ToolResult.failure(f"Directorio '{directorio}' no encontrado.")

        loop = asyncio.get_event_loop()
        matches = await loop.run_in_executor(
            None,
            lambda: list(base.rglob(patron))[:30],
        )

        if not matches:
            return ToolResult.failure(f"No encontré archivos con patrón '{patron}' en {base}.")

        lines = []
        for p in matches:
            try:
                sz = p.stat().st_size
                size_str = f"{sz/1024:.1f} KB" if sz > 1024 else f"{sz} B"
                lines.append(f"{p}  ({size_str})")
            except Exception:
                lines.append(str(p))

        output = f"Archivos '{patron}' en {base} ({len(matches)} resultados):\n" + "\n".join(lines)
        return ToolResult.success(output, data={"paths": [str(p) for p in matches]})

    except Exception as exc:
        return ToolResult.failure(f"Error buscando archivos: {exc}")


# ── 6. Abrir programa (versión extendida) ─────────────────────────────────────

@tool(
    name="abrir_programa",
    description=(
        "Abre una aplicación, programa o URL. "
        "Ejemplos: chrome, spotify, vscode, https://google.com, calculadora"
    ),
    params={"programa": "nombre del programa o URL a abrir"},
)
async def abrir_programa(programa: str) -> ToolResult:
    low = programa.strip().lower()

    # URL → webbrowser
    if re.match(r"https?://", low):
        try:
            import webbrowser
            webbrowser.open(programa)
            return ToolResult.success(f"Abrí '{programa}' en el navegador.")
        except Exception as exc:
            return ToolResult.failure(f"No pude abrir la URL: {exc}")

    # Alias lookup
    exe = _APP_ALIASES.get(low, programa)

    try:
        # ms-settings: and similar URI schemes
        if ":" in exe and not exe.endswith(".exe"):
            subprocess.Popen(["start", exe], shell=True)
            return ToolResult.success(f"Abrí configuración '{programa}'.")

        subprocess.Popen(
            exe, shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE
            if os.name == "nt" else 0,
        )
        return ToolResult.success(f"Abrí '{programa}'.")
    except Exception as exc:
        return ToolResult.failure(f"No pude abrir '{programa}': {exc}")


# ── 7. Procesos activos ───────────────────────────────────────────────────────

@tool(
    name="procesos_activos",
    description="Lista los procesos activos en el sistema con uso de CPU y memoria",
    params={"filtro": "texto para filtrar por nombre de proceso (opcional)"},
)
async def procesos_activos(filtro: str = "") -> ToolResult:
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["name", "pid", "cpu_percent", "memory_info", "status"]):
            try:
                name = p.info["name"] or ""
                if filtro and filtro.lower() not in name.lower():
                    continue
                mem_mb = (p.info["memory_info"].rss / 1024 / 1024) if p.info["memory_info"] else 0
                procs.append((name, p.info["pid"], mem_mb))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        procs.sort(key=lambda x: x[2], reverse=True)   # sort by RAM
        lines = [f"{name:28s} PID={pid:6d}  RAM={mem:.0f} MB"
                 for name, pid, mem in procs[:20]]
        output = f"Procesos activos{f' (filtro: {filtro})' if filtro else ''} — top 20 por RAM:\n" + "\n".join(lines)
        return ToolResult.success(output)

    except Exception as exc:
        return ToolResult.failure(f"No pude listar procesos: {exc}")


# ── 8. Portapapeles — leer ────────────────────────────────────────────────────

@tool(
    name="portapapeles_leer",
    description="Lee el contenido actual del portapapeles (clipboard)",
    params={},
)
async def portapapeles_leer() -> ToolResult:
    try:
        import pyperclip
        content = pyperclip.paste()
        if not content:
            return ToolResult.success("El portapapeles está vacío.")
        preview = content[:500]
        output = f"Portapapeles ({len(content)} chars):\n{preview}"
        if len(content) > 500:
            output += f"\n[...{len(content)-500} chars más...]"
        return ToolResult.success(output, data={"content": content})
    except Exception as exc:
        return ToolResult.failure(f"No pude leer el portapapeles: {exc}")


# ── 9. Portapapeles — copiar ──────────────────────────────────────────────────

@tool(
    name="portapapeles_copiar",
    description="Copia texto al portapapeles del sistema",
    params={"texto": "texto a copiar al portapapeles"},
)
async def portapapeles_copiar(texto: str) -> ToolResult:
    try:
        import pyperclip
        pyperclip.copy(texto)
        preview = texto[:80] + ("..." if len(texto) > 80 else "")
        return ToolResult.success(f"Copiado al portapapeles: \"{preview}\"")
    except Exception as exc:
        return ToolResult.failure(f"No pude copiar al portapapeles: {exc}")


# ── 10. Reconocimiento — quién habla / quién está en cámara ──────────────────

# Engine injects these at startup:
_JARVIS_SPEAKER_INTEL = None   # SpeakerIntelligence instance
_JARVIS_VISION        = None   # VisionManager instance


@tool(
    name="quien_habla",
    description="Identifica quién está hablando basándose en el reconocimiento de voz",
    params={},
)
async def quien_habla() -> ToolResult:
    si = _JARVIS_SPEAKER_INTEL
    if si is None:
        return ToolResult.failure("Reconocimiento de voz no disponible.")
    profiles = si.list_speakers()
    if not profiles:
        return ToolResult.success(
            "No hay voces enroladas. Di 'registra mi voz' para que pueda reconocerte."
        )
    enrolled = ", ".join(f"{p['id']} ({p['role']})" for p in profiles)
    return ToolResult.success(f"Voces enroladas: {enrolled}.")


@tool(
    name="quien_esta_en_camara",
    description="Usa la cámara para ver quién está frente al sistema ahora mismo",
    params={},
)
async def quien_esta_en_camara() -> ToolResult:
    vm = _JARVIS_VISION
    if vm is None:
        return ToolResult.failure("Cámara no disponible o no activada.")
    try:
        ctx = vm.get_context()
        if not ctx.faces:
            return ToolResult.success("No detecto ninguna cara en la cámara ahora mismo.")
        lines = []
        for f in ctx.faces:
            name = f.identity if f.identity and f.identity != "unknown" else "persona desconocida"
            conf = f" (confianza {f.confidence:.0%})" if f.confidence > 0 else ""
            emotion = f", emoción: {f.emotion}" if f.emotion else ""
            lines.append(f"{name}{conf}{emotion}")
        return ToolResult.success("Veo: " + "; ".join(lines))
    except Exception as exc:
        return ToolResult.failure(f"Error de cámara: {exc}")


@tool(
    name="personas_conocidas",
    description="Lista todas las personas que JARVIS conoce por voz y cara",
    params={},
)
async def personas_conocidas() -> ToolResult:
    from pathlib import Path

    lines = ["Personas conocidas por JARVIS:"]

    # Voice profiles
    si = _JARVIS_SPEAKER_INTEL
    if si:
        voice_profiles = si.list_speakers()
        if voice_profiles:
            lines.append("Por voz:")
            for p in voice_profiles:
                lines.append(f"  - {p['id']} ({p['role']})")
        else:
            lines.append("Por voz: ninguna (di 'registra mi voz' para enrolar)")

    # Face profiles
    face_db = Path("data/faces")
    if face_db.exists():
        persons = [d.name for d in face_db.iterdir() if d.is_dir()]
        if persons:
            lines.append("Por cara:")
            for p in persons:
                n_photos = len(list((face_db / p).glob("*.*")))
                lines.append(f"  - {p} ({n_photos} fotos)")
        else:
            lines.append("Por cara: ninguna (di 'registra mi cara' para enrolar)")
    else:
        lines.append("Por cara: ninguna")

    return ToolResult.success("\n".join(lines))
