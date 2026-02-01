"""
Prompt loader for YAML-based prompt management.

Provides caching and validation for prompt configurations.
Future: Can be extended to support remote prompt storage, versioning, A/B testing.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# In-memory cache for loaded prompts
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
    """

    def __init__(self, prompts_dir: Optional[Path] = None) -> None:
        """
        Initialize the prompt loader.

        Args:
            prompts_dir: Directory containing prompt YAML files.
                        Defaults to the directory of this module.
        """
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent
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
        """Clear all cached prompts."""
        _cache.clear()
        logger.info("Prompt cache cleared")

    def list_prompts(self) -> list[str]:
        """
        List all available prompt files.

        Returns:
            List of prompt names (without .yaml extension).
        """
        return [
            f.stem for f in self.prompts_dir.glob("*.yaml")
            if not f.name.startswith("_")
        ]


# Default loader instance
_default_loader: Optional[PromptLoader] = None


def get_loader() -> PromptLoader:
    """Get the default prompt loader instance."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader


def load_prompt(name: str) -> dict[str, Any]:
    """
    Load a prompt using the default loader.

    Args:
        name: Prompt file name without extension.

    Returns:
        Parsed prompt configuration.
    """
    return get_loader().load(name)
