"""Tests for `bloasis.ml.training` — LightGBM walk-forward training.

The model can learn → IC > 0 on a synthetic linear signal.
The model can NOT learn → IC ≈ 0 on noise.
Round-trip: train → save → load → predict matches.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bloasis.ml.training import (
    DEFAULT_LGBM_PARAMS,
    TrainingResult,
    information_coefficient,
    load_model,
    save_model,
    train_walk_forward,
)


def _synthetic_data(
    n_samples: int = 500, n_features: int = 5, signal_strength: float = 0.5, seed: int = 42
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Toy panel: y = signal · (X[:, 0] + X[:, 1]) + noise.

    Returns (X, y, timestamps). Timestamps are sequential business days.
    """
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_samples, n_features))
    noise = rng.standard_normal(n_samples) * 0.5
    y = signal_strength * (X[:, 0] + X[:, 1]) + noise
    cols = [f"feat_{i}" for i in range(n_features)]
    df_x = pd.DataFrame(X, columns=cols)
    series_y = pd.Series(y, name="label")
    ts = pd.bdate_range("2020-01-01", periods=n_samples, freq="B")
    return df_x, series_y, pd.Series(ts, name="timestamp")


# ---------------------------------------------------------------------------
# information_coefficient
# ---------------------------------------------------------------------------


def test_ic_perfect_correlation_one() -> None:
    a = np.arange(20, dtype=float)
    b = a * 2 + 5
    assert information_coefficient(a, b) == pytest.approx(1.0, abs=1e-9)


def test_ic_anti_correlation_negative_one() -> None:
    a = np.arange(20, dtype=float)
    b = -a * 3
    assert information_coefficient(a, b) == pytest.approx(-1.0, abs=1e-9)


def test_ic_uncorrelated_near_zero() -> None:
    rng = np.random.default_rng(0)
    a = rng.standard_normal(2000)
    b = rng.standard_normal(2000)
    ic = information_coefficient(a, b)
    assert abs(ic) < 0.1


def test_ic_constant_returns_nan() -> None:
    a = np.zeros(10)
    b = np.arange(10, dtype=float)
    import math

    assert math.isnan(information_coefficient(a, b))


# ---------------------------------------------------------------------------
# train_walk_forward — TrainingResult shape
# ---------------------------------------------------------------------------


def test_train_walk_forward_returns_result() -> None:
    X, y, ts = _synthetic_data(n_samples=400)
    result = train_walk_forward(X, y, ts, n_folds=4, embargo_days=5)
    assert isinstance(result, TrainingResult)
    assert len(result.fold_ics) == 4
    assert all(isinstance(ic, float) for ic in result.fold_ics)
    assert result.model is not None
    assert result.feature_names == list(X.columns)


def test_train_walk_forward_has_positive_ic_on_signal() -> None:
    """Linear signal in features → out-of-fold IC should be clearly > 0."""
    X, y, ts = _synthetic_data(n_samples=600, signal_strength=1.0, seed=1)
    result = train_walk_forward(X, y, ts, n_folds=4, embargo_days=5)
    assert result.mean_ic > 0.15, f"expected IC > 0.15 on signal, got {result.mean_ic}"


def test_train_walk_forward_low_ic_on_pure_noise() -> None:
    """No signal → mean IC should be near zero."""
    rng = np.random.default_rng(7)
    X = pd.DataFrame(rng.standard_normal((400, 5)), columns=[f"f{i}" for i in range(5)])
    y = pd.Series(rng.standard_normal(400))
    ts = pd.Series(pd.bdate_range("2020-01-01", periods=400, freq="B"))
    result = train_walk_forward(X, y, ts, n_folds=4, embargo_days=5)
    assert abs(result.mean_ic) < 0.15, f"expected |IC| < 0.15 on noise, got {result.mean_ic}"


def test_train_walk_forward_handles_nan_features() -> None:
    """LightGBM is NaN-native — should not raise on missing values."""
    X, y, ts = _synthetic_data(n_samples=400, signal_strength=0.5, seed=3)
    # Inject 5% NaN
    rng = np.random.default_rng(0)
    mask = rng.random(X.shape) < 0.05
    X = X.where(~mask)
    result = train_walk_forward(X, y, ts, n_folds=4, embargo_days=5)
    assert result.mean_ic is not None
    assert result.model is not None


def test_train_walk_forward_default_params_used_when_none() -> None:
    X, y, ts = _synthetic_data(n_samples=300)
    result = train_walk_forward(X, y, ts, n_folds=3, embargo_days=5, params=None)
    assert result.params == DEFAULT_LGBM_PARAMS


def test_train_walk_forward_too_few_samples_raises() -> None:
    X, y, ts = _synthetic_data(n_samples=10)
    with pytest.raises(ValueError, match="too few"):
        train_walk_forward(X, y, ts, n_folds=5, embargo_days=5)


# ---------------------------------------------------------------------------
# Model save / load (pickle + JSON sidecar)
# ---------------------------------------------------------------------------


def test_save_load_roundtrip_predicts_identical(tmp_path: Path) -> None:
    X, y, ts = _synthetic_data(n_samples=300, seed=11)
    result = train_walk_forward(X, y, ts, n_folds=3, embargo_days=5)

    model_path = tmp_path / "model.pkl"
    save_model(
        result,
        model_path,
        feature_version=2,
        label_name="label_20d",
        extra={"comment": "smoke"},
    )
    assert model_path.exists()
    sidecar = model_path.with_suffix(".json")
    assert sidecar.exists()
    meta = json.loads(sidecar.read_text())
    assert meta["feature_version"] == 2
    assert meta["label_name"] == "label_20d"
    assert meta["feature_names"] == list(X.columns)
    assert "fold_ics" in meta and len(meta["fold_ics"]) == 3
    assert "mean_ic" in meta
    assert meta["extra"]["comment"] == "smoke"

    loaded = load_model(model_path)
    # Predictions deterministic — round-trip identical.
    p0 = result.model.predict(X.iloc[:50])
    p1 = loaded.predict(X.iloc[:50])
    np.testing.assert_array_almost_equal(p0, p1, decimal=8)


def test_save_model_creates_parent_dir(tmp_path: Path) -> None:
    X, y, ts = _synthetic_data(n_samples=200, seed=13)
    result = train_walk_forward(X, y, ts, n_folds=3, embargo_days=5)
    nested = tmp_path / "deep" / "nest" / "model.pkl"
    save_model(result, nested, feature_version=2, label_name="label_20d")
    assert nested.exists()
    assert nested.with_suffix(".json").exists()
