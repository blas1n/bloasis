"""
Unit tests for prompts module.
"""

import pytest

from src.prompts import (
    format_sector_prompt,
    format_theme_prompt,
    get_sector_model_parameters,
    get_sector_response_schema,
    get_theme_model_parameters,
    get_theme_response_schema,
    load_prompt,
)


class TestLoadPrompt:
    """Tests for prompt loading."""

    def test_load_sector_analysis(self) -> None:
        """Test loading sector analysis prompt."""
        config = load_prompt("sector_analysis")
        assert "system_prompt" in config
        assert "user_prompt_template" in config
        assert "response_schema" in config
        assert "model_parameters" in config

    def test_load_theme_analysis(self) -> None:
        """Test loading theme analysis prompt."""
        config = load_prompt("theme_analysis")
        assert "system_prompt" in config
        assert "user_prompt_template" in config
        assert "response_schema" in config
        assert "model_parameters" in config

    def test_load_nonexistent_raises(self) -> None:
        """Test loading nonexistent prompt raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt")

    def test_caching_returns_same_object(self) -> None:
        """Test that prompts are cached."""
        config1 = load_prompt("sector_analysis")
        config2 = load_prompt("sector_analysis")
        assert config1 is config2


class TestFormatSectorPrompt:
    """Tests for sector prompt formatting."""

    def test_formats_with_regime(self) -> None:
        """Test sector prompt formatting with regime."""
        prompt = format_sector_prompt(regime="bull")
        assert "bull" in prompt
        assert "sector" in prompt.lower()
        assert "score" in prompt.lower()

    def test_formats_with_different_regimes(self) -> None:
        """Test formatting with different regime values."""
        regimes = ["crisis", "bear", "bull", "sideways", "recovery"]
        for regime in regimes:
            prompt = format_sector_prompt(regime=regime)
            assert regime in prompt

    def test_uses_default_for_missing_regime(self) -> None:
        """Test uses default value when regime not provided."""
        prompt = format_sector_prompt()
        assert "unknown" in prompt

    def test_includes_system_prompt(self) -> None:
        """Test includes system prompt in output."""
        prompt = format_sector_prompt(regime="bull")
        assert "financial analyst" in prompt.lower()

    def test_includes_all_gics_sectors(self) -> None:
        """Test prompt mentions all 11 GICS sectors."""
        prompt = format_sector_prompt(regime="bull")
        sectors = [
            "Technology",
            "Healthcare",
            "Financials",
            "Consumer Discretionary",
            "Industrials",
            "Communication Services",
            "Consumer Staples",
            "Energy",
            "Utilities",
            "Real Estate",
            "Materials",
        ]
        for sector in sectors:
            assert sector in prompt

    def test_mentions_json_format(self) -> None:
        """Test mentions JSON format requirement."""
        prompt = format_sector_prompt(regime="bull")
        assert "JSON" in prompt


class TestFormatThemePrompt:
    """Tests for theme prompt formatting."""

    def test_formats_with_sectors_and_regime(self) -> None:
        """Test theme prompt formatting with sectors and regime."""
        sectors = ["Technology", "Healthcare"]
        prompt = format_theme_prompt(sectors=sectors, regime="bull")
        assert "Technology" in prompt
        assert "Healthcare" in prompt
        assert "bull" in prompt

    def test_formats_with_empty_sectors(self) -> None:
        """Test formatting with empty sectors list."""
        prompt = format_theme_prompt(sectors=[], regime="bull")
        assert "No sectors selected" in prompt or "bull" in prompt

    def test_formats_multiple_sectors(self) -> None:
        """Test formatting with multiple sectors."""
        sectors = ["Technology", "Healthcare", "Financials"]
        prompt = format_theme_prompt(sectors=sectors, regime="recovery")
        for sector in sectors:
            assert sector in prompt

    def test_uses_defaults_for_missing_values(self) -> None:
        """Test uses default values when not provided."""
        prompt = format_theme_prompt(sectors=[], regime="")
        # Should not crash and should use defaults
        assert len(prompt) > 0

    def test_includes_system_prompt(self) -> None:
        """Test includes system prompt in output."""
        prompt = format_theme_prompt(sectors=["Technology"], regime="bull")
        assert "investment theme" in prompt.lower()

    def test_mentions_representative_symbols(self) -> None:
        """Test mentions representative symbols requirement."""
        prompt = format_theme_prompt(sectors=["Technology"], regime="bull")
        assert "representative" in prompt.lower() or "symbols" in prompt.lower()


class TestGetSectorResponseSchema:
    """Tests for sector response schema."""

    def test_returns_dict(self) -> None:
        """Test returns dictionary."""
        schema = get_sector_response_schema()
        assert isinstance(schema, dict)

    def test_has_type_object(self) -> None:
        """Test schema type is object."""
        schema = get_sector_response_schema()
        assert schema["type"] == "object"

    def test_has_sectors_property(self) -> None:
        """Test has sectors property with array type."""
        schema = get_sector_response_schema()
        assert "sectors" in schema["properties"]
        assert schema["properties"]["sectors"]["type"] == "array"

    def test_sectors_items_have_required_fields(self) -> None:
        """Test sector items have required fields."""
        schema = get_sector_response_schema()
        items_schema = schema["properties"]["sectors"]["items"]
        properties = items_schema["properties"]

        assert "sector" in properties
        assert "score" in properties
        assert "rationale" in properties
        assert "selected" in properties

    def test_score_has_bounds(self) -> None:
        """Test score property has min/max bounds."""
        schema = get_sector_response_schema()
        score_schema = schema["properties"]["sectors"]["items"]["properties"]["score"]
        assert score_schema["type"] == "number"
        assert score_schema["minimum"] == 0
        assert score_schema["maximum"] == 100

    def test_has_required_fields(self) -> None:
        """Test has required fields."""
        schema = get_sector_response_schema()
        required = schema["required"]
        assert "sectors" in required


class TestGetThemeResponseSchema:
    """Tests for theme response schema."""

    def test_returns_dict(self) -> None:
        """Test returns dictionary."""
        schema = get_theme_response_schema()
        assert isinstance(schema, dict)

    def test_has_type_object(self) -> None:
        """Test schema type is object."""
        schema = get_theme_response_schema()
        assert schema["type"] == "object"

    def test_has_themes_property(self) -> None:
        """Test has themes property with array type."""
        schema = get_theme_response_schema()
        assert "themes" in schema["properties"]
        assert schema["properties"]["themes"]["type"] == "array"

    def test_themes_items_have_required_fields(self) -> None:
        """Test theme items have required fields."""
        schema = get_theme_response_schema()
        items_schema = schema["properties"]["themes"]["items"]
        properties = items_schema["properties"]

        assert "theme" in properties
        assert "sector" in properties
        assert "score" in properties
        assert "rationale" in properties
        assert "representative_symbols" in properties

    def test_score_has_bounds(self) -> None:
        """Test score property has min/max bounds."""
        schema = get_theme_response_schema()
        score_schema = schema["properties"]["themes"]["items"]["properties"]["score"]
        assert score_schema["type"] == "number"
        assert score_schema["minimum"] == 0
        assert score_schema["maximum"] == 100

    def test_representative_symbols_is_array(self) -> None:
        """Test representative_symbols is array of strings."""
        schema = get_theme_response_schema()
        symbols_schema = schema["properties"]["themes"]["items"]["properties"][
            "representative_symbols"
        ]
        assert symbols_schema["type"] == "array"
        assert symbols_schema["items"]["type"] == "string"

    def test_has_required_fields(self) -> None:
        """Test has required fields."""
        schema = get_theme_response_schema()
        required = schema["required"]
        assert "themes" in required


class TestGetSectorModelParameters:
    """Tests for sector model parameters."""

    def test_returns_dict(self) -> None:
        """Test returns dictionary."""
        params = get_sector_model_parameters()
        assert isinstance(params, dict)

    def test_has_max_tokens(self) -> None:
        """Test has max_tokens parameter (Claude API)."""
        params = get_sector_model_parameters()
        assert "max_tokens" in params
        assert isinstance(params["max_tokens"], int)
        assert params["max_tokens"] > 0

    def test_has_model(self) -> None:
        """Test has model parameter."""
        params = get_sector_model_parameters()
        assert "model" in params
        assert isinstance(params["model"], str)

    def test_has_temperature(self) -> None:
        """Test has temperature parameter."""
        params = get_sector_model_parameters()
        assert "temperature" in params
        assert 0.0 <= params["temperature"] <= 2.0


class TestGetThemeModelParameters:
    """Tests for theme model parameters."""

    def test_returns_dict(self) -> None:
        """Test returns dictionary."""
        params = get_theme_model_parameters()
        assert isinstance(params, dict)

    def test_has_max_tokens(self) -> None:
        """Test has max_tokens parameter (Claude API)."""
        params = get_theme_model_parameters()
        assert "max_tokens" in params
        assert isinstance(params["max_tokens"], int)
        assert params["max_tokens"] > 0

    def test_has_model(self) -> None:
        """Test has model parameter."""
        params = get_theme_model_parameters()
        assert "model" in params
        assert isinstance(params["model"], str)

    def test_has_temperature(self) -> None:
        """Test has temperature parameter."""
        params = get_theme_model_parameters()
        assert "temperature" in params
        assert 0.0 <= params["temperature"] <= 2.0

    def test_theme_has_more_tokens_than_sector(self) -> None:
        """Test theme analysis allows more tokens than sector analysis."""
        sector_params = get_sector_model_parameters()
        theme_params = get_theme_model_parameters()
        # Theme analysis is typically longer output
        assert theme_params["max_tokens"] >= sector_params["max_tokens"]
