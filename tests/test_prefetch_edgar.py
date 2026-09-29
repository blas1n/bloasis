"""Issue #70 — prefetch must ask EDGAR for 10-Ks back to the window start.

The fetcher can page past the submissions `recent` block, but only if the
caller says how far back it needs; this guards the call site, not the fetcher.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd

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
