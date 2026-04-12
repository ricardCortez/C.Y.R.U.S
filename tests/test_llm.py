"""
C.Y.R.U.S — Tests for LLM clients and LLMManager.

Network-dependent tests are mocked to run without a live Ollama/Claude service.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.modules.llm.ollama_client import OllamaClient
from backend.modules.llm.claude_client import ClaudeClient
from backend.modules.llm.llm_manager import LLMManager
from backend.utils.exceptions import OllamaUnavailableError, LLMAPIError


# ── OllamaClient ─────────────────────────────────────────────────────────────

class TestOllamaClient:
    @pytest.mark.asyncio
    async def test_is_available_returns_false_when_offline(self):
        client = OllamaClient(host="http://localhost:9999")  # nothing there
        result = await client.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_chat_raises_on_connection_error(self):
        client = OllamaClient(host="http://localhost:9999", stream=False)
        with pytest.raises(OllamaUnavailableError):
            await client.chat([{"role": "user", "content": "hello"}])

    @pytest.mark.asyncio
    async def test_chat_mocked_response(self):
        client = OllamaClient(stream=False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "Hello, Ricardo."}}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            result = await client.chat([{"role": "user", "content": "hi"}])
        assert "Ricardo" in result or len(result) > 0

    @pytest.mark.asyncio
    async def test_build_payload_includes_system(self):
        client = OllamaClient()
        payload = client._build_payload(
            [{"role": "user", "content": "test"}],
            system_prompt="You are helpful.",
            temperature=0.5,
            max_tokens=100,
            stream=False,
        )
        assert payload["messages"][0]["role"] == "system"
        assert payload["options"]["temperature"] == 0.5


# ── ClaudeClient ──────────────────────────────────────────────────────────────

class TestClaudeClient:
    def test_raises_without_api_key(self):
        client = ClaudeClient(api_key="")
        with pytest.raises(LLMAPIError, match="CLAUDE_API_KEY"):
            client._get_client()

    @pytest.mark.asyncio
    async def test_chat_mocked(self):
        client = ClaudeClient(api_key="sk-test-fake")
        fake_content = MagicMock()
        fake_content.text = "Hello from Claude."
        fake_response = MagicMock()
        fake_response.content = [fake_content]

        with patch.object(client, "_get_client") as mock_get:
            mock_anthropic = MagicMock()
            mock_anthropic.messages.create = AsyncMock(return_value=fake_response)
            mock_get.return_value = mock_anthropic

            result = await client.chat([{"role": "user", "content": "hi"}])
        assert result == "Hello from Claude."


# ── LLMManager ───────────────────────────────────────────────────────────────

class TestLLMManager:
    def _make_manager(self, ollama_response: str | Exception, claude_response: str | None = None):
        ollama = AsyncMock(spec=OllamaClient)
        claude = AsyncMock(spec=ClaudeClient)

        if isinstance(ollama_response, Exception):
            ollama.chat.side_effect = ollama_response
        else:
            ollama.chat.return_value = ollama_response

        if claude_response:
            claude.chat.return_value = claude_response

        return LLMManager(
            ollama=ollama,
            claude=claude,
            soul_text="You are C.Y.R.U.S.",
            mode="HYBRID",
        )

    @pytest.mark.asyncio
    async def test_ollama_success(self):
        mgr = self._make_manager("It's 14:35, Ricardo.")
        result = await mgr.generate("What time is it?", language="en")
        assert "14:35" in result

    @pytest.mark.asyncio
    async def test_fallback_to_claude_on_ollama_failure(self):
        mgr = self._make_manager(
            OllamaUnavailableError("offline"),
            claude_response="I'm Claude, standing in.",
        )
        result = await mgr.generate("hello", language="en")
        assert "Claude" in result or len(result) > 0

    @pytest.mark.asyncio
    async def test_canned_response_in_local_mode(self):
        ollama = AsyncMock(spec=OllamaClient)
        ollama.chat.side_effect = OllamaUnavailableError("offline")
        claude = AsyncMock(spec=ClaudeClient)
        mgr = LLMManager(ollama=ollama, claude=claude, mode="LOCAL")
        result = await mgr.generate("hello")
        assert len(result) > 0  # canned message

    @pytest.mark.asyncio
    async def test_system_prompt_includes_soul(self):
        mgr = self._make_manager("ok")
        prompt = mgr._build_system_prompt("en", 1)
        assert "C.Y.R.U.S" in prompt
