"""Tests for AI clients (Claude)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import TextBlock

from shared.ai_clients import ClaudeClient


def make_text_block(text: str) -> TextBlock:
    """Create a TextBlock for testing."""
    return TextBlock(type="text", text=text)


class TestClaudeClient:
    """Tests for Claude client."""

    @pytest.fixture
    def claude_client(self):
        """Create Claude client with test API key."""
        return ClaudeClient(api_key="test_claude_key")

    @pytest.mark.asyncio
    async def test_analyze_json_success(self, claude_client):
        """Test successful Claude analysis with JSON response."""
        mock_response = AsyncMock()
        mock_response.content = [
            make_text_block('{"symbol": "AAPL", "direction": "long", "strength": 0.8}')
        ]

        with patch.object(
            claude_client.client.messages, "create", new=AsyncMock(return_value=mock_response)
        ):
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
        mock_response.content = [
            make_text_block('```json\n{"result": "success"}\n```')
        ]

        with patch.object(
            claude_client.client.messages,
            "create",
            new=AsyncMock(return_value=mock_response),
        ):
            result = await claude_client.analyze(
                prompt="Test prompt",
                response_format="json",
            )

            assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_analyze_text_success(self, claude_client):
        """Test successful Claude analysis with text response."""
        mock_response = AsyncMock()
        mock_response.content = [make_text_block("This is a text response")]

        with patch.object(
            claude_client.client.messages,
            "create",
            new=AsyncMock(return_value=mock_response),
        ):
            result = await claude_client.analyze(
                prompt="Test prompt",
                response_format="text",
            )

            assert result == "This is a text response"

    @pytest.mark.asyncio
    async def test_analyze_no_api_key(self):
        """Test analysis without API key raises error."""
        client = ClaudeClient(api_key="")

        with pytest.raises(ValueError, match="Claude API key not configured"):
            await client.analyze("test prompt")

    @pytest.mark.asyncio
    async def test_analyze_no_text_block(self, claude_client):
        """Test error when response contains no TextBlock."""
        mock_response = AsyncMock()
        # Simulate response with no TextBlock (e.g., only ThinkingBlock)
        mock_response.content = [MagicMock(type="thinking")]

        with patch.object(
            claude_client.client.messages,
            "create",
            new=AsyncMock(return_value=mock_response),
        ):
            with pytest.raises(ValueError, match="No text content in response"):
                await claude_client.analyze("test prompt")

    @pytest.mark.asyncio
    async def test_analyze_error_handling(self, claude_client):
        """Test error handling in Claude client."""
        with patch.object(
            claude_client.client.messages,
            "create",
            side_effect=Exception("API error"),
        ):
            with pytest.raises(Exception, match="API error"):
                await claude_client.analyze("test prompt")
