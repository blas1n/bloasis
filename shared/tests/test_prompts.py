"""
Tests for shared prompts module.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from shared.prompts import (
    PromptLoader,
    clear_prompt_cache,
    format_prompt,
    get_model_parameters,
    get_response_schema,
)


@pytest.fixture
def temp_prompts_dir():
    """Create a temporary directory with sample prompt files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prompts_dir = Path(tmpdir)

        # Create sample prompt file
        sample_config = {
            "system_prompt": "You are a helpful assistant.",
            "user_prompt_template": "Analyze {topic} for {regime} market.",
            "default_values": {
                "topic": "stocks",
                "regime": "bull",
            },
            "response_schema": {
                "type": "object",
                "properties": {
                    "analysis": {"type": "string"},
                },
            },
            "model_parameters": {
                "max_new_tokens": 1000,
                "temperature": 0.7,
            },
        }
        with open(prompts_dir / "sample.yaml", "w") as f:
            yaml.dump(sample_config, f)

        # Create another prompt file for testing list_prompts
        another_config = {"system_prompt": "Another prompt."}
        with open(prompts_dir / "another.yaml", "w") as f:
            yaml.dump(another_config, f)

        # Create a file that should be ignored (starts with _)
        ignored_config = {"system_prompt": "Ignored."}
        with open(prompts_dir / "_ignored.yaml", "w") as f:
            yaml.dump(ignored_config, f)

        yield prompts_dir


@pytest.fixture(autouse=True)
def clear_cache_before_each():
    """Clear the prompt cache before each test."""
    clear_prompt_cache()
    yield
    clear_prompt_cache()


class TestPromptLoader:
    """Tests for PromptLoader class."""

    def test_init_with_path(self, temp_prompts_dir: Path) -> None:
        """Test initialization with Path object."""
        loader = PromptLoader(temp_prompts_dir)
        assert loader.prompts_dir == temp_prompts_dir

    def test_init_with_string(self, temp_prompts_dir: Path) -> None:
        """Test initialization with string path."""
        loader = PromptLoader(str(temp_prompts_dir))
        assert loader.prompts_dir == temp_prompts_dir

    def test_load_prompt(self, temp_prompts_dir: Path) -> None:
        """Test loading a prompt configuration."""
        loader = PromptLoader(temp_prompts_dir)
        config = loader.load("sample")

        assert config["system_prompt"] == "You are a helpful assistant."
        assert "user_prompt_template" in config
        assert "response_schema" in config

    def test_load_prompt_with_cache(self, temp_prompts_dir: Path) -> None:
        """Test that loading uses cache by default."""
        loader = PromptLoader(temp_prompts_dir)

        # First load
        config1 = loader.load("sample")

        # Modify the file
        modified_config = {"system_prompt": "Modified."}
        with open(temp_prompts_dir / "sample.yaml", "w") as f:
            yaml.dump(modified_config, f)

        # Second load should return cached version
        config2 = loader.load("sample")
        assert config2["system_prompt"] == config1["system_prompt"]

    def test_load_prompt_bypass_cache(self, temp_prompts_dir: Path) -> None:
        """Test loading without cache."""
        loader = PromptLoader(temp_prompts_dir)

        # First load
        loader.load("sample")

        # Modify the file
        modified_config = {"system_prompt": "Modified."}
        with open(temp_prompts_dir / "sample.yaml", "w") as f:
            yaml.dump(modified_config, f)

        # Load without cache
        config = loader.load("sample", use_cache=False)
        assert config["system_prompt"] == "Modified."

    def test_reload_prompt(self, temp_prompts_dir: Path) -> None:
        """Test reload method bypasses cache."""
        loader = PromptLoader(temp_prompts_dir)

        # First load
        loader.load("sample")

        # Modify the file
        modified_config = {"system_prompt": "Reloaded."}
        with open(temp_prompts_dir / "sample.yaml", "w") as f:
            yaml.dump(modified_config, f)

        # Reload
        config = loader.reload("sample")
        assert config["system_prompt"] == "Reloaded."

    def test_load_nonexistent_prompt(self, temp_prompts_dir: Path) -> None:
        """Test loading a non-existent prompt raises FileNotFoundError."""
        loader = PromptLoader(temp_prompts_dir)

        with pytest.raises(FileNotFoundError, match="Prompt file not found"):
            loader.load("nonexistent")

    def test_list_prompts(self, temp_prompts_dir: Path) -> None:
        """Test listing available prompts."""
        loader = PromptLoader(temp_prompts_dir)
        prompts = loader.list_prompts()

        assert "sample" in prompts
        assert "another" in prompts
        assert "_ignored" not in prompts

    def test_list_prompts_empty_dir(self) -> None:
        """Test listing prompts in non-existent directory."""
        loader = PromptLoader(Path("/nonexistent/dir"))
        prompts = loader.list_prompts()
        assert prompts == []

    def test_clear_cache(self, temp_prompts_dir: Path) -> None:
        """Test clearing cache for specific loader."""
        loader = PromptLoader(temp_prompts_dir)

        # Load and cache
        loader.load("sample")

        # Modify the file
        modified_config = {"system_prompt": "After clear."}
        with open(temp_prompts_dir / "sample.yaml", "w") as f:
            yaml.dump(modified_config, f)

        # Clear cache
        loader.clear_cache()

        # Load should get new version
        config = loader.load("sample")
        assert config["system_prompt"] == "After clear."


class TestFormatPrompt:
    """Tests for format_prompt function."""

    def test_format_prompt_basic(self, temp_prompts_dir: Path) -> None:
        """Test basic prompt formatting."""
        loader = PromptLoader(temp_prompts_dir)
        config = loader.load("sample")

        system_prompt, user_prompt = format_prompt(
            config,
            {"topic": "tech stocks", "regime": "bear"},
        )

        assert system_prompt == "You are a helpful assistant."
        assert "tech stocks" in user_prompt
        assert "bear" in user_prompt

    def test_format_prompt_with_defaults(self, temp_prompts_dir: Path) -> None:
        """Test that defaults are used when variables not provided."""
        loader = PromptLoader(temp_prompts_dir)
        config = loader.load("sample")

        system_prompt, user_prompt = format_prompt(config, {})

        assert "stocks" in user_prompt
        assert "bull" in user_prompt

    def test_format_prompt_override_defaults(self, temp_prompts_dir: Path) -> None:
        """Test that provided variables override defaults."""
        loader = PromptLoader(temp_prompts_dir)
        config = loader.load("sample")

        _, user_prompt = format_prompt(
            config,
            {"topic": "crypto"},  # Only override topic, use default regime
        )

        assert "crypto" in user_prompt
        assert "bull" in user_prompt  # Default value

    def test_format_prompt_missing_variable(self) -> None:
        """Test that missing variables raise KeyError."""
        config = {
            "system_prompt": "System",
            "user_prompt_template": "Hello {name}, welcome to {place}",
            "default_values": {},
        }

        with pytest.raises(KeyError, match="Missing variable"):
            format_prompt(config, {"name": "Alice"})


class TestSchemaAndParameters:
    """Tests for schema and parameter retrieval functions."""

    def test_get_response_schema(self, temp_prompts_dir: Path) -> None:
        """Test getting response schema."""
        loader = PromptLoader(temp_prompts_dir)
        config = loader.load("sample")

        schema = get_response_schema(config)

        assert schema["type"] == "object"
        assert "properties" in schema

    def test_get_response_schema_empty(self) -> None:
        """Test getting schema when not present."""
        config = {"system_prompt": "Test"}
        schema = get_response_schema(config)
        assert schema == {}

    def test_get_model_parameters(self, temp_prompts_dir: Path) -> None:
        """Test getting model parameters."""
        loader = PromptLoader(temp_prompts_dir)
        config = loader.load("sample")

        params = get_model_parameters(config)

        assert params["max_new_tokens"] == 1000
        assert params["temperature"] == 0.7

    def test_get_model_parameters_empty(self) -> None:
        """Test getting parameters when not present."""
        config = {"system_prompt": "Test"}
        params = get_model_parameters(config)
        assert params == {}


class TestClearPromptCache:
    """Tests for global cache clearing function."""

    def test_clear_prompt_cache(self, temp_prompts_dir: Path) -> None:
        """Test clearing the global prompt cache."""
        loader = PromptLoader(temp_prompts_dir)

        # Load and cache
        loader.load("sample")

        # Modify the file
        modified_config = {"system_prompt": "After global clear."}
        with open(temp_prompts_dir / "sample.yaml", "w") as f:
            yaml.dump(modified_config, f)

        # Clear global cache
        clear_prompt_cache()

        # Load should get new version
        config = loader.load("sample")
        assert config["system_prompt"] == "After global clear."
