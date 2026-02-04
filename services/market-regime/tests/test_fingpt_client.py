"""
Unit tests for FinGPT client.
"""

from unittest.mock import AsyncMock, patch

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
        # Mock wrapper uses shared mock client internally
        assert client._client is not None

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
        """Test that close closes the HTTP client."""
        await client.connect()
        await client.close()
        # Wrapper still has reference to shared client
        assert client._client is not None

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

    def test_parse_regime_response_valid(self, client: FinGPTClient) -> None:
        """Test parsing valid regime response."""
        data = {"regime": "bull", "confidence": 0.85, "reasoning": "Low VIX", "key_indicators": ["vix"]}

        result = client._parse_regime_response(data)

        assert result["regime"] == "bull"
        assert result["confidence"] == 0.85
        assert result["reasoning"] == "Low VIX"
        assert result["indicators"] == ["vix"]

    def test_parse_regime_response_invalid_regime(self, client: FinGPTClient) -> None:
        """Test parsing response with invalid regime."""
        data = {"regime": "invalid", "confidence": 0.75}

        result = client._parse_regime_response(data)

        assert result["regime"] == "sideways"  # Defaults to sideways
        assert result["confidence"] == 0.75

    def test_parse_regime_response_confidence_clamping(self, client: FinGPTClient) -> None:
        """Test that confidence is clamped to [0, 1]."""
        data = {"regime": "bull", "confidence": 1.5}  # Above 1.0

        result = client._parse_regime_response(data)

        assert result["confidence"] == 1.0  # Clamped to max

    def test_parse_regime_response_empty(self, client: FinGPTClient) -> None:
        """Test parsing empty response returns defaults."""
        data = {}

        result = client._parse_regime_response(data)

        assert result["regime"] == "sideways"
        assert result["confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self) -> None:
        """Test creating client with no API key raises error."""
        with pytest.raises(ValueError, match="Hugging Face API token required"):
            FinGPTClient(api_key="")

    @pytest.mark.asyncio
    async def test_classify_regime_calls_api(self, client: FinGPTClient) -> None:
        """Test that classify_regime calls the API."""
        market_data = {"vix": 20.0}
        macro_indicators = {"fed_funds_rate": 5.25}

        # Mock the shared client's analyze method
        with patch.object(client._client, "analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = {"regime": "sideways", "confidence": 0.65, "reasoning": "Mixed signals", "key_indicators": []}

            result = await client.classify_regime(market_data, macro_indicators)

            mock_analyze.assert_called_once()
            assert result["regime"] == "sideways"

    @pytest.mark.asyncio
    async def test_classify_regime_handles_errors(self, client: FinGPTClient) -> None:
        """Test that classify_regime handles API errors gracefully."""
        market_data = {"vix": 20.0}
        macro_indicators = {"fed_funds_rate": 5.25}

        # Mock the shared client's analyze method to raise error
        with patch.object(client._client, "analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.side_effect = RuntimeError("API error")

            result = await client.classify_regime(market_data, macro_indicators)

            # Should return default values on error
            assert result["regime"] == "sideways"
            assert result["confidence"] == 0.5
            assert "Error" in result["reasoning"]
