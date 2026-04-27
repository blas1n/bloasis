"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from bloasis.config import StrategyConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_CONFIG_PATH = REPO_ROOT / "configs" / "baseline.yaml"


@pytest.fixture
def baseline_config_path() -> Path:
    return BASELINE_CONFIG_PATH


@pytest.fixture
def baseline_raw() -> dict:
    with BASELINE_CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    return data


@pytest.fixture
def baseline_config() -> StrategyConfig:
    return StrategyConfig.model_validate(yaml.safe_load(BASELINE_CONFIG_PATH.read_text()))


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Iterator[Path]:
    yield tmp_path / "test.db"
