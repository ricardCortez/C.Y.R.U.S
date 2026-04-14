"""C.Y.R.U.S — Memory orchestrator: store turns, search relevant context."""
from __future__ import annotations
import uuid
from typing import List, Optional
from backend.modules.memory.embedder import Embedder
from backend.modules.memory.qdrant_store import QdrantStore
from backend.modules.memory.conversation_db import ConversationDB
from backend.utils.logger import get_logger

logger = get_logger("cyrus.memory")


class MemoryManager:
    def __init__(
        self,
        embedder: Embedder,
        qdrant: QdrantStore,
        db: ConversationDB,
        session_id: Optional[str] = None,
        top_k: int = 5,
    ) -> None:
        self._embedder = embedder
        self._qdrant = qdrant
        self._db = db
        self._session_id = session_id or str(uuid.uuid4())
        self._top_k = top_k

    async def store_turn(self, role: str, content: str, language: str = "en") -> None:
        """Save a conversation turn to SQLite + Qdrant vector store."""
        turn_id = self._db.save_turn(self._session_id, role, content, language)
        if self._embedder.is_loaded:
            vector = self._embedder.embed(f"{role}: {content}")
            self._qdrant.upsert(
                point_id=turn_id,
                vector=vector,
                payload={
                    "role": role,
                    "content": content,
                    "language": language,
                    "session": self._session_id,
                },
            )

    async def retrieve_context(self, query: str, top_k: Optional[int] = None) -> str:
        """Return relevant past turns as a formatted string for LLM injection."""
        if not self._embedder.is_loaded or not self._qdrant.is_connected:
            return ""
        k = top_k or self._top_k
        vector = self._embedder.embed(query)
        results = self._qdrant.search(vector, top_k=k)
        if not results:
            return ""
        lines = ["[MEMORY — relevant past context:]"]
        for r in results:
            role = r.get("role", "?")
            content = r.get("content", "")
            lines.append(f"  {role}: {content}")
        return "\n".join(lines)

    @property
    def session_id(self) -> str:
        return self._session_id
