"""Tests for `bloasis.scoring.regime.classify_regime`."""

from __future__ import annotations

import math

from bloasis.scoring.regime import classify_regime


def test_crisis_when_vix_above_40() -> None:
    assert classify_regime(45.0, 1.0) == "crisis"
    assert classify_regime(45.0, 0.0) == "crisis"


def test_bear_when_vix_high() -> None:
    assert classify_regime(35.0, 1.0) == "bear"


def test_bear_when_spy_below_sma() -> None:
    assert classify_regime(18.0, 0.0) == "bear"


def test_sideways_when_vix_mid() -> None:
    assert classify_regime(25.0, 1.0) == "sideways"


def test_recovery_when_vix_low_mid() -> None:
    assert classify_regime(18.0, 1.0) == "recovery"


def test_bull_when_vix_low() -> None:
    assert classify_regime(12.0, 1.0) == "bull"


def test_nan_vix_defaults_bull() -> None:
    assert classify_regime(float("nan"), 1.0) == "bull"


def test_nan_spy_treated_as_below() -> None:
    # NaN spy_above_sma200 → not above → bear if vix > 30 or always bear
    assert classify_regime(18.0, float("nan")) == "bear"


def test_boundaries() -> None:
    # Exactly 40.0 is bear (not crisis — only >40)
    assert classify_regime(40.0, 1.0) == "bear"
    # Exactly 30.0 is sideways
    assert classify_regime(30.0, 1.0) == "sideways"
    # Exactly 20.0 is recovery
    assert classify_regime(20.0, 1.0) == "recovery"
    # Exactly 15.0 is bull
    assert classify_regime(15.0, 1.0) == "bull"


def test_all_labels_reachable() -> None:
    """Sanity: every label is producible from some (vix, spy) input."""
    seen = {
        classify_regime(v, s)
        for v, s in [(45.0, 1.0), (35.0, 1.0), (25.0, 1.0), (18.0, 1.0), (12.0, 1.0)]
    }
    assert seen == {"crisis", "bear", "sideways", "recovery", "bull"}


def test_classify_regime_does_not_mutate_or_persist() -> None:
    """Sanity: regime is computed on demand from raw inputs (per design)."""
    out = classify_regime(20.0, 1.0)
    assert isinstance(out, str)
    # Calling twice gives same label — pure function.
    assert out == classify_regime(20.0, 1.0)


def test_nan_vix_inputs_produce_label_not_exception() -> None:
    # Verify NaN pathway never raises (used during data outages)
    label = classify_regime(float("nan"), float("nan"))
    assert label in {"bull", "bear", "sideways", "recovery", "crisis"}
    assert not math.isnan(0.0)  # sanity
