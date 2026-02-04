"""Tests for AI clients (FinGPT and Claude)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from anthropic.types import TextBlock

from shared.ai_clients import ClaudeClient, FinGPTClient


def make_text_block(text: str) -> TextBlock:
    """Create a TextBlock for testing."""
    return TextBlock(type="text", text=text)


class TestFinGPTClient:
    """Tests for shared FinGPT client."""

    @pytest.fixture
    def fingpt_client(self):
        """Create FinGPT client with test API key."""
        return FinGPTClient(api_key="test_fingpt_key")

    @pytest.mark.asyncio
    async def test_analyze_success(self, fingpt_client):
        """Test successful FinGPT analysis."""
        # Mock the response to return JSON directly
        expected_result = {"risk_level": "medium", "confidence": 0.85}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: [{"generated_text": json.dumps(expected_result)}],
            )
            mock_post.return_value.raise_for_status = lambda: None

            result = await fingpt_client.analyze(
                prompt="Test prompt",
                schema=None,
                params=None,
            )

            assert result["risk_level"] == "medium"
            assert result["confidence"] == 0.85
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_no_api_key(self):
        """Test analysis without API key raises error."""
        with pytest.raises(ValueError, match="Hugging Face API token required"):
            FinGPTClient(api_key="")

    @pytest.mark.asyncio
    async def test_analyze_http_error(self, fingpt_client):
        """Test analysis with HTTP error."""
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "API error", request=MagicMock(), response=mock_response
            )
            mock_post.return_value = mock_response

            with pytest.raises(RuntimeError, match="Hugging Face API error"):
                await fingpt_client.analyze("test prompt")

    @pytest.mark.asyncio
    async def test_analyze_with_schema(self, fingpt_client):
        """Test analysis with structured output schema."""
        expected_result = {"regime": "bull", "confidence": 0.9}

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: [{"generated_text": json.dumps(expected_result)}],
            )
            mock_post.return_value.raise_for_status = lambda: None

            schema = {"type": "object", "properties": {"regime": {"type": "string"}}}
            result = await fingpt_client.analyze(
                prompt="Test prompt", schema=schema, params={"temperature": 0.1}
            )

            assert result["regime"] == "bull"
            assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_analyze_json_parsing(self, fingpt_client):
        """Test JSON parsing from generated text."""
        # Test with text containing JSON
        text_with_json = 'Here is the analysis: {"score": 85, "status": "good"} end'

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200,
                json=lambda: [{"generated_text": text_with_json}],
            )
            mock_post.return_value.raise_for_status = lambda: None

            result = await fingpt_client.analyze(prompt="Test")

            assert result["score"] == 85
            assert result["status"] == "good"


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
