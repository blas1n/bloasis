"""Tests for bloasis.data.cache.ParquetCache."""

from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

from bloasis.data.cache import ParquetCache


@pytest.fixture
def cache(tmp_path: Path) -> ParquetCache:
    return ParquetCache(tmp_path / "cache", namespace="test")


@pytest.fixture
def df() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    return pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]}, index=idx)


def test_put_then_get_roundtrip(cache: ParquetCache, df: pd.DataFrame) -> None:
    cache.put("AAPL", df)
    out = cache.get("AAPL", max_age=timedelta(hours=1))
    assert out is not None
    # parquet drops DatetimeIndex freq; values should still match.
    pd.testing.assert_frame_equal(out, df, check_freq=False)


def test_get_missing_returns_none(cache: ParquetCache) -> None:
    assert cache.get("NOPE", max_age=timedelta(hours=1)) is None


def test_get_stale_returns_none(cache: ParquetCache, df: pd.DataFrame, tmp_path: Path) -> None:
    cache.put("AAPL", df)
    # Backdate the file mtime so it's stale.
    target = cache._path("AAPL")
    old = time.time() - 10_000
    os.utime(target, (old, old))
    assert cache.get("AAPL", max_age=timedelta(hours=1)) is None


def test_invalidate_removes_file(cache: ParquetCache, df: pd.DataFrame) -> None:
    cache.put("AAPL", df)
    assert cache._path("AAPL").exists()
    cache.invalidate("AAPL")
    assert not cache._path("AAPL").exists()


def test_invalidate_missing_is_noop(cache: ParquetCache) -> None:
    cache.invalidate("MISSING")  # must not raise


def test_special_chars_in_key_sanitized(cache: ParquetCache, df: pd.DataFrame) -> None:
    cache.put("FOO/BAR", df)
    out = cache.get("FOO/BAR", max_age=timedelta(hours=1))
    assert out is not None
    assert "/" not in cache._path("FOO/BAR").name
