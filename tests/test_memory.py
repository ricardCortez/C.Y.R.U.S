"""C.Y.R.U.S — Tests for the Memory pipeline (Phase 3).

All tests are infrastructure-free — Qdrant and sentence-transformers are mocked.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

import numpy as np
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 — Embedder
# ─────────────────────────────────────────────────────────────────────────────

def test_embedder_returns_vector():
    import sys
    mock_st = MagicMock()
    mock_st.SentenceTransformer.return_value.encode.return_value = np.array([0.1, 0.2, 0.3])
    sys.modules["sentence_transformers"] = mock_st

    from backend.modules.memory.embedder import Embedder
    emb = Embedder(model_name="all-MiniLM-L6-v2")
    emb.load()
    vec = emb.embed("hello world")
    assert isinstance(vec, list)
    assert len(vec) == 3

    sys.modules.pop("sentence_transformers", None)


def test_embedder_not_loaded_raises():
    from backend.modules.memory.embedder import Embedder
    from backend.utils.exceptions import CYRUSError
    emb = Embedder()
    with pytest.raises(CYRUSError):
        emb.embed("test")


def test_embedder_is_loaded_flag():
    import sys
    mock_st = MagicMock()
    mock_st.SentenceTransformer.return_value.encode.return_value = np.array([0.1])
    sys.modules["sentence_transformers"] = mock_st

    from backend.modules.memory.embedder import Embedder
    emb = Embedder()
    assert not emb.is_loaded
    emb.load()
    assert emb.is_loaded

    sys.modules.pop("sentence_transformers", None)


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 — QdrantStore
# ─────────────────────────────────────────────────────────────────────────────

def _mock_qdrant_modules():
    """Inject mock qdrant_client into sys.modules."""
    import sys
    mock_qc = MagicMock()
    mock_models = MagicMock()
    sys.modules["qdrant_client"] = mock_qc
    sys.modules["qdrant_client.models"] = mock_models
    return mock_qc, mock_models


def test_qdrant_store_connect_creates_collection():
    import sys
    mock_qc, mock_models = _mock_qdrant_modules()

    # Simulate empty collection list
    mock_client_instance = MagicMock()
    mock_client_instance.get_collections.return_value.collections = []
    mock_qc.QdrantClient.return_value = mock_client_instance

    from backend.modules.memory.qdrant_store import QdrantStore
    store = QdrantStore(collection="test_col")
    store.connect()

    mock_client_instance.create_collection.assert_called_once()
    assert store.is_connected

    sys.modules.pop("qdrant_client", None)
    sys.modules.pop("qdrant_client.models", None)


def test_qdrant_store_upsert_and_search():
    import sys
    mock_qc, mock_models = _mock_qdrant_modules()

    mock_client_instance = MagicMock()
    mock_client_instance.get_collections.return_value.collections = []
    mock_result = MagicMock()
    mock_result.score = 0.95
    mock_result.payload = {"text": "hello", "role": "user"}
    mock_client_instance.search.return_value = [mock_result]
    mock_qc.QdrantClient.return_value = mock_client_instance

    from backend.modules.memory.qdrant_store import QdrantStore
    store = QdrantStore(collection="test_col")
    store.connect()
    store.upsert("mem-1", [0.1, 0.2, 0.3], {"text": "hello", "role": "user"})
    results = store.search([0.1, 0.2, 0.3], top_k=3)

    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["role"] == "user"
    assert results[0]["score"] == pytest.approx(0.95)

    sys.modules.pop("qdrant_client", None)
    sys.modules.pop("qdrant_client.models", None)


def test_qdrant_store_search_returns_empty_when_not_connected():
    from backend.modules.memory.qdrant_store import QdrantStore
    store = QdrantStore()
    results = store.search([0.1, 0.2], top_k=5)
    assert results == []
    assert not store.is_connected


def test_qdrant_store_upsert_noop_when_not_connected():
    from backend.modules.memory.qdrant_store import QdrantStore
    store = QdrantStore()
    # Should not raise
    store.upsert("x", [0.1], {"text": "hi"})


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 — ConversationDB
# ─────────────────────────────────────────────────────────────────────────────

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
        assert turns[1]["role"] == "assistant"
        assert turns[0]["content"] == "Hola"
    finally:
        os.unlink(db_path)


def test_conversation_db_multiple_sessions():
    from backend.modules.memory.conversation_db import ConversationDB

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = ConversationDB(db_path=db_path)
        db.init()
        db.save_turn("sess-a", "user", "Hello", "en")
        db.save_turn("sess-b", "user", "Hola", "es")

        turns_a = db.get_session_turns("sess-a")
        turns_b = db.get_session_turns("sess-b")
        assert len(turns_a) == 1
        assert len(turns_b) == 1
        assert turns_a[0]["language"] == "en"
        assert turns_b[0]["language"] == "es"
    finally:
        os.unlink(db_path)


def test_conversation_db_empty_session():
    from backend.modules.memory.conversation_db import ConversationDB

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        db = ConversationDB(db_path=db_path)
        db.init()
        turns = db.get_session_turns("nonexistent")
        assert turns == []
    finally:
        os.unlink(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# Task 4 — MemoryManager
# ─────────────────────────────────────────────────────────────────────────────

def _make_memory_manager(db_path: str):
    """Build a MemoryManager with all dependencies mocked."""
    from backend.modules.memory.embedder import Embedder
    from backend.modules.memory.qdrant_store import QdrantStore
    from backend.modules.memory.conversation_db import ConversationDB
    from backend.modules.memory.memory_manager import MemoryManager

    mock_embedder = MagicMock(spec=Embedder)
    mock_embedder.is_loaded = True
    mock_embedder.embed.return_value = [0.1, 0.2, 0.3]

    mock_qdrant = MagicMock(spec=QdrantStore)
    mock_qdrant.is_connected = True
    mock_qdrant.search.return_value = [
        {"role": "user", "content": "Mi color favorito es azul", "score": 0.9}
    ]

    real_db = ConversationDB(db_path=db_path)
    real_db.init()

    mm = MemoryManager(
        embedder=mock_embedder,
        qdrant=mock_qdrant,
        db=real_db,
        session_id="test-session",
        top_k=3,
    )
    return mm, mock_embedder, mock_qdrant


@pytest.mark.asyncio
async def test_memory_manager_store_turn():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        mm, mock_emb, mock_qdrant = _make_memory_manager(db_path)
        await mm.store_turn("user", "Hola mundo", "es")

        mock_emb.embed.assert_called_once()
        mock_qdrant.upsert.assert_called_once()

        from backend.modules.memory.conversation_db import ConversationDB
        db = ConversationDB(db_path=db_path)
        turns = db.get_session_turns("test-session")
        assert len(turns) == 1
        assert turns[0]["content"] == "Hola mundo"
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_memory_manager_retrieve_context():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        mm, mock_emb, mock_qdrant = _make_memory_manager(db_path)
        ctx = await mm.retrieve_context("¿Cuál es mi color favorito?")

        assert "[MEMORY" in ctx
        assert "azul" in ctx
        mock_qdrant.search.assert_called_once()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_memory_manager_retrieve_empty_when_not_connected():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        from backend.modules.memory.embedder import Embedder
        from backend.modules.memory.qdrant_store import QdrantStore
        from backend.modules.memory.conversation_db import ConversationDB
        from backend.modules.memory.memory_manager import MemoryManager

        mock_embedder = MagicMock(spec=Embedder)
        mock_embedder.is_loaded = False  # not loaded

        mock_qdrant = MagicMock(spec=QdrantStore)
        mock_qdrant.is_connected = False

        real_db = ConversationDB(db_path=db_path)
        real_db.init()

        mm = MemoryManager(mock_embedder, mock_qdrant, real_db)
        ctx = await mm.retrieve_context("anything")
        assert ctx == ""
    finally:
        os.unlink(db_path)


def test_memory_manager_session_id_generated():
    from backend.modules.memory.embedder import Embedder
    from backend.modules.memory.qdrant_store import QdrantStore
    from backend.modules.memory.conversation_db import ConversationDB
    from backend.modules.memory.memory_manager import MemoryManager

    mm = MemoryManager(
        MagicMock(spec=Embedder),
        MagicMock(spec=QdrantStore),
        MagicMock(spec=ConversationDB),
    )
    assert mm.session_id  # non-empty
    assert len(mm.session_id) == 36  # UUID format
