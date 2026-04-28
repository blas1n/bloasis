"""Tests for `bloasis.backtest.statistical`."""

from __future__ import annotations

import pytest

from bloasis.backtest.statistical import bootstrap_ci, white_reality_check_p_value


def test_bootstrap_ci_basic_mean() -> None:
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = bootstrap_ci(samples, statistic="mean", n_resamples=500, seed=42)
    assert result.point_estimate == pytest.approx(3.0)
    assert result.lower < result.point_estimate < result.upper


def test_bootstrap_ci_median() -> None:
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = bootstrap_ci(samples, statistic="median", n_resamples=500, seed=42)
    assert result.point_estimate == pytest.approx(3.0)


def test_bootstrap_ci_empty_returns_zeros() -> None:
    result = bootstrap_ci([], statistic="mean")
    assert result.point_estimate == 0.0
    assert result.lower == 0.0
    assert result.upper == 0.0
    assert result.n_resamples == 0


def test_bootstrap_ci_invalid_statistic_raises() -> None:
    with pytest.raises(ValueError, match="unknown statistic"):
        bootstrap_ci([1.0, 2.0], statistic="bogus")


def test_bootstrap_ci_invalid_confidence_raises() -> None:
    with pytest.raises(ValueError, match="confidence_level"):
        bootstrap_ci([1.0, 2.0], confidence_level=1.5)
    with pytest.raises(ValueError, match="confidence_level"):
        bootstrap_ci([1.0, 2.0], confidence_level=0.0)


def test_bootstrap_ci_deterministic_with_seed() -> None:
    samples = [1.0, 5.0, 2.0, 4.0, 3.0]
    a = bootstrap_ci(samples, n_resamples=100, seed=42)
    b = bootstrap_ci(samples, n_resamples=100, seed=42)
    assert a.lower == b.lower
    assert a.upper == b.upper


def test_white_reality_check_p_in_range() -> None:
    # All positive alphas → small p-value (significant).
    p = white_reality_check_p_value([0.05, 0.06, 0.04, 0.07, 0.05])
    assert 0.0 <= p <= 1.0
    assert p < 0.5  # mean is positive, randomized signs should rarely exceed


def test_white_reality_check_handles_empty() -> None:
    assert white_reality_check_p_value([]) == 1.0
