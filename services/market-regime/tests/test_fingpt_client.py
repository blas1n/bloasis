"""
Unit tests for FinGPT client.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.clients.fingpt_client import FinGPTClient, MockFinGPTClient


class TestMockFinGPTClient:
    """Tests for MockFinGPTClient."""

    @pytest.fixture
    def client(self) -> MockFinGPTClient:
        """Create a mock client instance."""
        return MockFinGPTClient()

    @pytest.mark.asyncio
    async def test_connect_is_noop(self, client: MockFinGPTClient) -> None:
        """Test that connect is a no-op."""
        await client.connect()
        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_is_noop(self, client: MockFinGPTClient) -> None:
        """Test that close is a no-op."""
        await client.close()

    @pytest.mark.asyncio
    async def test_health_check_returns_true(self, client: MockFinGPTClient) -> None:
        """Test that health check always returns True."""
        result = await client.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_classify_crisis_high_vix(self, client: MockFinGPTClient) -> None:
        """Test crisis classification when VIX > 35."""
        market_data = {"vix": 40.0}
        macro_indicators = {}

        result = await client.classify_regime(market_data, macro_indicators)

        assert result["regime"] == "crisis"
        assert result["confidence"] == 0.90
        assert "vix" in result["indicators"]

    @pytest.mark.asyncio
    async def test_classify_bear_elevated_vix(self, client: MockFinGPTClient) -> None:
        """Test bear classification when VIX > 25."""
        market_data = {"vix": 28.0}
        macro_indicators = {}

        result = await client.classify_regime(market_data, macro_indicators)

        assert result["regime"] == "bear"
        assert result["confidence"] == 0.80

    @pytest.mark.asyncio
    async def test_classify_bear_inverted_yield(self, client: MockFinGPTClient) -> None:
        """Test bear classification when yield curve is inverted."""
        market_data = {"vix": 20.0}
        macro_indicators = {"yield_curve_10y_2y": -0.5}

        result = await client.classify_regime(market_data, macro_indicators)

        assert result["regime"] == "bear"
        assert result["confidence"] == 0.75
        assert "yield_curve" in result["indicators"]

    @pytest.mark.asyncio
    async def test_classify_bull_low_vix(self, client: MockFinGPTClient) -> None:
        """Test bull classification when VIX < 15."""
        market_data = {"vix": 12.0}
        macro_indicators = {}

        result = await client.classify_regime(market_data, macro_indicators)

        assert result["regime"] == "bull"
        assert result["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_classify_bull_positive_momentum(
        self, client: MockFinGPTClient
    ) -> None:
        """Test bull classification with positive S&P momentum."""
        market_data = {"vix": 18.0, "sp500_1m_change": 5.0}
        macro_indicators = {"yield_curve_10y_2y": 0.5}

        result = await client.classify_regime(market_data, macro_indicators)

        assert result["regime"] == "bull"
        assert "sp500" in result["indicators"] or "momentum" in result["indicators"]

    @pytest.mark.asyncio
    async def test_classify_bear_negative_momentum(
        self, client: MockFinGPTClient
    ) -> None:
        """Test bear classification with negative S&P momentum."""
        market_data = {"vix": 18.0, "sp500_1m_change": -5.0}
        macro_indicators = {"yield_curve_10y_2y": 0.5}

        result = await client.classify_regime(market_data, macro_indicators)

        assert result["regime"] == "bear"

    @pytest.mark.asyncio
    async def test_classify_sideways_mixed_signals(
        self, client: MockFinGPTClient
    ) -> None:
        """Test sideways classification with mixed signals."""
        market_data = {"vix": 18.0, "sp500_1m_change": 0.5}
        macro_indicators = {"yield_curve_10y_2y": 0.5}

        result = await client.classify_regime(market_data, macro_indicators)

        assert result["regime"] == "sideways"
        assert result["confidence"] == 0.65


class TestFinGPTClient:
    """Tests for real FinGPTClient (via Hugging Face)."""

    @pytest.fixture
    def client(self) -> FinGPTClient:
        """Create a client instance."""
        return FinGPTClient(
            api_key="test-api-key",
            model="FinGPT/fingpt-sentiment_llama2-13b_lora",
            timeout=30.0,
        )

    @pytest.mark.asyncio
    async def test_connect_creates_client(self, client: FinGPTClient) -> None:
        """Test that connect creates an HTTP client."""
        await client.connect()
        assert client._client is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_close_clears_client(self, client: FinGPTClient) -> None:
        """Test that close clears the HTTP client."""
        await client.connect()
        await client.close()
        assert client._client is None

    def test_build_classification_prompt(self) -> None:
        """Test prompt building from YAML."""
        from src.prompts import format_classification_prompt

        market_data = {"vix": 25.0, "sp500_1m_change": -2.5}
        macro_indicators = {"fed_funds_rate": 5.25, "yield_curve_10y_2y": 0.5}

        prompt = format_classification_prompt(market_data, macro_indicators)

        assert "VIX (Volatility Index): 25.0" in prompt
        assert "S&P 500 Change (1 Month): -2.5%" in prompt
        assert "Federal Funds Rate: 5.25%" in prompt
        assert "crisis" in prompt
        assert "JSON" in prompt

    def test_parse_regime_response_hf_list_format(self, client: FinGPTClient) -> None:
        """Test parsing Hugging Face list response format."""
        response = [
            {
                "generated_text": '{"regime": "bull", "confidence": 0.85, "reasoning": "Low VIX", "key_indicators": ["vix"]}'
            }
        ]

        result = client._parse_regime_response(response)

        assert result["regime"] == "bull"
        assert result["confidence"] == 0.85
        assert result["reasoning"] == "Low VIX"
        assert result["indicators"] == ["vix"]

    def test_parse_regime_response_dict_content(self, client: FinGPTClient) -> None:
        """Test parsing response with dict content."""
        response = {
            "generated_text": '{"regime": "bear", "confidence": 0.75, "reasoning": "Elevated VIX", "key_indicators": ["vix", "momentum"]}'
        }

        result = client._parse_regime_response(response)

        assert result["regime"] == "bear"
        assert result["confidence"] == 0.75

    def test_parse_regime_response_embedded_json(self, client: FinGPTClient) -> None:
        """Test parsing response with JSON embedded in text."""
        response = [
            {
                "generated_text": 'Based on the analysis: {"regime": "sideways", "confidence": 0.65, "reasoning": "Mixed", "key_indicators": []}'
            }
        ]

        result = client._parse_regime_response(response)

        assert result["regime"] == "sideways"
        assert result["confidence"] == 0.65

    def test_parse_regime_response_invalid(self, client: FinGPTClient) -> None:
        """Test parsing invalid response returns defaults."""
        response = [{"generated_text": "invalid json with no braces"}]

        result = client._parse_regime_response(response)

        assert result["regime"] == "sideways"
        assert result["confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self) -> None:
        """Test health check returns False with no API key."""
        client = FinGPTClient(api_key="")
        result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_classify_regime_calls_api(self, client: FinGPTClient) -> None:
        """Test that classify_regime calls the API."""
        market_data = {"vix": 20.0}
        macro_indicators = {"fed_funds_rate": 5.25}

        with patch.object(client, "_call_api", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = [
                {"generated_text": '{"regime": "sideways", "confidence": 0.65, "reasoning": "Mixed signals", "key_indicators": []}'}
            ]

            result = await client.classify_regime(market_data, macro_indicators)

            mock_call.assert_called_once()
            assert result["regime"] == "sideways"

    @pytest.mark.asyncio
    async def test_call_api_handles_http_error(self, client: FinGPTClient) -> None:
        """Test that API errors are handled properly."""
        import httpx

        await client.connect()

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(client._client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_response
            )

            with pytest.raises(RuntimeError, match="Hugging Face API error"):
                await client._call_api("test prompt")

        await client.close()
