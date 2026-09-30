"""Class-share tickers at the yfinance boundary (issue #78).

Index constituents and Alpaca spell class shares with a dot (``BRK.B``);
Yahoo spells them with a dash (``BRK-B``) and returns nothing for the dotted
form. Only the request sent to yfinance is translated — every frame, cache
key, candidate and order keeps the canonical dotted symbol.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bloasis.broker import AlpacaBrokerAdapter, BrokerOrder
from bloasis.config import StrategyConfig
from bloasis.data.fetchers.yfinance_earnings import YfEarningsFetcher
from bloasis.data.fetchers.yfinance_financials import YfFinancialsFetcher
from bloasis.data.fetchers.yfinance_ohlcv import YfOhlcvFetcher
from bloasis.data.fetchers.yfinance_screener import YfFundamentalsFetcher


def _bars(end: pd.Timestamp, n: int = 5) -> pd.DataFrame:
    idx = pd.date_range(end=end, periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": [10.0] * n,
            "High": [11.0] * n,
            "Low": [9.0] * n,
            "Close": [10.5] * n,
            "Volume": [1000.0] * n,
        },
        index=idx,
    )


def _yahoo_like_module(end: pd.Timestamp) -> tuple[MagicMock, list[str]]:
    """A fake `yfinance` that behaves like Yahoo: dotted class shares are empty."""
    requested: list[str] = []

    def make_ticker(sym: str) -> MagicMock:
        requested.append(sym)
        t = MagicMock()
        t.history.return_value = pd.DataFrame() if "." in sym else _bars(end)
        return t

    module = MagicMock()
    module.Ticker.side_effect = make_ticker
    return module, requested


@pytest.mark.parametrize(
    ("canonical", "yahoo"),
    [("BRK.B", "BRK-B"), ("BF.B", "BF-B"), ("AAPL", "AAPL"), ("^VIX", "^VIX")],
)
def test_yahoo_symbol_dashes_class_shares_only(canonical: str, yahoo: str) -> None:
    from bloasis.data.fetchers._yfinance import yahoo_symbol

    assert yahoo_symbol(canonical) == yahoo


@pytest.mark.parametrize(("canonical", "yahoo"), [("BRK.B", "BRK-B"), ("BF.B", "BF-B")])
def test_ohlcv_requests_dashed_symbol_and_caches_under_dotted(
    tmp_path: Path, canonical: str, yahoo: str
) -> None:
    from bloasis.data.cache import ParquetCache

    module, requested = _yahoo_like_module(pd.Timestamp("2024-01-05"))
    cache = ParquetCache(tmp_path, namespace="ohlcv")
    with patch("bloasis.data.fetchers._yfinance.import_yfinance", return_value=module):
        df = YfOhlcvFetcher(cache=cache).fetch(canonical, date(2024, 1, 1), date(2024, 1, 5))

    assert requested == [yahoo]
    assert len(df) == 5
    names = [p.name for p in (tmp_path / "parquet" / "ohlcv").glob("*.parquet")]
    assert names and all(n.startswith(f"{canonical}_") for n in names)


def test_earnings_and_financials_request_dashed_symbol() -> None:
    module, requested = _yahoo_like_module(pd.Timestamp("2024-01-05"))
    with patch("bloasis.data.fetchers._yfinance.import_yfinance", return_value=module):
        YfEarningsFetcher(cache=None).fetch("BRK.B")
        YfFinancialsFetcher(cache=None).fetch("BF.B")
    assert requested == ["BRK-B", "BF-B"]


def test_fundamentals_single_row_keeps_dotted_symbol() -> None:
    module = MagicMock()
    module.Ticker.return_value = MagicMock(info={"symbol": "BRK-B", "marketCap": 1.0e12})
    with patch("bloasis.data.fetchers._yfinance.import_yfinance", return_value=module):
        row = YfFundamentalsFetcher().fetch_single("BRK.B")
    module.Ticker.assert_called_once_with("BRK-B")
    assert row is not None
    assert row.symbol == "BRK.B"


def test_live_candidates_get_bars_for_class_shares_keyed_dotted(tmp_path: Path) -> None:
    # The paper-rotate call site: SP500 hands `_build_live_candidates` the
    # dotted symbols; yfinance must be asked for the dashed ones and the
    # panel the scorer sees must be keyed by the dotted ones.
    from bloasis.cli import _build_live_candidates

    today = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
    module, requested = _yahoo_like_module(today)
    cfg = StrategyConfig.model_validate({"data": {"cache_dir": str(tmp_path)}})
    captured: list[Any] = []

    def fake_backtester(_cfg: StrategyConfig, data: Any) -> MagicMock:
        captured.append(data)
        bt = MagicMock()
        bt._build_candidates.return_value = ([], [])
        return bt

    with (
        patch("bloasis.data.fetchers._yfinance.import_yfinance", return_value=module),
        patch("bloasis.backtest.engine.Backtester", side_effect=fake_backtester),
    ):
        _build_live_candidates(cfg, ["brk.b", "BF.B", "AAPL"], days=30)

    assert {"BRK-B", "BF-B", "AAPL"} <= set(requested)
    assert not any("." in s for s in requested)
    assert set(captured[0].bars) == {"BRK.B", "BF.B", "AAPL"}


def test_alpaca_order_for_class_share_keeps_the_dot() -> None:
    client = MagicMock()
    client.submit_order.return_value = MagicMock(
        id="o1", client_order_id="c1", status="accepted", filled_qty=0, filled_avg_price=0
    )
    adapter = AlpacaBrokerAdapter(mode="paper", client=client)
    adapter.place_market_order(
        BrokerOrder(symbol="BRK.B", side="buy", qty=1.0, client_order_id="c1")
    )
    sent = client.submit_order.call_args.kwargs["order_data"]
    assert sent.symbol == "BRK.B"
