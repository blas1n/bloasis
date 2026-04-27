"""First-pass deterministic filter.

Operates on cached fundamentals to reduce a universe to "investable
candidates" before scoring. Pure function — same inputs always give same
output, no I/O, easy to test and parameterize.

Filters in order (cheapest cuts first):
    1. Sector exclusion
    2. Market cap minimum
    3. Dollar volume minimum
    4. P/E ceiling

Symbols missing any required field fail open by default — better to score
a slightly noisy candidate than to silently drop a large cap because
yfinance returned None for trailingPE. Callers wanting strict mode can
filter the input dict beforehand.
"""

from __future__ import annotations

from dataclasses import dataclass

from bloasis.config import PreFilterConfig
from bloasis.data.fetchers.protocols import FundamentalRow


@dataclass(frozen=True, slots=True)
class FilterResult:
    """Both kept and dropped symbols, with reasons for the drops."""

    kept: list[str]
    dropped: dict[str, str]


def apply_pre_filter(
    fundamentals: dict[str, FundamentalRow],
    cfg: PreFilterConfig,
) -> FilterResult:
    """Run the deterministic pre-filter against a fundamentals snapshot."""
    kept: list[str] = []
    dropped: dict[str, str] = {}
    excluded_sectors = {s.lower() for s in cfg.exclude_sectors}

    for symbol, row in fundamentals.items():
        reason = _evaluate(row, cfg, excluded_sectors)
        if reason is None:
            kept.append(symbol)
        else:
            dropped[symbol] = reason

    return FilterResult(kept=kept, dropped=dropped)


def _evaluate(
    row: FundamentalRow,
    cfg: PreFilterConfig,
    excluded_sectors: set[str],
) -> str | None:
    if row.sector and row.sector.lower() in excluded_sectors:
        return f"sector excluded: {row.sector}"

    if row.market_cap is not None and row.market_cap < cfg.min_market_cap:
        return f"market_cap {row.market_cap:.2e} < min {cfg.min_market_cap:.2e}"

    if (
        row.dollar_volume_avg is not None
        and row.dollar_volume_avg < cfg.min_dollar_volume
    ):
        return (
            f"dollar_volume {row.dollar_volume_avg:.2e} < "
            f"min {cfg.min_dollar_volume:.2e}"
        )

    # P/E: only filter if value is positive and present. Negative P/E means
    # the company is unprofitable; that's information, not a reason to
    # exclude — let the value composite handle it.
    if (
        row.pe_ratio_ttm is not None
        and row.pe_ratio_ttm > 0
        and row.pe_ratio_ttm > cfg.max_pe_ratio
    ):
        return f"PE {row.pe_ratio_ttm:.1f} > max {cfg.max_pe_ratio:.1f}"

    return None
