"""
Unit tests for prompts module.
"""

import pytest

from src.prompts import (
    format_classification_prompt,
    get_classification_prompt,
    get_model_parameters,
    get_response_schema,
    load_prompt,
)


class TestLoadPrompt:
    """Tests for prompt loading."""

    def test_load_regime_classification(self) -> None:
        """Test loading regime classification prompt."""
        config = load_prompt("regime_classification")
        assert "system" in config
        assert "classification" in config
        assert "parameters" in config

    def test_load_nonexistent_raises(self) -> None:
        """Test loading nonexistent prompt raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt")

    def test_caching_returns_same_object(self) -> None:
        """Test that prompts are cached."""
        config1 = load_prompt("regime_classification")
        config2 = load_prompt("regime_classification")
        assert config1 is config2


class TestGetClassificationPrompt:
    """Tests for classification prompt retrieval."""

    def test_returns_dict(self) -> None:
        """Test returns dictionary."""
        config = get_classification_prompt()
        assert isinstance(config, dict)

    def test_has_template(self) -> None:
        """Test has classification template."""
        config = get_classification_prompt()
        assert "template" in config["classification"]

    def test_has_response_schema(self) -> None:
        """Test has response schema."""
        config = get_classification_prompt()
        assert "response_schema" in config["classification"]

    def test_has_defaults(self) -> None:
        """Test has default values."""
        config = get_classification_prompt()
        assert "defaults" in config["classification"]


class TestFormatClassificationPrompt:
    """Tests for prompt formatting."""

    def test_formats_market_data(self) -> None:
        """Test market data is formatted into prompt."""
        market_data = {"vix": 25.5, "sp500_1m_change": 3.2}
        macro_indicators = {}

        prompt = format_classification_prompt(market_data, macro_indicators)

        assert "25.5" in prompt
        assert "3.2" in prompt

    def test_formats_macro_indicators(self) -> None:
        """Test macro indicators are formatted into prompt."""
        market_data = {}
        macro_indicators = {"fed_funds_rate": 5.25, "unemployment_rate": 3.8}

        prompt = format_classification_prompt(market_data, macro_indicators)

        assert "5.25" in prompt
        assert "3.8" in prompt

    def test_uses_defaults_for_missing(self) -> None:
        """Test uses default values for missing data."""
        market_data = {}
        macro_indicators = {}

        prompt = format_classification_prompt(market_data, macro_indicators)

        assert "N/A" in prompt

    def test_includes_regime_options(self) -> None:
        """Test includes all regime classification options."""
        prompt = format_classification_prompt({}, {})

        assert "crisis" in prompt
        assert "bear" in prompt
        assert "bull" in prompt
        assert "sideways" in prompt
        assert "recovery" in prompt

    def test_mentions_json_format(self) -> None:
        """Test mentions JSON format requirement."""
        prompt = format_classification_prompt({}, {})
        assert "JSON" in prompt


class TestGetResponseSchema:
    """Tests for response schema."""

    def test_returns_dict(self) -> None:
        """Test returns dictionary."""
        schema = get_response_schema()
        assert isinstance(schema, dict)

    def test_has_type_object(self) -> None:
        """Test schema type is object."""
        schema = get_response_schema()
        assert schema["type"] == "object"

    def test_has_regime_property(self) -> None:
        """Test has regime property with enum."""
        schema = get_response_schema()
        assert "regime" in schema["properties"]
        assert "enum" in schema["properties"]["regime"]

    def test_regime_enum_values(self) -> None:
        """Test regime enum has correct values."""
        schema = get_response_schema()
        expected = ["crisis", "bear", "bull", "sideways", "recovery"]
        assert schema["properties"]["regime"]["enum"] == expected

    def test_has_confidence_property(self) -> None:
        """Test has confidence property with bounds."""
        schema = get_response_schema()
        confidence = schema["properties"]["confidence"]
        assert confidence["type"] == "number"
        assert confidence["minimum"] == 0.0
        assert confidence["maximum"] == 1.0

    def test_has_required_fields(self) -> None:
        """Test has required fields."""
        schema = get_response_schema()
        required = schema["required"]
        assert "regime" in required
        assert "confidence" in required
        assert "reasoning" in required
        assert "key_indicators" in required


class TestGetModelParameters:
    """Tests for model parameters."""

    def test_returns_dict(self) -> None:
        """Test returns dictionary."""
        params = get_model_parameters()
        assert isinstance(params, dict)

    def test_has_max_new_tokens(self) -> None:
        """Test has max_new_tokens parameter."""
        params = get_model_parameters()
        assert "max_new_tokens" in params
        assert isinstance(params["max_new_tokens"], int)

    def test_has_temperature(self) -> None:
        """Test has temperature parameter."""
        params = get_model_parameters()
        assert "temperature" in params
        assert 0.0 <= params["temperature"] <= 1.0
