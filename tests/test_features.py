"""Tests for `bloasis.scoring.features` — FeatureVector."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np

from bloasis.scoring.features import FEATURE_COLUMNS, FeatureVector


def test_feature_vector_default_nan() -> None:
    fv = FeatureVector(timestamp=datetime.now(tz=UTC), symbol="AAPL", feature_version=1)
    for col in FEATURE_COLUMNS:
        v = getattr(fv, col)
        assert math.isnan(v), f"{col} should default to NaN, got {v!r}"


def test_feature_vector_to_array_order_matches_columns() -> None:
    fv = FeatureVector(
        timestamp=datetime.now(tz=UTC),
        symbol="X",
        feature_version=1,
        per=10.0,
        rsi_14=55.0,
    )
    arr = fv.to_array()
    assert arr.shape == (len(FEATURE_COLUMNS),)
    assert arr[FEATURE_COLUMNS.index("per")] == 10.0
    assert arr[FEATURE_COLUMNS.index("rsi_14")] == 55.0
    # All others NaN
    for i, col in enumerate(FEATURE_COLUMNS):
        if col not in {"per", "rsi_14"}:
            assert np.isnan(arr[i])


def test_feature_vector_immutable() -> None:
    fv = FeatureVector(timestamp=datetime.now(tz=UTC), symbol="X", feature_version=1)
    import dataclasses

    try:
        fv.per = 1.0  # type: ignore[misc]
    except (dataclasses.FrozenInstanceError, AttributeError):
        pass
    else:
        raise AssertionError("FeatureVector should be immutable")


def test_to_db_row_replaces_nan_with_none() -> None:
    fv = FeatureVector(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        symbol="X",
        feature_version=1,
        per=10.0,
        spy_above_sma200=1.0,
        news_count=5.0,
    )
    row = fv.to_db_row()
    assert row["per"] == 10.0
    assert row["pbr"] is None  # NaN → None
    assert row["spy_above_sma200"] == 1  # int conversion
    assert row["news_count"] == 5
    assert row["timestamp"] == datetime(2024, 1, 1, tzinfo=UTC)
    assert row["symbol"] == "X"
    assert row["feature_version"] == 1


def test_to_db_row_handles_all_nan() -> None:
    fv = FeatureVector(timestamp=datetime.now(tz=UTC), symbol="X", feature_version=1)
    row = fv.to_db_row()
    for col in FEATURE_COLUMNS:
        assert row[col] is None, f"{col} should be None for all-NaN vector"
