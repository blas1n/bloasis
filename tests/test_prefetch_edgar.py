"""Issue #70 — prefetch must ask EDGAR for 10-Ks back to the window start.

The fetcher can page past the submissions `recent` block, but only if the
caller says how far back it needs; this guards the call site, not the fetcher.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bloasis.backtest.prefetch import prefetch_backtest_data
from bloasis.config import StrategyConfig


def test_prefetch_passes_window_start_to_list_10k(tmp_path: Path) -> None:
    cfg = StrategyConfig.model_validate(
        {"scorer": {"type": "edgar_textdiff"}, "data": {"cache_dir": str(tmp_path)}}
    )
    bars = pd.DataFrame({"close": [1.0]}, index=pd.to_datetime(["2026-09-28"]))
    ohlcv = MagicMock()
    ohlcv.fetch.return_value = bars
    edgar = MagicMock()
    calls: list[dict[str, Any]] = []
    edgar.list_10k.side_effect = lambda sym, **kw: calls.append(kw) or []

    start, end = date(2025, 9, 29), date(2026, 9, 29)
    with (
        patch("bloasis.backtest.prefetch.YfOhlcvFetcher", return_value=ohlcv),
        patch("bloasis.backtest.prefetch.YfMarketContextFetcher"),
        patch("bloasis.data.fetchers.sec_edgar.EdgarClient", return_value=edgar),
    ):
        prefetch_backtest_data(cfg, ["JPM"], start, end, console=MagicMock())

    assert calls == [{"since": start - timedelta(days=5 * 365)}]


# ---------------------------------------------------------------------------
# Issue #72 — every EDGAR call site builds a client that refreshes its cache
# ---------------------------------------------------------------------------


def test_edgar_cache_max_age_defaults_to_24_hours() -> None:
    assert StrategyConfig().data.edgar_cache_max_age_hours == 24


@pytest.mark.parametrize("scorer_type", ["edgar_textdiff", "insider_cluster", "form_8k_event"])
def test_prefetch_passes_edgar_max_age_to_client(tmp_path: Path, scorer_type: str) -> None:
    cfg = StrategyConfig.model_validate(
        {
            "scorer": {"type": scorer_type},
            "data": {"cache_dir": str(tmp_path), "edgar_cache_max_age_hours": 7},
        }
    )
    bars = pd.DataFrame({"close": [1.0]}, index=pd.to_datetime(["2026-09-28"]))
    ohlcv = MagicMock()
    ohlcv.fetch.return_value = bars
    edgar = MagicMock()
    edgar.list_10k.return_value = []
    edgar.list_filings.return_value = []

    with (
        patch("bloasis.backtest.prefetch.YfOhlcvFetcher", return_value=ohlcv),
        patch("bloasis.backtest.prefetch.YfMarketContextFetcher"),
        patch("bloasis.data.fetchers.sec_edgar.EdgarClient", return_value=edgar) as client_cls,
    ):
        prefetch_backtest_data(cfg, ["JPM"], date(2025, 9, 29), date(2026, 9, 29))

    client_cls.assert_called_once_with(cache_dir=cfg.data.cache_dir, max_age_hours=7)


def test_live_candidates_see_a_10k_filed_after_the_cached_snapshot(tmp_path: Path) -> None:
    # The live paper path → prefetch → real EdgarClient: a snapshot cached
    # before the latest 10-K must be refreshed, and that 10-K must reach the
    # scorer's risk-factor history.
    from bloasis.cli import _build_live_candidates

    edgar_dir = tmp_path / "edgar"
    (edgar_dir / "filings").mkdir(parents=True)
    (edgar_dir / "tickers.json").write_text(
        json.dumps({"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple"}})
    )
    snap = edgar_dir / "filings" / "0000320193.json"

    def block(dates: list[str]) -> dict[str, list[str]]:
        return {
            "form": ["10-K"] * len(dates),
            "filingDate": dates,
            "reportDate": dates,
            "accessionNumber": [f"acc-{d}" for d in dates],
            "primaryDocument": [f"doc-{d}.htm" for d in dates],
        }

    snap.write_text(json.dumps({"filings": {"recent": block(["2025-06-02"])}}))
    old = time.time() - 48 * 3600
    os.utime(snap, (old, old))
    fresh = json.dumps({"filings": {"recent": block(["2026-06-01", "2025-06-02"])}})
    item_1a = "<h2>Item 1A. Risk Factors</h2><p>" + "Risk. " * 200 + "</p><h2>Item 1B.</h2>"

    def fake_get(url: str, *, accept: str = "text/html") -> bytes:
        if url.endswith("CIK0000320193.json"):
            return fresh.encode()
        if "/Archives/edgar/data/" in url:
            return item_1a.encode()
        raise AssertionError(url)

    cfg = StrategyConfig.model_validate(
        {"scorer": {"type": "edgar_textdiff"}, "data": {"cache_dir": str(tmp_path)}}
    )
    today = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
    bars = pd.DataFrame({"close": [1.0]}, index=[today])
    ohlcv = MagicMock()
    ohlcv.fetch.return_value = bars
    captured: list[Any] = []

    def fake_backtester(_cfg: StrategyConfig, data: Any) -> MagicMock:
        captured.append(data)
        bt = MagicMock()
        bt._build_candidates.return_value = ([], [])
        return bt

    with (
        patch("bloasis.backtest.prefetch.YfOhlcvFetcher", return_value=ohlcv),
        patch("bloasis.backtest.prefetch.YfMarketContextFetcher"),
        patch("bloasis.backtest.engine.Backtester", side_effect=fake_backtester),
        patch("bloasis.data.fetchers.sec_edgar._http_get", side_effect=fake_get),
        patch("bloasis.data.fetchers.sec_edgar.time.sleep"),
    ):
        _build_live_candidates(cfg, ["AAPL"], days=400)

    history = captured[0].risk_factors_history["AAPL"]
    assert [filed for filed, _period, _txt in history] == [date(2025, 6, 2), date(2026, 6, 1)]
