"""
JARVIS — Centralised logging configuration.

Provides:
  - Console handler (stdout) for all modules
  - Rotating file handler → logs/jarvis.log   (INFO+, 10 MB, 5 backups)
  - Rotating file handler → logs/errors.log   (WARNING+, 5 MB, 3 backups)
  - Per-process log       → logs/<process>.log when configure_process_logging() is called

Usage:
    from backend.utils.logger import get_logger, configure_file_logging
    logger = get_logger("jarvis.audio.input")
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

_LOG_DIR: Optional[Path] = None
_FILE_CONFIGURED = False


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Return a named logger that writes to console (and file if configured).

    Args:
        name: Dotted module name, e.g. ``"jarvis.audio.input"``.
        level: Optional override — ``"DEBUG"``, ``"INFO"``, etc.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    effective_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logger.setLevel(effective_level)

    fmt = logging.Formatter(
        fmt="%(asctime)s [JARVIS] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    # Windows cmd uses cp1252 — avoid crashing on Unicode symbols in log messages
    if hasattr(ch.stream, 'reconfigure'):
        try:
            ch.stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    logger.addHandler(ch)

    return logger


def configure_file_logging(log_dir: Path, level: str = "INFO", process_name: str = "backend") -> None:
    """Attach rotating file handlers to the root logger.

    Creates:
      - ``logs/jarvis.log``          — INFO+ from all processes
      - ``logs/errors.log``          — WARNING+ only (quick error triage)
      - ``logs/<process_name>.log``  — INFO+ for this specific process

    Args:
        log_dir:      Directory where log files are created.
        level:        Minimum log level (default INFO).
        process_name: Short label for the per-process log (e.g. "backend", "tts", "asr").
    """
    global _FILE_CONFIGURED, _LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    _LOG_DIR = log_dir

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s [JARVIS] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # let handlers filter

    # ── Main log: INFO+ from all processes ───────────────────────────────
    _add_rotating_handler(
        root, log_dir / "jarvis.log",
        level=numeric_level,
        formatter=fmt,
        max_bytes=10 * 1024 * 1024,  # 10 MB
        backup_count=5,
    )

    # ── Error log: WARNING+ only — quick triage ───────────────────────────
    _add_rotating_handler(
        root, log_dir / "errors.log",
        level=logging.WARNING,
        formatter=fmt,
        max_bytes=5 * 1024 * 1024,   # 5 MB
        backup_count=3,
    )

    # ── Per-process log (e.g. tts.log, asr.log, backend.log) ─────────────
    if process_name and process_name != "backend":
        _add_rotating_handler(
            root, log_dir / f"{process_name}.log",
            level=numeric_level,
            formatter=fmt,
            max_bytes=5 * 1024 * 1024,
            backup_count=3,
        )

    _FILE_CONFIGURED = True


def _add_rotating_handler(
    logger: logging.Logger,
    path: Path,
    level: int,
    formatter: logging.Formatter,
    max_bytes: int,
    backup_count: int,
) -> None:
    """Add a RotatingFileHandler to *logger* only if not already attached."""
    path_str = str(path)
    for h in logger.handlers:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            if h.baseFilename == path_str:
                return  # already attached

    fh = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
