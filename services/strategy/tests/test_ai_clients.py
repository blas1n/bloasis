"""Tests for AI clients (ClaudeClient backward compatibility via litellm)."""

from unittest.mock import AsyncMock, patch

import pytest

from shared.ai_clients import ClaudeClient


class TestClaudeClient:
    """Tests for Claude client (now litellm-based)."""

    @pytest.fixture
    def claude_client(self):
        """Create Claude client."""
        return ClaudeClient()

    @pytest.mark.asyncio
    async def test_analyze_json_success(self, claude_client):
        """Test successful Claude analysis with JSON response."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(
                message=AsyncMock(
                    content='{"symbol": "AAPL", "direction": "long", "strength": 0.8}'
                )
            )
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await claude_client.analyze(
                prompt="Analyze AAPL",
                response_format="json",
            )

            assert result["symbol"] == "AAPL"
            assert result["direction"] == "long"

    @pytest.mark.asyncio
    async def test_analyze_json_with_markdown(self, claude_client):
        """Test Claude analysis with JSON in markdown code block."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content='```json\n{"result": "success"}\n```'))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await claude_client.analyze(
                prompt="Test prompt",
                response_format="json",
            )

            assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_analyze_text_success(self, claude_client):
        """Test successful Claude analysis with text response."""
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content="This is a text response"))
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            result = await claude_client.analyze(
                prompt="Test prompt",
                response_format="text",
            )

            assert result == "This is a text response"

    @pytest.mark.asyncio
    async def test_analyze_no_text_block(self, claude_client):
        """Test error when response content is None."""
        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock(message=AsyncMock(content=None))]

        with patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            with pytest.raises(ValueError, match="No text content in response"):
                await claude_client.analyze("test prompt")

    @pytest.mark.asyncio
    async def test_analyze_error_handling(self, claude_client):
        """Test error handling in Claude client."""
        with patch("litellm.acompletion", side_effect=Exception("API error")):
            with pytest.raises(Exception, match="API error"):
                await claude_client.analyze("test prompt")
