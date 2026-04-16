"""
C.Y.R.U.S — Embedder Microservice (port 8002).

Standalone FastAPI server that produces sentence embeddings via
sentence-transformers.  Used by the Memory module instead of loading the
model in-process.

Endpoints
---------
GET  /health          → {"status":"ok","model":"all-MiniLM-L6-v2","dim":384}
POST /embed           → {"vector":[...float...]}
POST /embed_batch     → {"vectors":[[...float...], ...]}

Start
-----
    python -m services.embedder_server.main
    # or:
    uvicorn services.embedder_server.main:app --host 0.0.0.0 --port 8002

Dependencies
------------
    pip install sentence-transformers   (already installed)

Environment variables
---------------------
    EMBEDDER_MODEL   sentence-transformers model name  (default: all-MiniLM-L6-v2)
    EMBEDDER_DEVICE  cuda | cpu                        (default: cpu)
    EMBEDDER_PORT    listen port                       (default: 8002)
"""

from __future__ import annotations

import os
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="C.Y.R.U.S Embedder Server", version="1.0.0")

_model = None
_model_name = os.environ.get("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
_dim = 384


def _load_model():
    global _model, _dim
    from sentence_transformers import SentenceTransformer
    device = os.environ.get("EMBEDDER_DEVICE", "cpu")
    print(f"[Embedder-Server] Loading {_model_name} on {device}…")
    _model = SentenceTransformer(_model_name, device=device)
    # Probe embedding dim
    test = _model.encode(["test"], convert_to_numpy=True)
    _dim = test.shape[1]
    print(f"[Embedder-Server] Ready — dim={_dim}")


@app.on_event("startup")
async def on_startup():
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, _load_model)


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------

class EmbedRequest(BaseModel):
    text: str


class EmbedBatchRequest(BaseModel):
    texts: List[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok" if _model else "loading",
        "model": _model_name,
        "dim":   _dim,
    }


@app.post("/embed")
async def embed(req: EmbedRequest):
    if _model is None:
        raise HTTPException(503, "Model not loaded yet")
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        vec = await loop.run_in_executor(
            None,
            lambda: _model.encode([req.text], convert_to_numpy=True, normalize_embeddings=True)[0].tolist(),
        )
        return {"vector": vec, "dim": len(vec)}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/embed_batch")
async def embed_batch(req: EmbedBatchRequest):
    if _model is None:
        raise HTTPException(503, "Model not loaded yet")
    if not req.texts:
        return {"vectors": []}
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        vecs = await loop.run_in_executor(
            None,
            lambda: _model.encode(req.texts, convert_to_numpy=True, normalize_embeddings=True).tolist(),
        )
        return {"vectors": vecs, "dim": len(vecs[0]) if vecs else 0}
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("EMBEDDER_PORT", "8002"))
    uvicorn.run("services.embedder_server.main:app", host="0.0.0.0", port=port, reload=False)
