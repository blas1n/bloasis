"""Tests for Strategy service prompts module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.prompts import (
    PromptLoader,
    format_macro_prompt,
    format_regime_risk_prompt,
    format_risk_prompt,
    format_technical_prompt,
    get_loader,
    get_macro_model_parameters,
    get_macro_response_schema,
    get_regime_risk_model_parameters,
    get_risk_model_parameters,
    get_risk_response_schema,
    get_technical_model_parameters,
    get_technical_response_schema,
    load_prompt,
)


class TestGetLoader:
    """Tests for get_loader function."""

    def test_get_loader_returns_prompt_loader(self):
        """Test that get_loader returns a PromptLoader instance."""
        # Reset the default loader
        import src.prompts as prompts_module

        prompts_module._default_loader = None

        loader = get_loader()

        assert isinstance(loader, PromptLoader)
        # Clean up
        prompts_module._default_loader = None

    def test_get_loader_returns_singleton(self):
        """Test that get_loader returns same instance on repeated calls."""
        import src.prompts as prompts_module

        prompts_module._default_loader = None

        loader1 = get_loader()
        loader2 = get_loader()

        assert loader1 is loader2
        # Clean up
        prompts_module._default_loader = None


class TestLoadPrompt:
    """Tests for load_prompt function."""

    def test_load_prompt_macro_strategist(self):
        """Test loading macro strategist prompt."""
        result = load_prompt("macro_strategist")

        assert "system_prompt" in result
        assert "user_prompt_template" in result
        assert "response_schema" in result
        assert "model_parameters" in result

    def test_load_prompt_technical_analyst(self):
        """Test loading technical analyst prompt."""
        result = load_prompt("technical_analyst")

        assert "system_prompt" in result
        assert "user_prompt_template" in result

    def test_load_prompt_risk_manager(self):
        """Test loading risk manager prompt."""
        result = load_prompt("risk_manager")

        assert "system_prompt" in result
        assert "user_prompt_template" in result

    def test_load_prompt_not_found(self):
        """Test loading non-existent prompt raises error."""
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt")


class TestPromptLoaderEdgeCases:
    """Tests for PromptLoader edge cases."""

    def test_loader_with_string_path(self):
        """Test PromptLoader with string path instead of Path."""
        loader = PromptLoader("/workspace/services/strategy/src/prompts")
        assert loader.prompts_dir == Path("/workspace/services/strategy/src/prompts")

    def test_loader_reload_bypasses_cache(self):
        """Test that reload bypasses cache."""
        loader = PromptLoader(Path("/workspace/services/strategy/src/prompts"))

        # Load with cache
        first = loader.load("macro_strategist")

        # Reload should bypass cache
        reloaded = loader.reload("macro_strategist")

        assert first is not None
        assert reloaded is not None

    def test_loader_clear_cache(self):
        """Test clearing loader cache."""
        loader = PromptLoader(Path("/workspace/services/strategy/src/prompts"))

        # Load to populate cache
        loader.load("macro_strategist")

        # Clear cache
        loader.clear_cache()

        # Should be able to load again
        result = loader.load("macro_strategist")
        assert result is not None

    def test_loader_list_prompts(self):
        """Test listing available prompts."""
        loader = PromptLoader(Path("/workspace/services/strategy/src/prompts"))

        prompts = loader.list_prompts()

        assert "macro_strategist" in prompts
        assert "technical_analyst" in prompts
        assert "risk_manager" in prompts

    def test_loader_list_prompts_nonexistent_dir(self):
        """Test listing prompts from nonexistent directory."""
        loader = PromptLoader(Path("/nonexistent/directory"))

        prompts = loader.list_prompts()

        assert prompts == []

    def test_loader_load_without_cache(self):
        """Test loading prompt without caching."""
        loader = PromptLoader(Path("/workspace/services/strategy/src/prompts"))

        result = loader.load("macro_strategist", use_cache=False)

        assert result is not None
        assert "system_prompt" in result


class TestFormatMacroPrompt:
    """Tests for format_macro_prompt function."""

    def test_format_macro_prompt_with_values(self):
        """Test formatting macro prompt with values."""
        system_prompt, user_prompt = format_macro_prompt(
            symbols=["AAPL", "MSFT"],
            regime="normal_bull",
            sectors=["Technology"],
        )

        assert "macro strategist" in system_prompt.lower()
        assert "AAPL, MSFT" in user_prompt
        assert "normal_bull" in user_prompt
        assert "Technology" in user_prompt

    def test_format_macro_prompt_with_empty_values(self):
        """Test formatting macro prompt with empty values (uses defaults)."""
        system_prompt, user_prompt = format_macro_prompt(
            symbols=[],
            regime="",
            sectors=[],
        )

        assert system_prompt  # Should still have system prompt
        assert user_prompt  # Should still have user prompt

    def test_format_macro_prompt_strips_whitespace(self):
        """Test that prompt formatting strips leading/trailing whitespace."""
        system_prompt, user_prompt = format_macro_prompt(
            symbols=["AAPL"],
            regime="normal",
            sectors=["Tech"],
        )

        assert not system_prompt.startswith("\n")
        assert not system_prompt.endswith("\n")
        assert not user_prompt.startswith("\n")
        assert not user_prompt.endswith("\n")


class TestFormatTechnicalPrompt:
    """Tests for format_technical_prompt function."""

    def test_format_technical_prompt_with_values(self):
        """Test formatting technical prompt with values."""
        stock_data = [{"symbol": "AAPL", "factor_scores": {"momentum": 0.8}}]
        market_context = {
            "regime": "normal_bull",
            "risk_level": "medium",
            "sector_outlook": {"Technology": 75},
        }

        system_prompt, user_prompt = format_technical_prompt(
            stock_data=stock_data,
            ohlcv_summary="Sample OHLCV data",
            market_context=market_context,
        )

        assert system_prompt  # Should have system prompt
        assert "AAPL" in user_prompt
        assert "normal_bull" in user_prompt
        assert "medium" in user_prompt


class TestFormatRiskPrompt:
    """Tests for format_risk_prompt function."""

    def test_format_risk_prompt_with_values(self):
        """Test formatting risk prompt with values."""
        signals = [{"symbol": "AAPL", "direction": "long", "strength": 0.8}]
        market_context = {"regime": "normal_bull", "risk_level": "medium"}
        user_preferences = {
            "risk_profile": "MODERATE",
            "max_single_position": 0.10,
            "excluded_sectors": ["Energy"],
        }

        system_prompt, user_prompt = format_risk_prompt(
            signals=signals,
            market_context=market_context,
            user_preferences=user_preferences,
        )

        assert system_prompt  # Should have system prompt
        assert "MODERATE" in user_prompt
        assert "10" in user_prompt  # max_single_position * 100
        assert "Energy" in user_prompt

    def test_format_risk_prompt_with_defaults(self):
        """Test formatting risk prompt with default values."""
        signals = [{"symbol": "AAPL", "direction": "long", "strength": 0.8}]
        market_context = {"regime": "normal_bull", "risk_level": "medium"}
        user_preferences = {}  # Empty, should use defaults

        system_prompt, user_prompt = format_risk_prompt(
            signals=signals,
            market_context=market_context,
            user_preferences=user_preferences,
        )

        assert system_prompt  # Should have system prompt
        assert user_prompt  # Should have user prompt

    def test_format_risk_prompt_empty_excluded_sectors(self):
        """Test formatting risk prompt with no excluded sectors."""
        signals = [{"symbol": "AAPL", "direction": "long"}]
        market_context = {"regime": "normal_bull", "risk_level": "medium"}
        user_preferences = {"excluded_sectors": []}

        system_prompt, user_prompt = format_risk_prompt(
            signals=signals,
            market_context=market_context,
            user_preferences=user_preferences,
        )

        assert "None" in user_prompt  # Empty excluded sectors shows "None"


class TestFormatRegimeRiskPrompt:
    """Tests for format_regime_risk_prompt function."""

    def test_format_regime_risk_prompt(self):
        """Test formatting regime risk prompt."""
        system_prompt, user_prompt = format_regime_risk_prompt(
            regime="crisis",
            indicators={"vix": 35, "yield_curve": "inverted"},
        )

        assert system_prompt  # Should have system prompt
        assert "crisis" in user_prompt
        assert "vix" in user_prompt


class TestGetResponseSchemas:
    """Tests for response schema getter functions."""

    def test_get_macro_response_schema(self):
        """Test getting macro response schema."""
        schema = get_macro_response_schema()

        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_get_technical_response_schema(self):
        """Test getting technical response schema."""
        schema = get_technical_response_schema()

        assert schema is not None
        # Schema might be empty if not defined in YAML

    def test_get_risk_response_schema(self):
        """Test getting risk response schema."""
        schema = get_risk_response_schema()

        assert schema is not None


class TestGetModelParameters:
    """Tests for model parameters getter functions."""

    def test_get_macro_model_parameters(self):
        """Test getting macro model parameters."""
        params = get_macro_model_parameters()

        assert "max_new_tokens" in params or "temperature" in params

    def test_get_technical_model_parameters(self):
        """Test getting technical model parameters."""
        params = get_technical_model_parameters()

        assert params is not None

    def test_get_risk_model_parameters(self):
        """Test getting risk model parameters."""
        params = get_risk_model_parameters()

        assert params is not None

    def test_get_regime_risk_model_parameters(self):
        """Test getting regime risk model parameters."""
        params = get_regime_risk_model_parameters()

        assert params is not None


class TestPromptLoaderWithTempFiles:
    """Tests for PromptLoader using temporary files."""

    def test_loader_loads_yaml_content(self):
        """Test that loader correctly parses YAML content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test prompt YAML
            prompt_content = {
                "system_prompt": "Test system prompt",
                "user_prompt_template": "Hello {name}",
                "model_parameters": {"temperature": 0.5},
            }
            prompt_file = Path(tmpdir) / "test_prompt.yaml"
            with open(prompt_file, "w") as f:
                yaml.dump(prompt_content, f)

            loader = PromptLoader(tmpdir)
            result = loader.load("test_prompt")

            assert result["system_prompt"] == "Test system prompt"
            assert result["user_prompt_template"] == "Hello {name}"
            assert result["model_parameters"]["temperature"] == 0.5

    def test_loader_caches_loaded_prompts(self):
        """Test that loader caches loaded prompts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_content = {"system_prompt": "Cached prompt"}
            prompt_file = Path(tmpdir) / "cached_test.yaml"
            with open(prompt_file, "w") as f:
                yaml.dump(prompt_content, f)

            loader = PromptLoader(tmpdir)

            # First load
            result1 = loader.load("cached_test")

            # Delete the file
            prompt_file.unlink()

            # Second load should use cache (file is gone)
            result2 = loader.load("cached_test")

            assert result1 == result2

    def test_loader_raises_on_missing_file(self):
        """Test that loader raises FileNotFoundError for missing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PromptLoader(tmpdir)

            with pytest.raises(FileNotFoundError) as exc_info:
                loader.load("missing_prompt")

            assert "missing_prompt" in str(exc_info.value)
