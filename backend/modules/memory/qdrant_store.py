"""JARVIS — Qdrant vector store for semantic memory."""
from __future__ import annotations
from typing import Any, Dict, List
from backend.utils.logger import get_logger

logger = get_logger("jarvis.memory.qdrant")

_VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension


class QdrantStore:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection: str = "jarvis_memory",
    ) -> None:
        self._host = host
        self._port = port
        self._collection = collection
        self._client = None

    def connect(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        self._client = QdrantClient(host=self._host, port=self._port)
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"[JARVIS] Qdrant collection '{self._collection}' created")
        else:
            logger.info(f"[JARVIS] Qdrant collection '{self._collection}' ready")

    def upsert(self, point_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        if not self._client:
            return
        from qdrant_client.models import PointStruct
        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )

    def search(self, vector: List[float], top_k: int = 5) -> List[Dict]:
        if not self._client:
            return []
        results = self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )
        return [{"score": r.score, **r.payload} for r in results]

    @property
    def is_connected(self) -> bool:
        return self._client is not None
