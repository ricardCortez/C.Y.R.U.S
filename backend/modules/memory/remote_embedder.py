"""
JARVIS — Remote Embedder backend.

HTTP client for the JARVIS Embedder microservice (services/embedder_server).
Replaces the in-process sentence-transformers Embedder when
``services.embedder.enabled: true``.

Usage
-----
Configure in config.yaml:
    services:
      embedder:
        enabled: true
        host: http://localhost:8002
"""

from __future__ import annotations

from typing import List, Optional

from backend.utils.logger import get_logger

logger = get_logger("jarvis.memory.remote_embedder")

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


class RemoteEmbedder:
    """HTTP client for the JARVIS Embedder microservice.

    Provides the same interface as the in-process :class:`Embedder`:
    ``embed(text) -> List[float]``.

    Args:
        host:    Base URL (e.g. ``http://localhost:8002``).
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        host: str = "http://localhost:8002",
        timeout: float = 10.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._available: Optional[bool] = None
        self._dim: int = 0

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def check_health(self) -> bool:
        if not _HTTPX_OK:
            self._available = False
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._host}/health")
                self._available = r.status_code == 200
                if self._available:
                    data = r.json()
                    self._dim = data.get("dim", 0)
                    logger.info(
                        f"[JARVIS] RemoteEmbedder: server ready — "
                        f"model={data.get('model','?')}, dim={self._dim}"
                    )
                return self._available
        except Exception as exc:
            logger.warning(f"[JARVIS] RemoteEmbedder: server not reachable at {self._host} ({exc})")
            self._available = False
            return False

    @property
    def available(self) -> bool:
        return bool(self._available)

    @property
    def is_loaded(self) -> bool:
        """Embedder-compatible property."""
        return bool(self._available)

    # ------------------------------------------------------------------
    # Embedding — async
    # ------------------------------------------------------------------

    async def aembed(self, text: str) -> List[float]:
        """Async embedding.

        Args:
            text: Input text.

        Returns:
            Float vector (normalized).
        """
        if not _HTTPX_OK:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    f"{self._host}/embed",
                    json={"text": text},
                )
                if r.status_code != 200:
                    logger.warning(f"[JARVIS] RemoteEmbedder: server returned {r.status_code}")
                    return []
                self._available = True
                return r.json().get("vector", [])
        except Exception as exc:
            logger.warning(f"[JARVIS] RemoteEmbedder: embed failed ({exc})")
            self._available = False
            return []

    async def aembed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts in one request."""
        if not _HTTPX_OK or not texts:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    f"{self._host}/embed_batch",
                    json={"texts": texts},
                )
                if r.status_code != 200:
                    return []
                self._available = True
                return r.json().get("vectors", [])
        except Exception as exc:
            logger.warning(f"[JARVIS] RemoteEmbedder: batch embed failed ({exc})")
            return []

    def embed(self, text: str) -> List[float]:
        """Sync wrapper — compatible with in-process Embedder interface."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self.aembed(text))
                    return future.result(timeout=self._timeout + 2)
            return loop.run_until_complete(self.aembed(text))
        except Exception as exc:
            logger.warning(f"[JARVIS] RemoteEmbedder: sync embed failed ({exc})")
            return []

    # ------------------------------------------------------------------
    # Embedder-compatible stub
    # ------------------------------------------------------------------

    def load(self) -> None:
        """No-op — model lives in the remote server."""
        pass
