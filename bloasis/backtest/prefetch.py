"""Pre-fetch BacktestData for the backtester.

Extracted from ``bloasis/cli.py`` so the same pipeline can be reused by:

- single-config ``bloasis backtest`` (one scorer type)
- multi-config ``bloasis grid run`` (union of scorer types across combos)

Each fetcher kind is opt-in based on the ``scorer_types`` set; we never pay
yfinance / EDGAR cost for a feature the run won't use.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from typing import cast

import pandas as pd
from rich.console import Console

from bloasis.backtest.result import BacktestData
from bloasis.config import StrategyConfig
from bloasis.data.cache import ParquetCache
from bloasis.data.fetchers.yfinance_market import YfMarketContextFetcher
from bloasis.data.fetchers.yfinance_ohlcv import YfOhlcvFetcher

# Scorer types that need each fetcher kind. Centralised so prefetch and the
# grid runner agree on which data sources to warm.
_PEAD_SCORERS = ("pead", "pead_jt_intersect")
_LLM_SCORERS = ("fundamental_llm", "fundamental_llm_jt_intersect")
_EDGAR_TEXT_SCORERS = ("edgar_textdiff", "edgar_textdiff_jt_intersect")
_FORM4_SCORERS = ("insider_cluster",)
_FORM8K_SCORERS = ("form_8k_event",)


def prefetch_backtest_data(
    cfg: StrategyConfig,
    symbols: list[str],
    start_d: date,
    end_d: date,
    *,
    scorer_types: Iterable[str] | None = None,
    console: Console | None = None,
) -> BacktestData:
    """Build a ``BacktestData`` panel for the requested universe + window.

    ``scorer_types`` lets the caller widen the fetcher fan-out — the grid
    runner passes the union across every combination so cold-cache cost is
    paid once. Defaults to ``(cfg.scorer.type,)``.
    """
    if console is None:
        console = Console()
    if scorer_types is None:
        scorer_types = (cfg.scorer.type,)
    types = set(scorer_types)

    cache = ParquetCache(cfg.data.cache_dir, namespace="ohlcv")
    ohlcv = YfOhlcvFetcher(cache=cache, max_age_hours=cfg.data.ohlcv_cache_max_age_hours)
    market = YfMarketContextFetcher(ohlcv=ohlcv)

    warmup = timedelta(days=300)
    fetch_start = start_d - warmup
    bars: dict[str, pd.DataFrame] = {}
    skipped: list[tuple[str, str]] = []
    for sym in symbols:
        upper = sym.upper()
        try:
            bars[upper] = ohlcv.fetch(upper, fetch_start, end_d)
        except Exception as exc:  # noqa: BLE001 — yfinance/network errors vary
            skipped.append((upper, str(exc)))
            console.print(f"[yellow]skipping {upper}: {exc}[/yellow]")
    if skipped:
        console.print(
            f"[yellow]skipped {len(skipped)}/{len(symbols)} symbols "
            "(delisted, renamed, or unavailable in yfinance)[/yellow]"
        )
    if not bars:
        raise ValueError("every symbol failed to fetch — check connectivity / ticker validity")
    market_ctx = market.fetch(fetch_start, end_d)

    earnings_history: dict[str, pd.DataFrame] = {}
    if types & set(_PEAD_SCORERS):
        from bloasis.data.fetchers.yfinance_earnings import YfEarningsFetcher

        earnings_cache = ParquetCache(cfg.data.cache_dir, namespace="earnings")
        earnings_fetcher = YfEarningsFetcher(
            cache=earnings_cache,
            max_age_hours=cfg.data.fundamentals_cache_max_age_hours,
        )
        for sym in bars:
            try:
                earnings_history[sym] = earnings_fetcher.fetch(sym)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[yellow]skipping earnings for {sym}: {exc}[/yellow]")

    quarterly_financials: dict[str, pd.DataFrame] = {}
    if types & set(_LLM_SCORERS):
        from bloasis.data.fetchers.yfinance_financials import YfFinancialsFetcher

        fin_cache = ParquetCache(cfg.data.cache_dir, namespace="financials")
        fin_fetcher = YfFinancialsFetcher(
            cache=fin_cache,
            max_age_hours=cfg.data.fundamentals_cache_max_age_hours,
        )
        for sym in bars:
            try:
                quarterly_financials[sym] = fin_fetcher.fetch(sym)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[yellow]skipping financials for {sym}: {exc}[/yellow]")

    risk_factors_history: dict[str, list[tuple[date, date, str]]] = {}
    if types & set(_EDGAR_TEXT_SCORERS):
        from bloasis.data.fetchers.sec_edgar import EdgarClient

        edgar = EdgarClient(cache_dir=cfg.data.cache_dir)
        window_start = start_d - timedelta(days=5 * 365)
        for sym in bars:
            try:
                filings = edgar.list_10k(sym)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[yellow]skipping EDGAR list for {sym}: {exc}[/yellow]")
                continue
            history: list[tuple[date, date, str]] = []
            relevant = [f for f in filings if window_start <= f["filed"] <= end_d]
            for f in relevant[:12]:
                txt = edgar.risk_factors(sym, f)
                if txt is None:
                    continue
                history.append((f["filed"], f["period"], txt))
            history.sort(key=lambda t: t[0])
            if history:
                risk_factors_history[sym] = history

    insider_filings_dates: dict[str, list[date]] = {}
    form_8k_filings_dates: dict[str, list[date]] = {}
    if types & set(_FORM4_SCORERS):
        from bloasis.data.fetchers.sec_edgar import EdgarClient

        edgar = EdgarClient(cache_dir=cfg.data.cache_dir)
        for sym in bars:
            try:
                fl = edgar.list_filings(sym, form_type="4")
                insider_filings_dates[sym] = [
                    cast(date, f["filed"])
                    for f in fl
                    if start_d - timedelta(days=180) <= cast(date, f["filed"]) <= end_d
                ]
            except Exception as exc:  # noqa: BLE001
                console.print(f"[yellow]skipping Form 4 for {sym}: {exc}[/yellow]")
    if types & set(_FORM8K_SCORERS):
        from bloasis.data.fetchers.sec_edgar import EdgarClient

        edgar = EdgarClient(cache_dir=cfg.data.cache_dir)
        for sym in bars:
            try:
                fl = edgar.list_filings(sym, form_type="8-K")
                form_8k_filings_dates[sym] = [
                    cast(date, f["filed"])
                    for f in fl
                    if start_d - timedelta(days=90) <= cast(date, f["filed"]) <= end_d
                ]
            except Exception as exc:  # noqa: BLE001
                console.print(f"[yellow]skipping 8-K for {sym}: {exc}[/yellow]")

    return BacktestData(
        symbols=list(bars.keys()),
        bars=bars,
        vix_series=market_ctx.vix,
        spy_close_series=market_ctx.spy_close,
        earnings_history=earnings_history,
        quarterly_financials=quarterly_financials,
        risk_factors_history=risk_factors_history,
        insider_filings_dates=insider_filings_dates,
        form_8k_filings_dates=form_8k_filings_dates,
    )
