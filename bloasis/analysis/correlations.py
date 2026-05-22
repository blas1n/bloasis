"""Return-correlation + clustering — pure compute, no I/O (PR53).

The CLI feeds close-price series pulled from the OHLCV cache; everything
here operates on in-memory pandas objects so it stays testable and
side-effect free (CLAUDE.md architecture rule #2).

Two uses:
  - portfolio concentration: flag holdings that sit in the same
    correlation cluster (e.g. AMZN + QCOM both AI/tech).
  - cluster substrate for the economic-link event study (PR54).
"""

from __future__ import annotations

import pandas as pd


def returns_from_closes(closes: dict[str, pd.Series]) -> pd.DataFrame:
    """Align close-price series on common dates → daily pct-return panel.

    Inner-joins on the date index (so misaligned histories contribute only
    their overlap), then `pct_change` and drops the first NaN row.
    """
    if not closes:
        return pd.DataFrame()
    frame = pd.DataFrame(closes)
    frame = frame.dropna(how="any")  # inner-join: keep rows present for all
    returns = frame.pct_change().dropna(how="any")
    return returns


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Pairwise Pearson correlation of the return columns."""
    return returns.corr()


def cluster_symbols(corr: pd.DataFrame, threshold: float) -> list[list[str]]:
    """Connected-components clustering: symbols share a cluster when their
    absolute correlation is >= `threshold` (directly or transitively).

    Union-find over the threshold graph — dependency-free and deterministic.
    Returned clusters are sorted (largest first, then alphabetically) for
    stable output.
    """
    symbols = list(corr.columns)
    parent = {s: s for s in symbols}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i, a in enumerate(symbols):
        for b in symbols[i + 1 :]:
            val = corr.loc[a, b]
            if pd.notna(val) and abs(float(val)) >= threshold:  # type: ignore[arg-type]
                union(a, b)

    groups: dict[str, list[str]] = {}
    for s in symbols:
        groups.setdefault(find(s), []).append(s)

    clusters = [sorted(g) for g in groups.values()]
    clusters.sort(key=lambda c: (-len(c), c[0]))
    return clusters


def top_pairs(corr: pd.DataFrame, n: int) -> list[tuple[str, str, float]]:
    """Top-`n` symbol pairs by correlation (descending), excluding self-pairs."""
    symbols = list(corr.columns)
    pairs: list[tuple[str, str, float]] = []
    for i, a in enumerate(symbols):
        for b in symbols[i + 1 :]:
            val = corr.loc[a, b]
            if pd.notna(val):
                pairs.append((a, b, float(val)))  # type: ignore[arg-type]
    pairs.sort(key=lambda t: t[2], reverse=True)
    return pairs[:n]


def concentration_report(
    corr: pd.DataFrame, holdings: list[str], threshold: float
) -> list[list[str]]:
    """Cluster the held symbols and return the per-cluster holding groups.

    Only considers symbols in `holdings` that are present in `corr`. A
    cluster with >1 holding is a concentration flag — the strategy is
    exposed to one correlated bloc through multiple names.
    """
    present = [h for h in holdings if h in corr.columns]
    if not present:
        return []
    sub = corr.loc[present, present]
    return cluster_symbols(sub, threshold)
