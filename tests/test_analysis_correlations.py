"""Tests for bloasis.analysis.correlations (PR53).

Pure-compute correlation + clustering on a returns panel. No I/O — the
CLI feeds it close-price series pulled from the OHLCV cache. Used to
spot portfolio concentration (e.g. holding AMZN + QCOM = same AI/tech
cluster) and as the cluster substrate for the economic-link event study.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bloasis.analysis.correlations import (
    cluster_symbols,
    concentration_report,
    correlation_matrix,
    returns_from_closes,
    top_pairs,
)


def _close_series(values: list[float], start: str = "2026-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="B", tz="UTC")
    return pd.Series(values, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# returns_from_closes — align + pct-change
# ---------------------------------------------------------------------------


def test_returns_from_closes_aligns_and_diffs() -> None:
    closes = {
        "AAA": _close_series([100, 110, 121]),  # +10%, +10%
        "BBB": _close_series([50, 55, 60.5]),  # +10%, +10%
    }
    rets = returns_from_closes(closes)
    assert list(rets.columns) == ["AAA", "BBB"]
    # 2 return rows (first row dropped by pct_change)
    assert len(rets) == 2
    assert rets["AAA"].iloc[0] == pytest.approx(0.10)


def test_returns_from_closes_inner_joins_misaligned_dates() -> None:
    a = pd.Series([100, 110], index=pd.date_range("2026-01-01", periods=2, freq="B", tz="UTC"))
    b = pd.Series([50, 55, 60], index=pd.date_range("2026-01-01", periods=3, freq="B", tz="UTC"))
    rets = returns_from_closes({"A": a, "B": b})
    # Only overlapping dates contribute; B's extra day is dropped on inner join.
    assert len(rets) == 1


# ---------------------------------------------------------------------------
# correlation_matrix
# ---------------------------------------------------------------------------


def test_correlation_matrix_perfectly_correlated() -> None:
    # AAA and BBB share the SAME (varying) return path → corr 1.0.
    # Returns must vary — constant returns have zero variance → NaN corr.
    closes = {
        "AAA": _close_series([100, 110, 104.5, 112.86]),  # +10%, -5%, +8%
        "BBB": _close_series([10, 11, 10.45, 11.286]),  # same return path, scaled
    }
    rets = returns_from_closes(closes)
    corr = correlation_matrix(rets)
    assert corr.loc["AAA", "BBB"] == pytest.approx(1.0, abs=1e-9)
    assert corr.loc["AAA", "AAA"] == pytest.approx(1.0)


def test_correlation_matrix_anticorrelated() -> None:
    # DN's returns are the exact negation of UP's → corr -1.0.
    closes = {
        "UP": _close_series([100, 110, 104.5, 112.86]),  # +10%, -5%, +8%
        "DN": _close_series([100, 90, 94.5, 86.94]),  # -10%, +5%, -8%
    }
    rets = returns_from_closes(closes)
    corr = correlation_matrix(rets)
    assert corr.loc["UP", "DN"] < -0.9


# ---------------------------------------------------------------------------
# cluster_symbols — connected components above threshold
# ---------------------------------------------------------------------------


def test_cluster_symbols_groups_correlated() -> None:
    # AAA~BBB highly correlated; CCC independent.
    rng = np.random.default_rng(42)
    base = rng.normal(0, 0.01, 100)
    idx = pd.date_range("2026-01-01", periods=100, freq="B", tz="UTC")
    rets = pd.DataFrame(
        {
            "AAA": base,
            "BBB": base + rng.normal(0, 0.0005, 100),  # near-identical to AAA
            "CCC": rng.normal(0, 0.01, 100),  # independent
        },
        index=idx,
    )
    corr = correlation_matrix(rets)
    clusters = cluster_symbols(corr, threshold=0.8)
    # AAA + BBB in one cluster, CCC alone.
    cluster_of = {s: i for i, c in enumerate(clusters) for s in c}
    assert cluster_of["AAA"] == cluster_of["BBB"]
    assert cluster_of["CCC"] != cluster_of["AAA"]


def test_cluster_symbols_all_independent_each_alone() -> None:
    rng = np.random.default_rng(1)
    idx = pd.date_range("2026-01-01", periods=100, freq="B", tz="UTC")
    rets = pd.DataFrame({s: rng.normal(0, 0.01, 100) for s in ["A", "B", "C"]}, index=idx)
    clusters = cluster_symbols(corr=correlation_matrix(rets), threshold=0.8)
    assert len(clusters) == 3
    assert all(len(c) == 1 for c in clusters)


# ---------------------------------------------------------------------------
# top_pairs
# ---------------------------------------------------------------------------


def test_top_pairs_returns_most_correlated_first() -> None:
    closes = {
        "AAA": _close_series([100, 110, 104.5, 112.86]),  # +10%, -5%, +8%
        "BBB": _close_series([10, 11, 10.45, 11.286]),  # = AAA return path
        "CCC": _close_series([100, 99, 100.5, 99.2]),  # different path
    }
    rets = returns_from_closes(closes)
    corr = correlation_matrix(rets)
    pairs = top_pairs(corr, n=1)
    assert len(pairs) == 1
    s1, s2, c = pairs[0]
    assert {s1, s2} == {"AAA", "BBB"}
    assert c == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# concentration_report — current holdings vs clusters
# ---------------------------------------------------------------------------


def test_concentration_report_flags_same_cluster_holdings() -> None:
    rng = np.random.default_rng(7)
    base = rng.normal(0, 0.01, 100)
    idx = pd.date_range("2026-01-01", periods=100, freq="B", tz="UTC")
    rets = pd.DataFrame(
        {
            "AMZN": base,
            "QCOM": base + rng.normal(0, 0.0005, 100),  # same cluster as AMZN
            "KO": rng.normal(0, 0.01, 100),  # independent
        },
        index=idx,
    )
    corr = correlation_matrix(rets)
    report = concentration_report(corr, holdings=["AMZN", "QCOM", "KO"], threshold=0.8)
    # AMZN + QCOM flagged as a multi-holding cluster; KO alone.
    multi = [c for c in report if len(c) > 1]
    assert len(multi) == 1
    assert set(multi[0]) == {"AMZN", "QCOM"}
