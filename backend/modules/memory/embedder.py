"""JARVIS — Sentence embedding for semantic memory search."""
from __future__ import annotations
from typing import List
from backend.utils.exceptions import JARVISError
from backend.utils.logger import get_logger

logger = get_logger("jarvis.memory.embedder")


class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None

    def load(self) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self._model_name)
        logger.info(f"[JARVIS] Embedder loaded: {self._model_name}")

    def embed(self, text: str) -> List[float]:
        if self._model is None:
            raise JARVISError("[JARVIS] Embedder not loaded — call load() first")
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
