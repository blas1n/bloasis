"""Tests for `bloasis.data.pre_filter`."""

from __future__ import annotations

from datetime import UTC, datetime

from bloasis.config import PreFilterConfig
from bloasis.data.fetchers.protocols import FundamentalRow
from bloasis.data.pre_filter import apply_pre_filter

NOW = datetime.now(tz=UTC)


def _row(
    symbol: str,
    *,
    market_cap: float | None = 5e9,
    pe: float | None = 18.0,
    dollar_vol: float | None = 1e8,
    sector: str | None = "Technology",
    profit_margin: float | None = 0.15,
) -> FundamentalRow:
    return FundamentalRow(
        symbol=symbol,
        fetched_at=NOW,
        sector=sector,
        market_cap=market_cap,
        pe_ratio_ttm=pe,
        dollar_volume_avg=dollar_vol,
        profit_margin=profit_margin,
    )


def test_keeps_passing_symbols() -> None:
    cfg = PreFilterConfig(
        min_market_cap=1e9,
        max_pe_ratio=25.0,
        min_dollar_volume=1e7,
        exclude_sectors=[],
    )
    fundamentals = {"AAPL": _row("AAPL"), "MSFT": _row("MSFT")}
    result = apply_pre_filter(fundamentals, cfg)
    assert sorted(result.kept) == ["AAPL", "MSFT"]
    assert result.dropped == {}


def test_drops_below_min_market_cap() -> None:
    cfg = PreFilterConfig(min_market_cap=1e10)
    fundamentals = {"SMALL": _row("SMALL", market_cap=1e9)}
    result = apply_pre_filter(fundamentals, cfg)
    assert result.kept == []
    assert "market_cap" in result.dropped["SMALL"]


def test_drops_below_min_dollar_volume() -> None:
    cfg = PreFilterConfig(min_dollar_volume=1e10)
    fundamentals = {"ILLIQ": _row("ILLIQ", dollar_vol=1e6)}
    result = apply_pre_filter(fundamentals, cfg)
    assert result.kept == []
    assert "dollar_volume" in result.dropped["ILLIQ"]


def test_drops_above_max_pe() -> None:
    cfg = PreFilterConfig(max_pe_ratio=20.0)
    fundamentals = {"EXP": _row("EXP", pe=50.0)}
    result = apply_pre_filter(fundamentals, cfg)
    assert result.kept == []
    assert "PE" in result.dropped["EXP"]


def test_keeps_negative_pe() -> None:
    cfg = PreFilterConfig(max_pe_ratio=20.0)
    fundamentals = {"LOSS": _row("LOSS", pe=-5.0)}
    result = apply_pre_filter(fundamentals, cfg)
    assert "LOSS" in result.kept


def test_excludes_specified_sectors_case_insensitive() -> None:
    cfg = PreFilterConfig(exclude_sectors=["Energy", "REAL ESTATE"])
    fundamentals = {
        "TECH": _row("TECH", sector="Technology"),
        "OIL": _row("OIL", sector="energy"),
        "RE": _row("RE", sector="Real Estate"),
    }
    result = apply_pre_filter(fundamentals, cfg)
    assert result.kept == ["TECH"]
    assert "sector" in result.dropped["OIL"]
    assert "sector" in result.dropped["RE"]


def test_missing_fields_fail_open() -> None:
    cfg = PreFilterConfig(min_market_cap=1e9, min_dollar_volume=1e7)
    fundamentals = {"MISSING": _row("MISSING", market_cap=None, dollar_vol=None, pe=None)}
    result = apply_pre_filter(fundamentals, cfg)
    # All filters skip when their field is None — symbol passes through.
    assert result.kept == ["MISSING"]


def test_multiple_failures_record_first() -> None:
    cfg = PreFilterConfig(min_market_cap=1e10, max_pe_ratio=10.0)
    fundamentals = {"BAD": _row("BAD", market_cap=1e8, pe=50.0)}
    result = apply_pre_filter(fundamentals, cfg)
    # First failing rule wins (sector→cap→volume→pe order).
    assert "market_cap" in result.dropped["BAD"]
