"""
C.Y.R.U.S — Configuration Manager.

Loads ``config/config.yaml``, merges with ``.env`` overrides, and exposes a
single :class:`CYRUSConfig` namespace accessible throughout the application.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv

from backend.utils.exceptions import ConfigError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.config")

# ---------------------------------------------------------------------------
# Nested dataclasses — mirrors config.yaml structure
# ---------------------------------------------------------------------------

@dataclass
class LLMLocalConfig:
    provider: str = "ollama"
    model: str = "mistral:latest"
    host: str = "http://localhost:11434"
    timeout: int = 30
    stream: bool = True


@dataclass
class TTSLocalConfig:
    provider: str = "kokoro"           # kokoro | piper
    voice: str = "ef_dora"            # Kokoro voice ID
    speed: float = 0.95               # speaking rate (0.5–2.0)
    sample_rate: int = 24000          # output sample rate (Hz)
    lang_code: str = "e"             # Kokoro language code
    # Piper-specific fields (only used when provider = "piper")
    piper_model: str = ""            # path to .onnx model file
    piper_speaker: Optional[int] = None  # speaker ID for multi-speaker models


@dataclass
class LocalConfig:
    llm: LLMLocalConfig = field(default_factory=LLMLocalConfig)
    tts: TTSLocalConfig = field(default_factory=TTSLocalConfig)


@dataclass
class LLMAPIConfig:
    provider: str = "anthropic"
    api_key: str = ""
    model: str = "claude-opus-4-1"
    max_tokens: int = 500
    timeout: int = 60


@dataclass
class TTSAPIConfig:
    provider: str = "edge-tts"
    voice: str = "en-GB-RyanNeural"
    rate: str = "+0%"
    volume: str = "+0%"


@dataclass
class APIConfig:
    enabled: bool = True
    fallback_mode: bool = True
    llm: LLMAPIConfig = field(default_factory=LLMAPIConfig)
    tts: TTSAPIConfig = field(default_factory=TTSAPIConfig)


@dataclass
class AudioInputConfig:
    device: str = "default"
    sample_rate: int = 16000
    chunk_size: int = 1024
    channels: int = 1
    format: str = "int16"
    silence_threshold: int = 500
    silence_duration: float = 1.5


@dataclass
class AudioOutputConfig:
    device: str = "default"
    volume: float = 0.85
    sample_rate: int = 24000


@dataclass
class AudioConfig:
    input: AudioInputConfig = field(default_factory=AudioInputConfig)
    output: AudioOutputConfig = field(default_factory=AudioOutputConfig)


@dataclass
class TriggerConfig:
    wake_words: List[str] = field(
        default_factory=lambda: ["hola cyrus", "oye cyrus", "hey cyrus", "cyrus"]
    )
    fuzzy_matching: bool = True
    threshold: int = 85


@dataclass
class ASRConfig:
    model: str = "tiny"
    device: str = "cuda"
    compute_type: str = "float16"
    language: Optional[str] = None
    beam_size: int = 5
    vad_filter: bool = True
    initial_prompt: Optional[str] = None


@dataclass
class ConversationConfig:
    max_history_turns: int = 10
    system_prompt_file: str = "config/soul.md"
    prompts_file: str = "config/prompts.yaml"


@dataclass
class WebSocketConfig:
    host: str = "localhost"
    port: int = 8765
    ping_interval: int = 20
    ping_timeout: int = 10


@dataclass
class LoggingConfig:
    level: str = "INFO"
    console: bool = True
    file: bool = True
    log_dir: str = "logs"
    max_bytes: int = 10_485_760
    backup_count: int = 5


@dataclass
class SystemConfig:
    name: str = "C.Y.R.U.S"
    version: str = "1.0.0"
    mode: str = "LOCAL"
    log_level: str = "INFO"


@dataclass
class CYRUSConfig:
    """Top-level config object — use this everywhere in the app."""

    system: SystemConfig = field(default_factory=SystemConfig)
    local: LocalConfig = field(default_factory=LocalConfig)
    api: APIConfig = field(default_factory=APIConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Resolved paths (set after load)
    project_root: Path = field(default_factory=Path.cwd)
    soul_text: str = ""
    prompts: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_CONFIG_INSTANCE: Optional[CYRUSConfig] = None


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (non-destructive copy)."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(raw: dict) -> dict:
    """Apply ``CYRUS_*`` environment variables onto *raw* dict (flat keys only)."""
    for env_key, env_val in os.environ.items():
        if not env_key.startswith("CYRUS_"):
            continue
        parts = env_key[6:].lower().split("_")
        node = raw
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = env_val
    return raw


def load_config(config_path: Optional[Path] = None) -> CYRUSConfig:
    """Load and return the global :class:`CYRUSConfig`.

    Subsequent calls return the cached instance unless *config_path* is supplied.

    Args:
        config_path: Explicit path to ``config.yaml``.  Defaults to
            ``<project_root>/config/config.yaml``.

    Returns:
        Populated :class:`CYRUSConfig` dataclass.

    Raises:
        ConfigError: If the config file is missing or malformed.
    """
    global _CONFIG_INSTANCE
    if _CONFIG_INSTANCE is not None and config_path is None:
        return _CONFIG_INSTANCE

    # Determine project root (two levels up from this file: backend/core/ → root)
    project_root = Path(__file__).resolve().parent.parent.parent

    # Load .env before anything else so ${VAR} references resolve
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        # Also try config/.env.example as last resort during development
        dotenv_candidate = project_root / "config" / ".env.example"
        if dotenv_candidate.exists():
            logger.debug("[C.Y.R.U.S] .env not found; loading .env.example for defaults")

    resolved_path = config_path or (project_root / "config" / "config.yaml")
    if not resolved_path.exists():
        raise ConfigError(f"[C.Y.R.U.S] config.yaml not found at {resolved_path}")

    try:
        raw_text = resolved_path.read_text(encoding="utf-8")
        # Expand ${VAR} references using os.environ
        for var, val in os.environ.items():
            raw_text = raw_text.replace(f"${{{var}}}", val)
        raw: dict = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"[C.Y.R.U.S] Malformed config.yaml: {exc}") from exc

    raw = _apply_env_overrides(raw)

    cfg = CYRUSConfig(project_root=project_root)

    # ── system ───────────────────────────────────────────────────────────────
    if s := raw.get("system"):
        cfg.system = SystemConfig(**{k: v for k, v in s.items() if hasattr(SystemConfig, k)})

    # ── local ────────────────────────────────────────────────────────────────
    if loc := raw.get("local"):
        llm_cfg = LLMLocalConfig(**{k: v for k, v in (loc.get("llm") or {}).items() if k in LLMLocalConfig.__dataclass_fields__})
        tts_raw = dict(loc.get("tts") or {})
        tts_cfg = TTSLocalConfig(**{k: v for k, v in tts_raw.items() if k in TTSLocalConfig.__dataclass_fields__})
        cfg.local = LocalConfig(llm=llm_cfg, tts=tts_cfg)

    # ── api ──────────────────────────────────────────────────────────────────
    if api := raw.get("api"):
        api_llm = LLMAPIConfig(**(api.get("llm") or {}))
        api_tts = TTSAPIConfig(**(api.get("tts") or {}))
        cfg.api = APIConfig(
            enabled=api.get("enabled", True),
            fallback_mode=api.get("fallback_mode", True),
            llm=api_llm,
            tts=api_tts,
        )

    # ── audio ────────────────────────────────────────────────────────────────
    if aud := raw.get("audio"):
        cfg.audio = AudioConfig(
            input=AudioInputConfig(**(aud.get("input") or {})),
            output=AudioOutputConfig(**(aud.get("output") or {})),
        )

    # ── trigger ───────────────────────────────────────────────────────────────
    if trig := raw.get("trigger"):
        cfg.trigger = TriggerConfig(**{k: v for k, v in trig.items() if hasattr(TriggerConfig, k)})

    # ── asr ───────────────────────────────────────────────────────────────────
    if asr := raw.get("asr"):
        cfg.asr = ASRConfig(**{k: v for k, v in asr.items() if hasattr(ASRConfig, k)})

    # ── conversation ──────────────────────────────────────────────────────────
    if conv := raw.get("conversation"):
        cfg.conversation = ConversationConfig(**{k: v for k, v in conv.items() if hasattr(ConversationConfig, k)})

    # ── websocket ────────────────────────────────────────────────────────────
    if ws := raw.get("websocket"):
        cfg.websocket = WebSocketConfig(**{k: v for k, v in ws.items() if hasattr(WebSocketConfig, k)})

    # ── logging ───────────────────────────────────────────────────────────────
    if log := raw.get("logging"):
        cfg.logging = LoggingConfig(**{k: v for k, v in log.items() if hasattr(LoggingConfig, k)})

    # ── Resolve soul.md ───────────────────────────────────────────────────────
    soul_path = project_root / cfg.conversation.system_prompt_file
    if soul_path.exists():
        cfg.soul_text = soul_path.read_text(encoding="utf-8")
    else:
        logger.warning(f"[C.Y.R.U.S] soul.md not found at {soul_path}; using empty personality")

    # ── Resolve prompts.yaml ──────────────────────────────────────────────────
    prompts_path = project_root / cfg.conversation.prompts_file
    if prompts_path.exists():
        cfg.prompts = yaml.safe_load(prompts_path.read_text(encoding="utf-8")) or {}

    _CONFIG_INSTANCE = cfg
    logger.info(f"[C.Y.R.U.S] Configuration loaded — mode={cfg.system.mode}")
    return cfg
