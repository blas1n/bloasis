"""Unit tests for FinGPT Client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.clients.fingpt_client import FinGPTClient


@pytest.fixture
def fingpt_client():
    """Create FinGPT client with test config."""
    return FinGPTClient(
        api_key="test-api-key",
        base_url="https://api.test.fingpt.ai",
    )


@pytest.mark.asyncio
async def test_connect(fingpt_client):
    """Test client connection initialization."""
    await fingpt_client.connect()

    assert fingpt_client._client is not None
    assert isinstance(fingpt_client._client, httpx.AsyncClient)

    await fingpt_client.close()


@pytest.mark.asyncio
async def test_close(fingpt_client):
    """Test client disconnection."""
    await fingpt_client.connect()
    assert fingpt_client._client is not None

    await fingpt_client.close()
    assert fingpt_client._client is None


@pytest.mark.asyncio
async def test_analyze_sentiment_success(fingpt_client):
    """Test successful sentiment analysis."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "sentiment": 0.75,
        "confidence": 0.9,
        "news_count": 15,
        "summary": "Positive news about AI investments",
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        await fingpt_client.connect()
        result = await fingpt_client.analyze_sentiment("AAPL")

        assert result["sentiment"] == 0.75
        assert result["confidence"] == 0.9
        assert result["news_count"] == 15
        assert result["summary"] == "Positive news about AI investments"

        mock_post.assert_called_once_with(
            "/v1/sentiment/analyze",
            json={"symbol": "AAPL"},
        )

        await fingpt_client.close()


@pytest.mark.asyncio
async def test_analyze_sentiment_auto_connect(fingpt_client):
    """Test that analyze_sentiment auto-connects if not connected."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "sentiment": 0.5,
        "confidence": 0.8,
        "news_count": 10,
        "summary": "Neutral sentiment",
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        # Don't call connect() - should auto-connect
        assert fingpt_client._client is None
        result = await fingpt_client.analyze_sentiment("MSFT")

        assert fingpt_client._client is not None
        assert result["sentiment"] == 0.5

        await fingpt_client.close()


@pytest.mark.asyncio
async def test_analyze_sentiment_http_error(fingpt_client):
    """Test fallback on HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    http_error = httpx.HTTPStatusError(
        message="Server error",
        request=MagicMock(),
        response=mock_response,
    )

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = http_error

        await fingpt_client.connect()
        result = await fingpt_client.analyze_sentiment("AAPL")

        # Should return default sentiment
        assert result["sentiment"] == 0.0
        assert result["confidence"] == 0.0
        assert result["news_count"] == 0
        assert result["summary"] == "No sentiment data available"

        await fingpt_client.close()


@pytest.mark.asyncio
async def test_analyze_sentiment_request_error(fingpt_client):
    """Test fallback on request error (network issues)."""
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.RequestError("Connection refused")

        await fingpt_client.connect()
        result = await fingpt_client.analyze_sentiment("AAPL")

        # Should return default sentiment
        assert result["sentiment"] == 0.0
        assert result["confidence"] == 0.0
        assert result["news_count"] == 0

        await fingpt_client.close()


@pytest.mark.asyncio
async def test_analyze_sentiment_unexpected_error(fingpt_client):
    """Test fallback on unexpected error."""
    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = RuntimeError("Unexpected error")

        await fingpt_client.connect()
        result = await fingpt_client.analyze_sentiment("AAPL")

        # Should return default sentiment
        assert result["sentiment"] == 0.0
        assert result["confidence"] == 0.0

        await fingpt_client.close()


@pytest.mark.asyncio
async def test_analyze_sentiment_bearish(fingpt_client):
    """Test bearish sentiment response."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "sentiment": -0.8,
        "confidence": 0.85,
        "news_count": 20,
        "summary": "Negative earnings outlook",
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        await fingpt_client.connect()
        result = await fingpt_client.analyze_sentiment("XYZ")

        assert result["sentiment"] == -0.8
        assert result["confidence"] == 0.85

        await fingpt_client.close()


def test_default_sentiment(fingpt_client):
    """Test default sentiment values."""
    default = fingpt_client._default_sentiment()

    assert default["sentiment"] == 0.0
    assert default["confidence"] == 0.0
    assert default["news_count"] == 0
    assert default["summary"] == "No sentiment data available"


@pytest.mark.asyncio
async def test_uses_config_defaults():
    """Test that client uses config defaults when no args provided."""
    with patch("src.clients.fingpt_client.config") as mock_config:
        mock_config.fingpt_api_key = "config-api-key"
        mock_config.fingpt_base_url = "https://config.fingpt.ai"

        client = FinGPTClient()

        assert client.api_key == "config-api-key"
        assert client.base_url == "https://config.fingpt.ai"
