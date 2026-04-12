"""
C.Y.R.U.S — Centralised logging configuration.

All log records carry the [C.Y.R.U.S] prefix so they are easy to grep.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Return a named logger that prefixes every message with [C.Y.R.U.S].

    Args:
        name: Dotted module name (e.g. ``"cyrus.audio.input"``).
        level: Optional override — ``"DEBUG"``, ``"INFO"``, etc.

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    logger = logging.getLogger(name)
    # Avoid adding duplicate handlers when the module is re-imported.
    if logger.handlers:
        return logger

    effective_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logger.setLevel(effective_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [C.Y.R.U.S] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (stdout so Docker/systemd capture it cleanly).
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


def configure_file_logging(log_dir: Path, level: str = "INFO") -> None:
    """Attach a rotating file handler to the root logger.

    Args:
        log_dir: Directory in which ``cyrus.log`` will be created.
        level: Logging level string.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "cyrus.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s [C.Y.R.U.S] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(getattr(logging, level.upper(), logging.INFO))
    fh.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(fh)
