"""
C.Y.R.U.S — Text cleaner for TTS.

Strips markdown and other visual formatting that sounds wrong when read aloud.
"""

from __future__ import annotations

import re


def clean_for_tts(text: str) -> str:
    """Remove markdown and formatting symbols before TTS synthesis.

    Args:
        text: Raw LLM response, possibly containing markdown.

    Returns:
        Clean plain text suitable for speech.
    """
    # Bold / italic: **text** → text, *text* → text, __text__ → text
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)

    # Headers: # Title → Title
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Inline code: `code` → code
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Code blocks: ```...``` → (omit entirely — not speakable)
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

    # HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)

    # Collapse multiple blank lines to one
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Trim
    return text.strip()
