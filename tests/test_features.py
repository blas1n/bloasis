"""Tests for `bloasis.scoring.features` — FeatureVector."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np

from bloasis.scoring.features import FEATURE_COLUMNS, FeatureVector


def test_feature_vector_default_nan() -> None:
    fv = FeatureVector(timestamp=datetime.now(tz=UTC), symbol="AAPL", feature_version=2)
    for col in FEATURE_COLUMNS:
        v = getattr(fv, col)
        assert math.isnan(v), f"{col} should default to NaN, got {v!r}"


def test_feature_vector_to_array_order_matches_columns() -> None:
    fv = FeatureVector(
        timestamp=datetime.now(tz=UTC),
        symbol="X",
        feature_version=2,
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
    fv = FeatureVector(timestamp=datetime.now(tz=UTC), symbol="X", feature_version=2)
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
        feature_version=2,
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
    assert row["feature_version"] == 2


def test_to_db_row_handles_all_nan() -> None:
    fv = FeatureVector(timestamp=datetime.now(tz=UTC), symbol="X", feature_version=2)
    row = fv.to_db_row()
    for col in FEATURE_COLUMNS:
        assert row[col] is None, f"{col} should be None for all-NaN vector"


# ---------------------------------------------------------------------------
# PR12 — feature_version 2 + 5 new fields
# ---------------------------------------------------------------------------


def test_feature_columns_includes_pr12_additions() -> None:
    """Five new features must be present in FEATURE_COLUMNS."""
    new = {"momentum_252_21", "roc_120", "kbar_kmid2", "kbar_ksft2", "corr_pv_20"}
    assert new.issubset(set(FEATURE_COLUMNS)), f"missing: {new - set(FEATURE_COLUMNS)}"


def test_feature_columns_append_only_pr12() -> None:
    """New features must be APPENDED (existing index order preserved)."""
    # Original PR9 ordering — these must keep their original indices.
    pre_pr12 = [
        "per",
        "pbr",
        "market_cap",
        "profit_margin",
        "roe",
        "debt_to_equity",
        "current_ratio",
        "rsi_14",
        "macd",
        "macd_signal",
        "macd_hist",
        "adx_14",
        "atr_14",
        "bb_width",
        "momentum_20d",
        "momentum_60d",
        "volatility_20d",
        "volume_ratio_20d",
        "vix",
        "spy_above_sma200",
        "vix_zscore_60d",
        "sentiment_score",
        "news_count",
    ]
    for i, name in enumerate(pre_pr12):
        assert FEATURE_COLUMNS[i] == name, (
            f"FEATURE_COLUMNS[{i}] should be {name!r} (preserved), got {FEATURE_COLUMNS[i]!r}"
        )


def test_feature_vector_pr12_fields_default_nan() -> None:
    fv = FeatureVector(timestamp=datetime.now(tz=UTC), symbol="X", feature_version=2)
    for col in ("momentum_252_21", "roc_120", "kbar_kmid2", "kbar_ksft2", "corr_pv_20"):
        assert math.isnan(getattr(fv, col)), f"{col} should default to NaN"


def test_feature_vector_pr12_fields_assignable() -> None:
    fv = FeatureVector(
        timestamp=datetime.now(tz=UTC),
        symbol="X",
        feature_version=2,
        momentum_252_21=0.42,
        roc_120=0.18,
        kbar_kmid2=0.6,
        kbar_ksft2=-0.3,
        corr_pv_20=0.25,
    )
    assert fv.momentum_252_21 == 0.42
    assert fv.roc_120 == 0.18
    assert fv.kbar_kmid2 == 0.6
    assert fv.kbar_ksft2 == -0.3
    assert fv.corr_pv_20 == 0.25
    arr = fv.to_array()
    assert arr[FEATURE_COLUMNS.index("momentum_252_21")] == 0.42
    assert arr[FEATURE_COLUMNS.index("kbar_ksft2")] == -0.3
