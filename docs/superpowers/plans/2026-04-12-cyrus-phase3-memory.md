# C.Y.R.U.S Phase 3 — Memory & Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task.

**Goal:** Give C.Y.R.U.S persistent long-term memory using Qdrant vector search + SQLite conversation history, so it remembers past interactions across sessions.

**Architecture:** Each conversation turn is embedded with `sentence-transformers` and stored in Qdrant. SQLite holds full conversation logs. Before each LLM call, `MemoryManager` does a semantic search to retrieve relevant past context and injects it into the system prompt.

**Tech Stack:** qdrant-client, sentence-transformers, sqlite3 (stdlib), numpy.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/modules/memory/__init__.py` | Module init |
| Create | `backend/modules/memory/embedder.py` | Sentence-transformer embeddings |
| Create | `backend/modules/memory/qdrant_store.py` | Qdrant vector store wrapper |
| Create | `backend/modules/memory/conversation_db.py` | SQLite conversation log |
| Create | `backend/modules/memory/memory_manager.py` | Orchestrates search + storage |
| Modify | `backend/core/cyrus_engine.py` | Wire MemoryManager |
| Modify | `backend/modules/llm/llm_manager.py` | Inject memory context |
| Modify | `config/config.yaml` | Add `memory:` section |
| Create | `tests/test_memory.py` | Memory module tests |
| Modify | `requirements.txt` | Add qdrant-client, sentence-transformers |

---

## Task 1: Embedder

**Files:**
- Create: `backend/modules/memory/embedder.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_memory.py
from unittest.mock import patch, MagicMock
import numpy as np

def test_embedder_returns_vector():
    from backend.modules.memory.embedder import Embedder
    with patch("sentence_transformers.SentenceTransformer") as MockST:
        MockST.return_value.encode.return_value = np.array([0.1, 0.2, 0.3])
        emb = Embedder(model_name="all-MiniLM-L6-v2")
        emb.load()
        vec = emb.embed("hello world")
        assert isinstance(vec, list)
        assert len(vec) == 3

def test_embedder_not_loaded_raises():
    from backend.modules.memory.embedder import Embedder
    from backend.utils.exceptions import CYRUSError
    emb = Embedder()
    try:
        emb.embed("test")
        assert False
    except CYRUSError:
        pass
```

- [ ] **Step 2: Run — expect FAIL**
```bat
pytest tests/test_memory.py -v
```

- [ ] **Step 3: Implement `embedder.py`**

```python
"""C.Y.R.U.S — Sentence embedding for semantic memory search."""
from __future__ import annotations
from typing import List
from backend.utils.exceptions import CYRUSError
from backend.utils.logger import get_logger

logger = get_logger("cyrus.memory.embedder")


class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None

    def load(self) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self._model_name)
        logger.info(f"[C.Y.R.U.S] Embedder loaded: {self._model_name}")

    def embed(self, text: str) -> List[float]:
        if self._model is None:
            raise CYRUSError("[C.Y.R.U.S] Embedder not loaded — call load() first")
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
```

- [ ] **Step 4: Run — expect PASS**
```bat
pytest tests/test_memory.py -v -k "embedder"
```

- [ ] **Step 5: Commit**
```bat
git add backend/modules/memory/embedder.py tests/test_memory.py
git commit -m "feat(memory): add sentence-transformer Embedder"
```

---

## Task 2: Qdrant vector store

**Files:**
- Create: `backend/modules/memory/qdrant_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_memory.py
def test_qdrant_store_upsert_and_search():
    from backend.modules.memory.qdrant_store import QdrantStore
    store = QdrantStore(host="localhost", port=6333, collection="cyrus_test")
    # Mock the qdrant client
    with patch("qdrant_client.QdrantClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.search.return_value = []
        store.connect()
        store.upsert("mem-1", [0.1, 0.2, 0.3], {"text": "hello", "role": "user"})
        results = store.search([0.1, 0.2, 0.3], top_k=3)
        assert isinstance(results, list)
```

- [ ] **Step 2: Implement `qdrant_store.py`**

```python
"""C.Y.R.U.S — Qdrant vector store for semantic memory."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from backend.utils.logger import get_logger

logger = get_logger("cyrus.memory.qdrant")
_VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension


class QdrantStore:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection: str = "cyrus_memory",
    ) -> None:
        self._host = host
        self._port = port
        self._collection = collection
        self._client = None

    def connect(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        self._client = QdrantClient(host=self._host, port=self._port)
        # Create collection if missing
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"[C.Y.R.U.S] Qdrant collection '{self._collection}' created")
        else:
            logger.info(f"[C.Y.R.U.S] Qdrant collection '{self._collection}' ready")

    def upsert(self, point_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        from qdrant_client.models import PointStruct
        if not self._client:
            return
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
```

- [ ] **Step 3: Run tests**
```bat
pytest tests/test_memory.py -v -k "qdrant"
```

- [ ] **Step 4: Commit**
```bat
git add backend/modules/memory/qdrant_store.py tests/test_memory.py
git commit -m "feat(memory): add QdrantStore vector memory"
```

---

## Task 3: SQLite conversation log

**Files:**
- Create: `backend/modules/memory/conversation_db.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_memory.py
import tempfile, os

def test_conversation_db_save_and_retrieve():
    from backend.modules.memory.conversation_db import ConversationDB
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = ConversationDB(db_path=db_path)
        db.init()
        db.save_turn(session_id="s1", role="user", content="Hola", language="es")
        db.save_turn(session_id="s1", role="assistant", content="Hola Ricardo", language="es")
        turns = db.get_session_turns("s1")
        assert len(turns) == 2
        assert turns[0]["role"] == "user"
    finally:
        os.unlink(db_path)
```

- [ ] **Step 2: Implement `conversation_db.py`**

```python
"""C.Y.R.U.S — SQLite conversation history."""
from __future__ import annotations
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict
from backend.utils.logger import get_logger

logger = get_logger("cyrus.memory.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    language    TEXT DEFAULT 'en',
    timestamp   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session ON turns(session_id);
"""


class ConversationDB:
    def __init__(self, db_path: str = "data/conversations.db") -> None:
        self._path = db_path

    def init(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
        logger.info(f"[C.Y.R.U.S] ConversationDB initialised at {self._path}")

    def save_turn(self, session_id: str, role: str, content: str, language: str = "en") -> str:
        turn_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO turns(id,session_id,role,content,language,timestamp) VALUES(?,?,?,?,?,?)",
                (turn_id, session_id, role, content, language, ts),
            )
        return turn_id

    def get_session_turns(self, session_id: str, limit: int = 50) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, language, timestamp FROM turns "
                "WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [{"role": r[0], "content": r[1], "language": r[2], "timestamp": r[3]}
                for r in reversed(rows)]

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)
```

- [ ] **Step 3: Run tests — expect PASS**
```bat
pytest tests/test_memory.py::test_conversation_db_save_and_retrieve -v
```

- [ ] **Step 4: Commit**
```bat
git add backend/modules/memory/conversation_db.py tests/test_memory.py
git commit -m "feat(memory): add SQLite ConversationDB"
```

---

## Task 4: MemoryManager + LLM injection

**Files:**
- Create: `backend/modules/memory/memory_manager.py`
- Modify: `backend/modules/llm/llm_manager.py`
- Modify: `config/config.yaml`
- Modify: `backend/core/cyrus_engine.py`

- [ ] **Step 1: Implement `memory_manager.py`**

```python
"""C.Y.R.U.S — Memory orchestrator: store turns, search relevant context."""
from __future__ import annotations
import uuid
from typing import List, Dict, Optional
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
        """Save a turn to SQLite + Qdrant."""
        turn_id = self._db.save_turn(self._session_id, role, content, language)
        if self._embedder.is_loaded:
            vector = self._embedder.embed(f"{role}: {content}")
            self._qdrant.upsert(
                point_id=turn_id,
                vector=vector,
                payload={"role": role, "content": content,
                         "language": language, "session": self._session_id},
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
```

- [ ] **Step 2: Add `memory_context` param to `LLMManager.generate()`**

```python
async def generate(
    self,
    user_input: str,
    history=None,
    language: str = "es",
    turn_count: int = 0,
    vision_context=None,
    memory_context: str = "",    # NEW
) -> str:
    system = self._build_system_prompt(language, turn_count, vision_context, memory_context)
    ...
```

Update `_build_system_prompt`:
```python
def _build_system_prompt(self, language, turn_count, vision_context=None, memory_context="") -> str:
    parts = [self._soul_text]
    parts.append(self._prompts.get("context_template", "").format(...))
    if memory_context:
        parts.append(memory_context)     # NEW
    if vision_context:
        parts.append(vision_context.to_prompt_text())
    return "\n\n".join(p for p in parts if p.strip())
```

- [ ] **Step 3: Wire MemoryManager in `cyrus_engine.py`**

```python
# In _process_one_turn, before LLM call:
memory_ctx = ""
if self._memory:
    memory_ctx = await self._memory.retrieve_context(clean_input)

response = await self._llm.generate(
    clean_input,
    history=...,
    language=lang,
    turn_count=...,
    vision_context=vision_ctx,
    memory_context=memory_ctx,   # NEW
)

# After LLM response, store both turns:
if self._memory:
    await self._memory.store_turn("user", clean_input, lang)
    await self._memory.store_turn("assistant", response, lang)
```

- [ ] **Step 4: Add `memory:` config block**

```yaml
memory:
  enabled: false    # set true when Qdrant is running
  qdrant:
    host: "localhost"
    port: 6333
    collection: "cyrus_memory"
  embedder:
    model: "all-MiniLM-L6-v2"
  db_path: "data/conversations.db"
  top_k: 5
```

- [ ] **Step 5: Run full test suite**
```bat
pytest tests/ -v
```

- [ ] **Step 6: Commit**
```bat
git add backend/ config/config.yaml tests/
git commit -m "feat(memory): Phase 3 complete — persistent semantic memory"
```

---

## Success Criteria

- [ ] `pytest tests/ -v` — all tests pass
- [ ] `memory.enabled: true` + Qdrant running → turns saved to vector DB
- [ ] LLM responses reference past interactions
- [ ] SQLite `data/conversations.db` grows with each session
- [ ] Memory search latency < 200ms
