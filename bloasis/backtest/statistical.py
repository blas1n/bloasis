"""Statistical significance tests for backtest results.

Phase 1 ships a basic bootstrap CI helper and a White Reality Check stub.
Phase 2/3 expand these — the API surface is stable so reporting code can
reference them today without re-wiring.

Design intent: a backtest with high alpha and a `p-value > 0.10` from the
reality check is treated as "statistically indistinguishable from luck"
and refused promotion to live trading.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Bootstrap confidence interval for a scalar statistic."""

    point_estimate: float
    lower: float  # confidence_level low bound
    upper: float  # confidence_level high bound
    confidence_level: float
    n_resamples: int


def bootstrap_ci(
    samples: Sequence[float],
    *,
    statistic: str = "mean",
    confidence_level: float = 0.95,
    n_resamples: int = 1000,
    seed: int = 42,
) -> BootstrapResult:
    """Percentile bootstrap CI for a scalar statistic of `samples`.

    `statistic` is one of {"mean", "median"}. We sample with replacement
    `n_resamples` times, compute the statistic on each resample, and
    return the empirical percentile bounds.

    Used in `BacktestResult` reporting to quantify "how confident are we
    that median_alpha > 0?".
    """
    if not samples:
        return BootstrapResult(
            point_estimate=0.0,
            lower=0.0,
            upper=0.0,
            confidence_level=confidence_level,
            n_resamples=0,
        )
    if not (0.0 < confidence_level < 1.0):
        raise ValueError("confidence_level must be in (0, 1)")
    if statistic not in {"mean", "median"}:
        raise ValueError(f"unknown statistic {statistic!r}")

    rng = np.random.default_rng(seed)
    arr = np.asarray(samples, dtype=np.float64)
    fn = np.mean if statistic == "mean" else np.median
    point = float(fn(arr))

    boot_stats = np.empty(n_resamples, dtype=np.float64)
    n = arr.size
    for i in range(n_resamples):
        resample = rng.choice(arr, size=n, replace=True)
        boot_stats[i] = fn(resample)

    alpha = (1.0 - confidence_level) / 2.0
    low = float(np.quantile(boot_stats, alpha))
    high = float(np.quantile(boot_stats, 1.0 - alpha))
    return BootstrapResult(
        point_estimate=point,
        lower=low,
        upper=high,
        confidence_level=confidence_level,
        n_resamples=n_resamples,
    )


def white_reality_check_p_value(
    fold_alphas: Sequence[float],
    *,
    n_resamples: int = 2000,
    seed: int = 42,
) -> float:
    """Stub implementation of White's Reality Check.

    Tests the null hypothesis "best observed strategy is no better than
    the benchmark". We shuffle the sign of fold_alphas and count how
    often the resampled mean exceeds the observed mean.

    A real WRC requires the full set of strategies considered (to penalize
    multiple-testing bias). We approximate with a single-strategy bootstrap
    here as a reasonable Phase 1 baseline. Returns a p-value in [0, 1].
    """
    if not fold_alphas:
        return 1.0
    arr = np.asarray(fold_alphas, dtype=np.float64)
    observed_mean = float(arr.mean())
    if not np.isfinite(observed_mean):
        return 1.0

    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_resamples, dtype=np.float64)
    n = arr.size
    for i in range(n_resamples):
        signs = rng.choice([-1.0, 1.0], size=n)
        boot_means[i] = float((arr * signs).mean())

    # One-sided test: how often does randomized mean exceed observed?
    p = float((boot_means >= observed_mean).sum() / n_resamples)
    return p
