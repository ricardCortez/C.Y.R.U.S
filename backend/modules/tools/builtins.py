"""
JARVIS — Built-in tools.

All tools are registered at import time via @tool decorator.
Import this module once at engine startup to populate the registry.

Available tools:
  buscar_web      — DuckDuckGo search (no API key needed)
  clima           — Weather via wttr.in (no API key needed)
  hora_ciudad     — Current time in any city (worldtimeapi.org)
  calculadora     — Safe arithmetic evaluator
  listar_archivos — List files in a local directory
  abrir_archivo   — Read content of a text file
  traducir        — Translate text using LibreTranslate (local/public)
  sistema_info    — CPU, RAM, disk usage
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from backend.modules.tools.registry import tool
from backend.modules.tools.result import ToolResult
from backend.utils.logger import get_logger

logger = get_logger("jarvis.tools.builtins")

_HTTP_TIMEOUT = 8.0


# ── 1. Web search — DuckDuckGo (no API key) ───────────────────────────────

@tool(
    name="buscar_web",
    description="Busca información actual en internet usando DuckDuckGo",
    params={"query": "texto a buscar", "max_results": "número de resultados (por defecto 3)"},
)
async def web_search(query: str, max_results: str = "3") -> ToolResult:
    n = min(int(max_results), 5)
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1", "skip_disambig": "1"}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            data = r.json()

        results = []
        # AbstractText — direct answer
        if data.get("AbstractText"):
            results.append(data["AbstractText"][:400])

        # RelatedTopics
        for topic in data.get("RelatedTopics", [])[:n]:
            text = topic.get("Text", "")
            if text and text not in results:
                results.append(text[:200])
            if len(results) >= n:
                break

        if not results:
            return ToolResult.failure(f"Sin resultados para: {query}")

        output = f"Resultados para '{query}':\n" + "\n• ".join(results)
        return ToolResult.success(output, data=results)

    except Exception as exc:
        return ToolResult.failure(f"búsqueda fallida: {exc}")


# ── 2. Clima — wttr.in (no API key) ───────────────────────────────────────

@tool(
    name="clima",
    description="Obtiene el clima actual de cualquier ciudad",
    params={"ciudad": "nombre de la ciudad (ej: Lima, Madrid, Buenos Aires)"},
)
async def get_weather(ciudad: str) -> ToolResult:
    url = f"https://wttr.in/{httpx.URL(ciudad).path}?format=j1&lang=es"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
            r = await c.get(f"https://wttr.in/{ciudad}?format=j1")
            r.raise_for_status()
            data = r.json()

        current = data["current_condition"][0]
        temp_c  = current["temp_C"]
        feels   = current["FeelsLikeC"]
        desc    = current["lang_es"][0]["value"] if current.get("lang_es") else current["weatherDesc"][0]["value"]
        humidity = current["humidity"]
        wind_km  = current["windspeedKmph"]

        output = (
            f"Clima en {ciudad}: {desc}. "
            f"Temperatura {temp_c}°C (sensación {feels}°C). "
            f"Humedad {humidity}%, viento {wind_km} km/h."
        )
        return ToolResult.success(output, data=current)

    except Exception as exc:
        return ToolResult.failure(f"no pude obtener el clima de {ciudad}: {exc}")


# ── 3. Hora en cualquier ciudad ────────────────────────────────────────────

@tool(
    name="hora_ciudad",
    description="Obtiene la hora actual en cualquier ciudad o zona horaria",
    params={"ciudad": "nombre de la ciudad o zona horaria (ej: Tokyo, New_York, Europe/Madrid)"},
)
async def get_time_in_city(ciudad: str) -> ToolResult:
    # Map common city names to timezone strings
    CITY_MAP = {
        "nueva york": "America/New_York", "new york": "America/New_York",
        "londres": "Europe/London",        "london": "Europe/London",
        "madrid": "Europe/Madrid",         "españa": "Europe/Madrid",
        "tokio": "Asia/Tokyo",             "tokyo": "Asia/Tokyo",
        "lima": "America/Lima",            "peru": "America/Lima",
        "buenos aires": "America/Argentina/Buenos_Aires",
        "cdmx": "America/Mexico_City",     "mexico": "America/Mexico_City",
        "bogota": "America/Bogota",        "bogotá": "America/Bogota",
        "santiago": "America/Santiago",
    }
    tz = CITY_MAP.get(ciudad.lower(), ciudad.replace(" ", "_"))
    url = f"https://worldtimeapi.org/api/timezone/{tz}"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
            r = await c.get(url)
            r.raise_for_status()
            data = r.json()

        dt_str   = data["datetime"][:19]   # 2026-04-19T14:30:00
        dt       = datetime.fromisoformat(dt_str)
        readable = dt.strftime("%H:%M del %A %d de %B de %Y")

        output = f"En {ciudad} son las {readable}."
        return ToolResult.success(output, data=data)

    except Exception as exc:
        return ToolResult.failure(f"no pude obtener la hora en {ciudad}: {exc}")


# ── 4. Calculadora — safe eval ────────────────────────────────────────────

@tool(
    name="calculadora",
    description="Calcula expresiones matemáticas de forma segura",
    params={"expresion": "expresión matemática (ej: 15 * 8 + 200 / 4, sqrt(144), 2**10)"},
)
async def calculate(expresion: str) -> ToolResult:
    # Safe whitelist of allowed names
    safe = {
        "abs": abs, "round": round, "min": min, "max": max,
        "sqrt": math.sqrt, "pow": math.pow, "log": math.log,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "pi": math.pi, "e": math.e,
    }
    # Strip anything that's not math
    clean = re.sub(r"[^0-9+\-*/().,%\s\w]", "", expresion)
    try:
        result = eval(clean, {"__builtins__": {}}, safe)  # noqa: S307
        output = f"{expresion} = {result}"
        return ToolResult.success(output, data=result)
    except Exception as exc:
        return ToolResult.failure(f"no pude calcular '{expresion}': {exc}")


# ── 5. Listar archivos ────────────────────────────────────────────────────

@tool(
    name="listar_archivos",
    description="Lista los archivos en un directorio del sistema",
    params={"ruta": "ruta al directorio (ej: C:/Users/ricar/Desktop, ~/Documentos)"},
)
async def list_files(ruta: str) -> ToolResult:
    try:
        path = Path(os.path.expanduser(ruta))
        if not path.exists():
            return ToolResult.failure(f"La ruta '{ruta}' no existe.")
        if not path.is_dir():
            return ToolResult.failure(f"'{ruta}' no es un directorio.")

        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = []
        for e in entries[:20]:
            if e.is_dir():
                lines.append(f"[DIR] {e.name}/")
            else:
                size = e.stat().st_size
                sz   = f"{size/1024:.1f} KB" if size > 1024 else f"{size} B"
                lines.append(f"[FILE] {e.name} ({sz})")

        total = len(list(path.iterdir()))
        output = f"Directorio '{path.name}' ({total} elementos):\n" + "\n".join(lines)
        if total > 20:
            output += f"\n... y {total-20} más."
        return ToolResult.success(output)

    except PermissionError:
        return ToolResult.failure(f"Sin permisos para acceder a '{ruta}'.")
    except Exception as exc:
        return ToolResult.failure(str(exc))


# ── 6. Leer archivo de texto ──────────────────────────────────────────────

@tool(
    name="leer_archivo",
    description="Lee el contenido de un archivo de texto",
    params={"ruta": "ruta completa al archivo", "max_lineas": "máximo de líneas a leer (por defecto 50)"},
)
async def read_file(ruta: str, max_lineas: str = "50") -> ToolResult:
    try:
        n    = min(int(max_lineas), 200)
        path = Path(os.path.expanduser(ruta))
        if not path.exists():
            return ToolResult.failure(f"Archivo '{ruta}' no encontrado.")
        if not path.is_file():
            return ToolResult.failure(f"'{ruta}' no es un archivo.")

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        shown = lines[:n]
        output = f"Archivo '{path.name}' ({len(lines)} líneas):\n" + "\n".join(shown)
        if len(lines) > n:
            output += f"\n[...{len(lines)-n} líneas más...]"
        return ToolResult.success(output)

    except Exception as exc:
        return ToolResult.failure(str(exc))


# ── 7. Info del sistema ───────────────────────────────────────────────────

@tool(
    name="sistema_info",
    description="Obtiene información del sistema: CPU, RAM, disco y procesos",
    params={},
)
async def system_info() -> ToolResult:
    try:
        import psutil
        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        output = (
            f"CPU: {cpu:.0f}% de uso | "
            f"RAM: {ram.used/1e9:.1f}/{ram.total/1e9:.1f} GB ({ram.percent:.0f}%) | "
            f"Disco: {disk.used/1e9:.0f}/{disk.total/1e9:.0f} GB ({disk.percent:.0f}%) | "
            f"OS: {platform.system()} {platform.release()}"
        )
        return ToolResult.success(output, data={
            "cpu_pct": cpu, "ram_pct": ram.percent,
            "disk_pct": disk.percent,
        })
    except Exception as exc:
        return ToolResult.failure(str(exc))


# ── 8. Abrir aplicación (Windows) ─────────────────────────────────────────

@tool(
    name="abrir_app",
    description="Abre una aplicación o URL en el sistema Windows",
    params={"target": "nombre de app (notepad, chrome, calculadora) o URL completa"},
)
async def open_app(target: str) -> ToolResult:
    APP_MAP = {
        "notepad":      "notepad.exe",
        "bloc de notas": "notepad.exe",
        "calculadora":  "calc.exe",
        "explorador":   "explorer.exe",
        "paint":        "mspaint.exe",
        "cmd":          "cmd.exe",
        "terminal":     "wt.exe",
    }
    try:
        low = target.lower().strip()
        exe = APP_MAP.get(low, target)

        if exe.startswith("http://") or exe.startswith("https://"):
            import webbrowser
            webbrowser.open(exe)
            return ToolResult.success(f"Abrí '{target}' en el navegador.")

        subprocess.Popen(
            exe,
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0,
        )
        return ToolResult.success(f"Abrí '{target}'.")

    except Exception as exc:
        return ToolResult.failure(f"no pude abrir '{target}': {exc}")


# ── 9. Uso y costo ────────────────────────────────────────────────────────

@tool(
    name="uso_jarvis",
    description="Muestra el uso de tokens y costo estimado de esta sesión y del día",
    params={},
)
async def uso_jarvis() -> ToolResult:
    try:
        # Access tracker via engine singleton pattern — engine injects it at startup
        import sys
        tracker = None
        for mod in sys.modules.values():
            if hasattr(mod, '_JARVIS_USAGE_TRACKER'):
                tracker = mod._JARVIS_USAGE_TRACKER
                break
        if tracker is None:
            return ToolResult.success("Tracker no disponible en esta sesión.")

        session = tracker.session_summary()
        today   = tracker.today_summary()
        alltime = tracker.all_time_summary()
        output  = f"{session}\n{today}\n{alltime}"
        return ToolResult.success(output)
    except Exception as exc:
        return ToolResult.failure(f"No pude obtener estadísticas: {exc}")


# ── Import guard ──────────────────────────────────────────────────────────
import re  # used by calculadora — imported here to avoid circular issues
