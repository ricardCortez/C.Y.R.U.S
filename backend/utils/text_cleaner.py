"""
C.Y.R.U.S — Text preparation for TTS synthesis.

Two-stage pipeline:
  1. clean_for_tts()        — strips markdown and visual formatting
  2. normalize_for_speech() — converts technical text to natural spoken Spanish

Use prepare_speech() as the single entry-point for the full pipeline.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Stage 1 — Markdown stripper
# ---------------------------------------------------------------------------

def clean_for_tts(text: str) -> str:
    """Remove markdown and formatting symbols before TTS synthesis.

    Args:
        text: Raw LLM response, possibly containing markdown.

    Returns:
        Clean plain text suitable for speech.
    """
    # System name: C.Y.R.U.S → CYRUS (prevent letter-by-letter pronunciation)
    text = re.sub(r'\bC\.Y\.R\.U\.S\b', 'CYRUS', text, flags=re.IGNORECASE)

    # Bold / italic: **text** → text, *text* → text, __text__ → text
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_\n]+)_{1,3}', r'\1', text)

    # Headers: # Title → Title
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Inline code: `code` → code (keep content — normalize_for_speech handles it)
    text = re.sub(r'`([^`\n]+)`', r'\1', text)

    # Code blocks: ```...``` → omit entirely (not speakable)
    text = re.sub(r'```[\s\S]*?```', '', text)

    # Bullet/numbered lists: remove leading "- ", "* ", "1. "
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Blockquotes: > text → text
    text = re.sub(r'^\s*>\s+', '', text, flags=re.MULTILINE)

    # Links: [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Bare URLs
    text = re.sub(r'https?://\S+', '', text)

    # Reasoning model thinking blocks: <think>...</think> → remove entirely
    text = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)

    # HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)

    # Table rows (| cell | cell |)
    text = re.sub(r'^\s*\|.*\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-| :]+$', '', text, flags=re.MULTILINE)

    # Collapse multiple blank lines to one
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


# ---------------------------------------------------------------------------
# Stage 2 — Technical normalizer
# ---------------------------------------------------------------------------

# Each entry: (regex_pattern, replacement, re_flags)
# Applied in order — specific patterns before generic.
# PHILOSOPHY: normalize syntax/symbols, don't re-translate sentences.
# The LLM is expected to write clean prose in the VOZ: line; these
# patterns are a safety net for residual technical artifacts.
_NORMALIZATIONS: list[tuple[str, str]] = [
    # ── Command-name hyphens → spaces (readability) ─────────────────────
    (r'\bdocker-compose\b',              'docker compose'),
    (r'\bk8s\b',                         'kubernetes'),

    # ── sudo — strip the prefix (adds no spoken meaning) ────────────────
    (r'\bsudo\s+',                       ''),

    # ── Bare systemctl verb + service → natural phrase ──────────────────
    # Only matches when the verb is the first word (bare command context)
    (r'(?<!\w)systemctl restart (\S+)',  r'reinicia el servicio \1'),
    (r'(?<!\w)systemctl start (\S+)',    r'inicia el servicio \1'),
    (r'(?<!\w)systemctl stop (\S+)',     r'detiene el servicio \1'),
    (r'(?<!\w)systemctl enable (\S+)',   r'habilita el servicio \1'),
    (r'(?<!\w)systemctl status (\S+)',   r'estado del servicio \1'),

    # ── CLI flags that appear standalone after a command ─────────────────
    # Only normalize when flag appears after whitespace (not mid-word)
    (r'(?<=\s)--verbose\b',              'con salida detallada'),
    (r'(?<=\s)--help\b',                 'con ayuda'),
    (r'(?<=\s)-h\b',                     'con ayuda'),

    # ── Bare file paths (path-like patterns, not words in a sentence) ────
    (r'/var/log/([^\s,]+)',              r'el log de \1'),
    (r'/etc/([^\s,]+)',                  r'la configuración de \1'),
    (r'~?/home/\w+/([^\s,\.]+)',         r'la carpeta \1'),

    # ── Ports written as :NNNN (skip http: and https: and time HH:MM) ──────────────────
    (r'(?<!http)(?<!\d):(\d{4,5})\b',    r' puerto \1'),

    # ── Repeated "puerto" artifact clean-up ─────────────────────────────
    (r'\bpuerto\s+puerto\b',             'puerto'),

    # ── IP addresses ────────────────────────────────────────────────────
    (r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', r'la dirección \1'),

    # ── Technical abbreviations (only expand non-obvious ones) ──────────
    # RAM, CPU, GPU, SSH, API, URL — kept as-is (universally understood spoken)
    (r'\bVM\b',    'máquina virtual'),
    (r'\bNVR\b',   'grabador de video'),
    (r'\bOS\b',    'sistema operativo'),
    (r'\bLAN\b',   'red local'),
    (r'\bSSD\b',   'disco de estado sólido'),
    (r'\bHDD\b',   'disco duro'),
]


def normalize_for_speech(text: str) -> str:
    """Convert technical text to natural spoken Spanish.

    Applies ordered pattern substitutions so that CLI commands,
    file paths, flags, and technical abbreviations read naturally
    when synthesised by TTS.

    Args:
        text: Plain text (markdown already stripped).

    Returns:
        Text suitable for speech synthesis.
    """
    for pattern, replacement in _NORMALIZATIONS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Collapse multiple spaces left by removals
    text = re.sub(r'[ \t]{2,}', ' ', text)
    # Remove lone punctuation artifacts (e.g. "  ,  " after removals)
    text = re.sub(r'\s+([,;:.])', r'\1', text)

    return text.strip()


# ---------------------------------------------------------------------------
# Combined pipeline
# ---------------------------------------------------------------------------

def prepare_speech(text: str) -> str:
    """Full speech preparation pipeline.

    Runs ``clean_for_tts`` followed by ``normalize_for_speech``.
    Use this as the single entry-point for TTS text preparation.

    Args:
        text: Raw LLM output (may contain markdown and technical notation).

    Returns:
        Clean, natural text ready for TTS synthesis.
    """
    # As a final safety measure, strip any leading "VOZ:" markers that
    # could have slipped through the LLM output to avoid double-reading.
    cleaned = clean_for_tts(text)
    # Remove any standalone or inline "VOZ:" markers (case-insensitive)
    cleaned = re.sub(r'(?im)^\s*voz:\s*', '', cleaned)
    cleaned = re.sub(r'(?i)\bvoz:\s*', '', cleaned)
    return normalize_for_speech(cleaned)
