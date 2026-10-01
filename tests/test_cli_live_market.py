"""Live trade path feeds real VIX + SPY returns to the runner (#91).

Until #91 the `trade` commands called `execute_strategy_step` with
`vix=0.0` and an empty SPY return series, so the VIX risk gates and the
regime overlay could never act in paper/live while the backtest applied
both. These tests sit at the CLI call sites, not on `RiskEvaluator` /
`compute_regime_scale`, because the defect was the wiring.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from bloasis.config import StrategyConfig


def _buy_signal(symbol: str) -> MagicMock:
    sig = MagicMock()
    sig.action = "BUY"
    sig.symbol = symbol
    sig.sector = None
    sig.entry_price = 200.0
    sig.target_size_pct = 0.02
    sig.reason = f"buy-{symbol}"
    return sig


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    from bloasis.broker import BrokerAdapter

    BrokerAdapter.register(MagicMock)
    b = MagicMock()
    b.mode = "paper"
    b.get_account.return_value = MagicMock(cash=100_000.0, equity=100_000.0)
    b.get_positions.return_value = []
    b.place_market_order.return_value = MagicMock(
        status="filled", filled_qty=10.0, filled_avg_price=200.0, reason=None
    )

    sig_gen = MagicMock()
    sig_gen.return_value.generate.return_value = [_buy_signal("AAPL"), _buy_signal("MSFT")]
    monkeypatch.setattr("bloasis.signal.SignalGenerator", sig_gen)
    return b


def _calm_returns() -> pd.Series:
    idx = pd.bdate_range("2024-01-01", periods=300, tz="UTC")
    return pd.Series(0.0005, index=idx)


def _stormy_returns() -> pd.Series:
    idx = pd.bdate_range("2024-01-01", periods=600, tz="UTC")
    rng = np.random.default_rng(0)
    return pd.Series(rng.normal(-0.002, 0.05, len(idx)), index=idx)


def test_live_step_rejects_buys_when_vix_is_extreme(broker: MagicMock) -> None:
    from bloasis.cli import LiveMarketInputs, _execute_against_broker

    cfg = StrategyConfig()  # vix_extreme 40
    market = LiveMarketInputs(vix=45.0, spy_returns=_calm_returns())

    _execute_against_broker(cfg, [], broker, market=market, label="paper")

    broker.place_market_order.assert_not_called()


def test_live_step_buys_when_vix_is_calm(broker: MagicMock) -> None:
    # Control for the test above: same stubs, calm VIX -> both BUYs go out.
    from bloasis.cli import LiveMarketInputs, _execute_against_broker

    cfg = StrategyConfig()
    market = LiveMarketInputs(vix=15.0, spy_returns=_calm_returns())

    _execute_against_broker(cfg, [], broker, market=market, label="paper")

    assert broker.place_market_order.call_count == 2


def _first_buy_qty(broker: MagicMock) -> float:
    return float(broker.place_market_order.call_args_list[0].args[0].qty)


def test_live_step_regime_overlay_shrinks_size_in_a_stormy_market(broker: MagicMock) -> None:
    from bloasis.cli import LiveMarketInputs, _execute_against_broker

    market = LiveMarketInputs(vix=15.0, spy_returns=_stormy_returns())

    off = StrategyConfig()
    _execute_against_broker(off, [], broker, market=market, label="paper")
    qty_off = _first_buy_qty(broker)

    broker.place_market_order.reset_mock()
    on = StrategyConfig.model_validate(
        {"regime_overlay": {"enabled": True, "scale_clip": [0.0, 1.0]}}
    )
    _execute_against_broker(on, [], broker, market=market, label="paper")
    qty_on = _first_buy_qty(broker)

    assert qty_on < 0.5 * qty_off


def _fake_panel(bar_dates: list[str], market_dates: list[str]) -> SimpleNamespace:
    bar_idx = pd.DatetimeIndex(bar_dates, tz="UTC")
    mkt_idx = pd.DatetimeIndex(market_dates, tz="UTC")
    return SimpleNamespace(
        bars={"AAPL": pd.DataFrame({"close": 1.0}, index=bar_idx)},
        vix_series=pd.Series(np.arange(len(mkt_idx), dtype=float) + 20.0, index=mkt_idx),
        spy_close_series=pd.Series(np.linspace(400.0, 410.0, len(mkt_idx)), index=mkt_idx),
    )


def test_build_live_candidates_returns_market_inputs_as_of_the_latest_bar() -> None:
    from bloasis.cli import _build_live_candidates

    # The market series run one day past the latest stock bar; the extra
    # day must not leak in (same as-of rule the backtester applies).
    data = _fake_panel(
        ["2026-09-28", "2026-09-29", "2026-09-30"],
        ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"],
    )
    bt = MagicMock()
    bt._build_candidates.return_value = ([], [])

    with (
        patch("bloasis.backtest.prefetch.prefetch_backtest_data", return_value=data),
        patch("bloasis.backtest.engine.Backtester", return_value=bt),
    ):
        _cands, _closes, market = _build_live_candidates(StrategyConfig(), ["AAPL", "MSFT"], 365)

    assert market.vix == 22.0  # 2026-09-30, not 23.0 from 2026-10-01
    expected = data.spy_close_series.pct_change().dropna().loc[:"2026-09-30"]
    pd.testing.assert_series_equal(market.spy_returns, expected)


def test_build_live_candidates_refuses_to_trade_without_a_vix_close() -> None:
    from bloasis.cli import _build_live_candidates

    data = _fake_panel(["2026-09-30"], ["2026-10-01"])  # no VIX on/before the bar
    bt = MagicMock()
    bt._build_candidates.return_value = ([], [])

    with (
        patch("bloasis.backtest.prefetch.prefetch_backtest_data", return_value=data),
        patch("bloasis.backtest.engine.Backtester", return_value=bt),
        pytest.raises(ValueError, match="VIX"),
    ):
        _build_live_candidates(StrategyConfig(), ["AAPL", "MSFT"], 365)
