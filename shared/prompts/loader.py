"""
Prompt loader for YAML-based prompt management.

Provides caching and validation for prompt configurations.
Future: Can be extended to support remote prompt storage, versioning, A/B testing.
"""

import logging
from pathlib import Path
from typing import Any, Union

import yaml

logger = logging.getLogger(__name__)

# Global in-memory cache for loaded prompts
# Key: "{prompts_dir}:{name}" -> Value: parsed YAML content
_cache: dict[str, dict[str, Any]] = {}


class PromptLoader:
    """
    Loads and caches prompt configurations from YAML files.

    Features:
    - File-based YAML prompts
    - In-memory caching
    - Validation support

    Future extensions:
    - Remote prompt storage (S3, database)
    - Prompt versioning
    - A/B testing support
    - Hot reloading

    Example:
        loader = PromptLoader(Path("/workspace/services/strategy/src/prompts"))
        config = loader.load("macro_strategist")
        system_prompt = config.get("system_prompt", "")
    """

    def __init__(self, prompts_dir: Union[Path, str]) -> None:
        """
        Initialize the prompt loader.

        Args:
            prompts_dir: Directory containing prompt YAML files.
        """
        if isinstance(prompts_dir, str):
            prompts_dir = Path(prompts_dir)
        self.prompts_dir = prompts_dir

    def load(self, name: str, use_cache: bool = True) -> dict[str, Any]:
        """
        Load a prompt configuration from YAML.

        Args:
            name: Prompt file name without extension.
            use_cache: Whether to use cached version if available.

        Returns:
            Parsed YAML content as dictionary.

        Raises:
            FileNotFoundError: If prompt file doesn't exist.
            yaml.YAMLError: If YAML parsing fails.
        """
        cache_key = f"{self.prompts_dir}:{name}"

        if use_cache and cache_key in _cache:
            return _cache[cache_key]

        prompt_file = self.prompts_dir / f"{name}.yaml"

        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

        logger.debug(f"Loading prompt from: {prompt_file}")

        with open(prompt_file, encoding="utf-8") as f:
            content = yaml.safe_load(f)

        if use_cache:
            _cache[cache_key] = content

        return content

    def reload(self, name: str) -> dict[str, Any]:
        """
        Force reload a prompt, bypassing cache.

        Args:
            name: Prompt file name without extension.

        Returns:
            Freshly loaded prompt configuration.
        """
        return self.load(name, use_cache=False)

    def clear_cache(self) -> None:
        """Clear all cached prompts for this loader's directory."""
        keys_to_remove = [
            key for key in _cache if key.startswith(f"{self.prompts_dir}:")
        ]
        for key in keys_to_remove:
            del _cache[key]
        logger.info(f"Prompt cache cleared for {self.prompts_dir}")

    def list_prompts(self) -> list[str]:
        """
        List all available prompt files.

        Returns:
            List of prompt names (without .yaml extension).
        """
        if not self.prompts_dir.exists():
            return []
        return [
            f.stem
            for f in self.prompts_dir.glob("*.yaml")
            if not f.name.startswith("_")
        ]


def clear_prompt_cache() -> None:
    """Clear the global prompt cache."""
    _cache.clear()
    logger.info("Global prompt cache cleared")
