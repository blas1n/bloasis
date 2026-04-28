"""Tests for AlpacaBrokerAdapter — paper/live key dispatch + mocked client.

The adapter holds an injected client object (via the `client=` kwarg) so we
don't need alpaca-py installed during tests. Each test fakes the surface the
adapter actually calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from bloasis.broker import (
    AlpacaBrokerAdapter,
    BrokerOrder,
)


class _FakeClient:
    """Minimal stand-in for alpaca-py's TradingClient."""

    def __init__(self) -> None:
        self.submitted: list[Any] = []
        self.cancel_calls: list[str] = []
        self.cancel_should_fail = False

    def get_account(self) -> Any:
        return SimpleNamespace(cash="50000", equity="60000", buying_power="50000", currency="USD")

    def get_all_positions(self) -> list[Any]:
        return [
            SimpleNamespace(
                symbol="AAPL",
                qty="10",
                avg_entry_price="150",
                current_price="155",
                market_value="1550",
            )
        ]

    def submit_order(self, order_data: Any) -> Any:
        self.submitted.append(order_data)
        return SimpleNamespace(
            id="alpaca-order-1",
            client_order_id=order_data.client_order_id,
            status="accepted",
            filled_qty=0,
            filled_avg_price=0,
            submitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    def cancel_order_by_id(self, order_id: str) -> None:
        if self.cancel_should_fail:
            raise RuntimeError("cancel failed")
        self.cancel_calls.append(order_id)


def test_constructor_rejects_invalid_mode() -> None:
    with pytest.raises(ValueError, match="must be 'paper' or 'live'"):
        AlpacaBrokerAdapter(mode="offline", client=_FakeClient())  # type: ignore[arg-type]


def test_paper_mode_loads_paper_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "paper-k")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "paper-s")
    monkeypatch.delenv("ALPACA_LIVE_API_KEY", raising=False)
    key, secret = AlpacaBrokerAdapter._load_keys("paper")
    assert (key, secret) == ("paper-k", "paper-s")


def test_live_mode_loads_live_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "live-k")
    monkeypatch.setenv("ALPACA_LIVE_API_SECRET", "live-s")
    key, secret = AlpacaBrokerAdapter._load_keys("live")
    assert (key, secret) == ("live-k", "live-s")


def test_missing_paper_keys_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_PAPER_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_API_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="ALPACA_PAPER_API_KEY"):
        AlpacaBrokerAdapter._load_keys("paper")


def test_missing_live_keys_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_LIVE_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_LIVE_API_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="ALPACA_LIVE_API_KEY"):
        AlpacaBrokerAdapter._load_keys("live")


def test_paper_keys_dont_cross_into_live(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only paper keys set — live mode must still raise.
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "paper-k")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "paper-s")
    monkeypatch.delenv("ALPACA_LIVE_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_LIVE_API_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="ALPACA_LIVE_API_KEY"):
        AlpacaBrokerAdapter._load_keys("live")


def test_mode_property_paper() -> None:
    adapter = AlpacaBrokerAdapter(mode="paper", client=_FakeClient())
    assert adapter.mode == "paper"


def test_mode_property_live() -> None:
    adapter = AlpacaBrokerAdapter(mode="live", client=_FakeClient())
    assert adapter.mode == "live"


def test_get_account_translates_strings_to_float() -> None:
    adapter = AlpacaBrokerAdapter(mode="paper", client=_FakeClient())
    acct = adapter.get_account()
    assert acct.cash == pytest.approx(50_000.0)
    assert acct.equity == pytest.approx(60_000.0)
    assert acct.buying_power == pytest.approx(50_000.0)
    assert acct.currency == "USD"


def test_get_positions_normalizes_strings_to_float() -> None:
    adapter = AlpacaBrokerAdapter(mode="paper", client=_FakeClient())
    positions = adapter.get_positions()
    assert len(positions) == 1
    p = positions[0]
    assert p.symbol == "AAPL"
    assert p.quantity == pytest.approx(10.0)
    assert p.avg_cost == pytest.approx(150.0)
    assert p.current_price == pytest.approx(155.0)
    assert p.market_value == pytest.approx(1_550.0)


def test_place_market_order_passes_client_order_id() -> None:
    fake = _FakeClient()
    adapter = AlpacaBrokerAdapter(mode="paper", client=fake)
    result = adapter.place_market_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=2.5, client_order_id="bloasis-x")
    )
    assert result.client_order_id == "bloasis-x"
    assert result.order_id == "alpaca-order-1"
    assert result.status == "accepted"
    # Also assert the request hit the client.
    assert len(fake.submitted) == 1
    sent = fake.submitted[0]
    assert sent.client_order_id == "bloasis-x"


def test_place_market_order_returns_rejected_on_exception() -> None:
    class FailingClient(_FakeClient):
        def submit_order(self, order_data: Any) -> Any:
            raise RuntimeError("api down")

    adapter = AlpacaBrokerAdapter(mode="paper", client=FailingClient())
    result = adapter.place_market_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=1, client_order_id="x")
    )
    assert result.status == "rejected"
    assert "api down" in result.reason


def test_cancel_order_success() -> None:
    fake = _FakeClient()
    adapter = AlpacaBrokerAdapter(mode="paper", client=fake)
    assert adapter.cancel_order("oid-1") is True
    assert fake.cancel_calls == ["oid-1"]


def test_cancel_order_failure_returns_false() -> None:
    fake = _FakeClient()
    fake.cancel_should_fail = True
    adapter = AlpacaBrokerAdapter(mode="paper", client=fake)
    assert adapter.cancel_order("oid-1") is False


def test_translate_status_partial_fill() -> None:
    from bloasis.broker.alpaca import _translate_status

    assert _translate_status("partially_filled") == "partially_filled"
    assert _translate_status("FILLED") == "filled"
    assert _translate_status("rejected") == "rejected"
    assert _translate_status("canceled") == "canceled"
    assert _translate_status("new") == "accepted"
