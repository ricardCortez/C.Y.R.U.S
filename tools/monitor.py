#!/usr/bin/env python3
"""
C.Y.R.U.S — Console Monitor
Conecta al backend por WebSocket y muestra el flujo de conversación en tiempo real.

Uso:
    python tools/monitor.py
    python tools/monitor.py --url ws://localhost:8765
    python tools/monitor.py --no-debug      (oculta logs de debug)
    python tools/monitor.py --no-color      (sin colores ANSI)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime

# ── ANSI colors ───────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BLUE   = "\033[34m"
MAGENTA= "\033[35m"
WHITE  = "\033[97m"
GRAY   = "\033[90m"

# ── Event renderers ───────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")

def _line(color: str, tag: str, text: str, use_color: bool) -> str:
    ts = f"{GRAY}{_ts()}{RESET}" if use_color else _ts()
    if use_color:
        return f"{ts}  {color}{BOLD}{tag:<14}{RESET}  {color}{text}{RESET}"
    return f"{ts}  {tag:<14}  {text}"

def render(event: str, data: dict, use_color: bool, show_debug: bool) -> str | None:
    match event:

        case "transcript":
            text = data.get("text", "")
            lang = data.get("language", "")
            tag  = f"[ USUARIO ]"
            body = f"{text}  {GRAY}[{lang}]{RESET}" if use_color else f"{text}  [{lang}]"
            return _line(GREEN, tag, body, use_color)

        case "response":
            text = data.get("text", "")
            # Truncate for console display
            preview = text[:180] + ("…" if len(text) > 180 else "")
            return _line(CYAN, "[ C.Y.R.U.S ]", preview, use_color)

        case "status":
            state = data.get("state", "").upper()
            msg   = data.get("message", "")
            STATE_COLOR = {
                "LISTENING":    GREEN,
                "TRANSCRIBING": CYAN,
                "THINKING":     YELLOW,
                "SPEAKING":     BLUE,
                "IDLE":         GRAY,
                "OFFLINE":      RED,
                "ERROR":        RED,
            }
            col  = STATE_COLOR.get(state, WHITE) if use_color else ""
            body = f"{state}" + (f"  {GRAY}{msg}{RESET}" if msg and use_color else
                                  f"  {msg}"              if msg else "")
            return _line(col, "[ STATUS ]", body, use_color)

        case "debug":
            if not show_debug:
                return None
            text  = data.get("text", "")
            level = data.get("level", "info")
            LEVEL_COL = {"ok": GREEN, "warn": YELLOW, "error": RED, "info": GRAY}
            col = LEVEL_COL.get(level, GRAY) if use_color else ""
            # Skip very verbose lines unless they're ok/warn/error
            if level == "info" and len(text) > 120:
                return None
            return _line(col, "  debug", text, use_color)

        case "enrollment":
            step = data.get("step","")
            if step == "result":
                heard = data.get("heard","")
                n     = data.get("sample","?")
                total = data.get("total","?")
                return _line(MAGENTA, "[ ENROLL ]", f"Muestra {n}/{total}: \"{heard}\"", use_color)
            elif step == "done":
                added = data.get("added", [])
                return _line(GREEN, "[ ENROLL ]", f"Completado — {len(added)} wake words registradas", use_color)

        case "wake_words":
            words = data.get("words", [])
            return _line(GRAY, "  wake_words", ", ".join(f'"{w}"' for w in words), use_color)

        case "system_stats":
            cpu  = data.get("cpu", 0)
            ram  = data.get("ram", 0)
            vram = data.get("vram", 0)
            temp = data.get("gpu_temp", 0)
            tts  = data.get("tts_backend", "?")
            body = f"CPU {cpu:.0f}%  RAM {ram:.0f}%  VRAM {vram:.0f}%  GPU {temp}°C  TTS {tts.upper()}"
            return _line(GRAY, "  stats", body, use_color)

        case "error":
            return _line(RED, "[ ERROR ]", data.get("message",""), use_color)

    return None


# ── Header ────────────────────────────────────────────────────────────────────

HEADER = r"""
  ██████ ██    ██ ██████  ██    ██ ███████
 ██       ██  ██  ██   ██ ██    ██ ██
 ██        ████   ██████  ██    ██ ███████
 ██         ██    ██   ██ ██    ██      ██
  ██████    ██    ██   ██  ██████  ███████
"""

# ── Main loop ─────────────────────────────────────────────────────────────────

async def run(url: str, show_debug: bool, use_color: bool) -> None:
    import websockets  # type: ignore

    if use_color:
        print(f"{CYAN}{HEADER}{RESET}")
        print(f"{BOLD}  Console Monitor{RESET}  —  {GRAY}Ctrl+C para salir{RESET}")
        print(f"{GRAY}  Conectando a {url}…{RESET}\n")
    else:
        print("C.Y.R.U.S Console Monitor")
        print(f"Conectando a {url}…\n")

    sep = f"{GRAY}{'─' * 70}{RESET}" if use_color else "─" * 70

    while True:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                if use_color:
                    print(f"{GREEN}{BOLD}  CONECTADO{RESET}  {GRAY}{url}{RESET}")
                else:
                    print(f"  CONECTADO  {url}")
                print(sep)

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    evt  = msg.get("event", "")
                    data = msg.get("data", {})

                    line = render(evt, data, use_color, show_debug)
                    if line:
                        print(line)

        except (ConnectionRefusedError, OSError):
            if use_color:
                print(f"{YELLOW}  Backend no disponible — reintentando en 3s…{RESET}")
            else:
                print("  Backend no disponible — reintentando en 3s…")
            await asyncio.sleep(3)

        except KeyboardInterrupt:
            break

        except Exception as exc:
            if use_color:
                print(f"{RED}  Error: {exc}{RESET}")
            else:
                print(f"  Error: {exc}")
            await asyncio.sleep(3)

    print("\n  Monitor cerrado.")


def main() -> None:
    # Fix Windows console encoding for Unicode output
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="C.Y.R.U.S Console Monitor")
    parser.add_argument("--url",      default="ws://localhost:8765", help="WebSocket URL")
    parser.add_argument("--no-debug", action="store_true",           help="Ocultar mensajes debug")
    parser.add_argument("--no-color", action="store_true",           help="Sin colores ANSI")
    args = parser.parse_args()

    use_color = not args.no_color
    # Disable color on non-TTY or Windows legacy console
    if not sys.stdout.isatty():
        use_color = False

    try:
        asyncio.run(run(args.url, not args.no_debug, use_color))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
