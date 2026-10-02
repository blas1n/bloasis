"""Issue #103 — backtests resolve historical constituent tickers too.

`data.ticker_renames` (#80) was applied only on the live trade path. A
backtest over a historical S&P 500 list asked yfinance for symbols such as
ANTM, which no longer trade, so the company dropped out of the panel even
though its price history lives on under the current symbol.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from bloasis.backtest.prefetch import prefetch_backtest_data
from bloasis.config import StrategyConfig
from tests.market_stub import market_fetcher

_ANTM = {
    "listed": "ANTM",
    "current": "ELV",
    "cik": "1156039",
    "evidence_accession": "0001156039-26-000005",
}


def _run(
    tmp_path: Path, symbols: list[str], sec: dict[str, str]
) -> tuple[object, list[str], MagicMock]:
    cfg = StrategyConfig.model_validate(
        {
            "scorer": {"type": "rule"},
            "risk": {"max_sector_concentration": 1.0},
            "data": {"cache_dir": str(tmp_path), "ticker_renames": [_ANTM]},
        }
    )
    idx = pd.to_datetime(["2026-09-28"])
    requested: list[str] = []

    def fetch(sym: str, _s: object, _e: object) -> pd.DataFrame:
        requested.append(sym)
        return pd.DataFrame({"close": [1.0]}, index=idx)

    ohlcv = MagicMock()
    ohlcv.fetch.side_effect = fetch
    edgar = MagicMock()
    edgar.cik.side_effect = lambda t: sec.get(t)
    with (
        patch("bloasis.backtest.prefetch.YfOhlcvFetcher", return_value=ohlcv),
        patch("bloasis.backtest.prefetch.YfMarketContextFetcher", return_value=market_fetcher(idx)),
        patch("bloasis.data.fetchers.sec_edgar.EdgarClient", return_value=edgar) as client_cls,
    ):
        data = prefetch_backtest_data(
            cfg, symbols, date(2016, 1, 1), date(2017, 12, 31), console=MagicMock()
        )
    return data, requested, client_cls


def test_backtest_fetches_a_renamed_constituent_under_its_current_ticker(tmp_path: Path) -> None:
    data, requested, _ = _run(tmp_path, ["ANTM", "AAPL"], {"ELV": "0001156039"})
    assert "ELV" in requested and "ANTM" not in requested
    assert set(data.bars) == {"ELV", "AAPL"}  # type: ignore[attr-defined]


def test_backtest_keeps_the_listed_ticker_when_sec_does_not_confirm(tmp_path: Path) -> None:
    # ELV mapping to another registrant means the rename is not followed (#80 rule).
    _data, requested, _ = _run(tmp_path, ["ANTM", "AAPL"], {"ELV": "0000000001"})
    assert "ANTM" in requested and "ELV" not in requested


def test_no_listed_symbol_means_no_sec_lookup(tmp_path: Path) -> None:
    _data, requested, client_cls = _run(tmp_path, ["AAPL", "MSFT"], {})
    assert requested[:2] == ["AAPL", "MSFT"]
    client_cls.assert_not_called()
