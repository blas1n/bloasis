"""Tests for LLMClient (litellm-based) and ClaudeClient backward compat."""

from unittest.mock import AsyncMock, patch

import pytest

from shared.ai_clients import ClaudeClient, LLMClient


class TestLLMClient:
    """Tests for LLMClient."""

    @pytest.fixture
    def client(self):
        """Create LLMClient with default model."""
        return LLMClient(model="anthropic/claude-haiku-4-5-20251001")

    @pytest.fixture
    def ollama_client(self):
        """Create LLMClient for Ollama."""
        return LLMClient(
            model="ollama_chat/llama3.1:8b",
            api_base="http://localhost:11434",
        )

    @pytest.mark.asyncio
    async def test_analyze_json_success(self, client):
        """Test successful JSON analysis."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"regime": "bull", "confidence": 0.9}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await client.analyze(
                prompt="Analyze market",
                response_format="json",
            )

        assert result["regime"] == "bull"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_analyze_json_with_markdown(self, client):
        """Test JSON extraction from markdown code block."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='```json\n{"result": "ok"}\n```'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await client.analyze(prompt="Test", response_format="json")

        assert result["result"] == "ok"

    @pytest.mark.asyncio
    async def test_analyze_json_with_generic_code_block(self, client):
        """Test JSON extraction from generic code block."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='```\n{"key": "value"}\n```'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await client.analyze(prompt="Test", response_format="json")

        assert result["key"] == "value"

    @pytest.mark.asyncio
    async def test_analyze_text_success(self, client):
        """Test text response mode."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content="Market outlook is positive"))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await client.analyze(prompt="Outlook?", response_format="text")

        assert result == "Market outlook is positive"

    @pytest.mark.asyncio
    async def test_analyze_passes_model_override(self, client):
        """Test that model parameter overrides default."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"ok": true}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.analyze(
                prompt="Test",
                model="openai/gpt-4o-mini",
                response_format="json",
            )

            assert mock_call.call_args.kwargs["model"] == "openai/gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_analyze_passes_system_prompt(self, client):
        """Test that system prompt is forwarded."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"ok": true}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.analyze(
                prompt="Test",
                system_prompt="You are a risk analyst.",
                response_format="json",
            )

            messages = mock_call.call_args.kwargs["messages"]
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "You are a risk analyst."

    @pytest.mark.asyncio
    async def test_analyze_default_system_prompt(self, client):
        """Test default system prompt when none provided."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"ok": true}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.analyze(prompt="Test", response_format="json")

            messages = mock_call.call_args.kwargs["messages"]
            assert "financial analysis expert" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_analyze_ollama_passes_api_base(self, ollama_client):
        """Test that Ollama client passes api_base."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"result": "local"}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await ollama_client.analyze(prompt="Test", response_format="json")

            assert mock_call.call_args.kwargs["api_base"] == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_analyze_passes_api_key(self):
        """Test that api_key is forwarded to litellm."""
        client = LLMClient(model="openai/gpt-4o-mini", api_key="sk-test-123")
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"ok": true}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.analyze(prompt="Test", response_format="json")

            assert mock_call.call_args.kwargs["api_key"] == "sk-test-123"

    @pytest.mark.asyncio
    async def test_analyze_no_api_key_when_none(self, client):
        """Test that api_key is not passed when None."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"ok": true}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.analyze(prompt="Test", response_format="json")

            assert "api_key" not in mock_call.call_args.kwargs

    @pytest.mark.asyncio
    async def test_analyze_no_api_base_when_none(self, client):
        """Test that api_base is not passed when None."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"ok": true}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.analyze(prompt="Test", response_format="json")

            assert "api_base" not in mock_call.call_args.kwargs

    @pytest.mark.asyncio
    async def test_analyze_error_propagation(self, client):
        """Test that LLM errors are re-raised."""
        with patch("litellm.acompletion", side_effect=Exception("Connection refused")):
            with pytest.raises(Exception, match="Connection refused"):
                await client.analyze(prompt="Test")

    @pytest.mark.asyncio
    async def test_analyze_null_content_raises(self, client):
        """Test error when response content is None."""
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock(message=AsyncMock(content=None))]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            with pytest.raises(ValueError, match="No text content"):
                await client.analyze(prompt="Test")

    def test_parse_json_plain(self):
        """Test parsing plain JSON."""
        result = LLMClient._parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_markdown_block(self):
        """Test parsing JSON from markdown block."""
        result = LLMClient._parse_json('```json\n{"a": 1}\n```')
        assert result == {"a": 1}

    def test_parse_json_generic_block(self):
        """Test parsing JSON from generic code block."""
        result = LLMClient._parse_json('```\n{"b": 2}\n```')
        assert result == {"b": 2}

    def test_parse_json_invalid_raises(self):
        """Test that invalid JSON raises."""
        with pytest.raises(Exception):
            LLMClient._parse_json("not json at all")


class TestClaudeClientBackwardCompat:
    """Tests for ClaudeClient backward compatibility."""

    def test_claude_client_is_llm_client(self):
        """ClaudeClient should be a subclass of LLMClient."""
        assert issubclass(ClaudeClient, LLMClient)

    def test_default_model_is_anthropic(self):
        """Default model should use anthropic/ prefix."""
        client = ClaudeClient()
        assert client.default_model.startswith("anthropic/")

    def test_init_accepts_and_stores_api_key(self):
        """api_key param should be forwarded to LLMClient."""
        client = ClaudeClient(api_key="sk-test-key")
        assert isinstance(client, LLMClient)
        assert client.api_key == "sk-test-key"

    @pytest.mark.asyncio
    async def test_auto_prefix_bare_model(self):
        """Bare model names should get anthropic/ prefix."""
        client = ClaudeClient()

        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"ok": true}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.analyze(
                prompt="Test",
                model="claude-haiku-4-5-20251001",
                response_format="json",
            )

            assert mock_call.call_args.kwargs["model"] == "anthropic/claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_prefixed_model_unchanged(self):
        """Already-prefixed model names should pass through."""
        client = ClaudeClient()

        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"ok": true}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.analyze(
                prompt="Test",
                model="anthropic/claude-haiku-4-5-20251001",
                response_format="json",
            )

            assert mock_call.call_args.kwargs["model"] == "anthropic/claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_none_model_uses_default(self):
        """None model should use ClaudeClient default."""
        client = ClaudeClient()

        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='{"ok": true}'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)) as mock_call:
            await client.analyze(prompt="Test", response_format="json")

            assert mock_call.call_args.kwargs["model"].startswith("anthropic/")
