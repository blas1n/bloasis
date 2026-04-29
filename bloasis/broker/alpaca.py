"""Alpaca-py adapter — paper or live mode.

Mode is chosen at construction (no env-var sensing inside the adapter,
so tests don't accidentally talk to live with the wrong key). Endpoint
selection comes from the SDK's `paper=` flag; we just pass it through.

`alpaca-py` is an optional dependency (`pip install bloasis[broker]`).
The SDK import is lazy so the package can be imported in environments
without it (e.g., backtest-only deployment).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from bloasis.broker.protocols import (
    AccountInfo,
    BrokerOrder,
    BrokerPosition,
    OrderResult,
)

BrokerMode = Literal["paper", "live"]


class AlpacaBrokerAdapter:
    """Real Alpaca adapter. Constructor keeps paper and live separate.

    Reads keys from `ALPACA_PAPER_API_KEY`/`ALPACA_PAPER_API_SECRET`
    (paper) or `ALPACA_LIVE_API_KEY`/`ALPACA_LIVE_API_SECRET` (live).
    Missing live key in live mode raises immediately — failing fast at
    construction prevents accidentally falling back to paper credentials.
    """

    def __init__(self, mode: BrokerMode, *, client: Any = None) -> None:
        if mode not in ("paper", "live"):
            raise ValueError(f"mode must be 'paper' or 'live', got {mode!r}")
        self._mode: BrokerMode = mode
        if client is not None:
            # Test injection path.
            self._client = client
            return
        key, secret = self._load_keys(mode)
        self._client = self._build_client(key, secret, paper=(mode == "paper"))

    @property
    def mode(self) -> Literal["paper", "live", "offline"]:
        return cast(Literal["paper", "live", "offline"], self._mode)

    # ------------------------------------------------------------------

    @staticmethod
    def _load_keys(mode: BrokerMode) -> tuple[str, str]:
        prefix = "ALPACA_PAPER" if mode == "paper" else "ALPACA_LIVE"
        key = os.environ.get(f"{prefix}_API_KEY", "").strip()
        secret = os.environ.get(f"{prefix}_API_SECRET", "").strip()
        if not key or not secret:
            raise RuntimeError(
                f"{prefix}_API_KEY / {prefix}_API_SECRET not set; "
                f"cannot run AlpacaBrokerAdapter in {mode!r} mode"
            )
        return key, secret

    @staticmethod
    def _build_client(api_key: str, secret_key: str, *, paper: bool) -> Any:
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as exc:  # pragma: no cover — env-dependent
            raise ImportError(
                "alpaca-py is required for AlpacaBrokerAdapter. "
                "Install with: pip install 'bloasis[broker]'"
            ) from exc
        return TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)

    # ------------------------------------------------------------------

    def get_account(self) -> AccountInfo:
        acct = self._client.get_account()
        return AccountInfo(
            cash=float(acct.cash),
            equity=float(acct.equity),
            buying_power=float(acct.buying_power),
            currency=getattr(acct, "currency", "USD"),
        )

    def get_positions(self) -> list[BrokerPosition]:
        raw = self._client.get_all_positions()
        return [
            BrokerPosition(
                symbol=p.symbol,
                quantity=float(p.qty),
                avg_cost=float(p.avg_entry_price),
                current_price=float(p.current_price),
                market_value=float(p.market_value),
            )
            for p in raw
        ]

    def place_market_order(self, order: BrokerOrder) -> OrderResult:
        from alpaca.trading.enums import OrderSide as AlpacaSide
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        side_enum = AlpacaSide.BUY if order.side == "buy" else AlpacaSide.SELL
        request = MarketOrderRequest(
            symbol=order.symbol,
            qty=order.qty,
            side=side_enum,
            time_in_force=TimeInForce.DAY,
            client_order_id=order.client_order_id,
        )
        try:
            placed = self._client.submit_order(order_data=request)
        except Exception as exc:  # noqa: BLE001 — surface broker error verbatim
            return OrderResult(
                order_id=str(uuid.uuid4()),
                client_order_id=order.client_order_id,
                status="rejected",
                filled_qty=0.0,
                filled_avg_price=0.0,
                submitted_at=datetime.now(tz=UTC),
                reason=str(exc),
            )

        return OrderResult(
            order_id=str(placed.id),
            client_order_id=str(placed.client_order_id),
            status=_translate_status(str(placed.status)),
            filled_qty=float(getattr(placed, "filled_qty", 0) or 0),
            filled_avg_price=float(getattr(placed, "filled_avg_price", 0) or 0),
            submitted_at=getattr(placed, "submitted_at", datetime.now(tz=UTC)),
        )

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except Exception:  # noqa: BLE001
            return False


def _translate_status(
    alpaca_status: str,
) -> Literal["accepted", "filled", "partially_filled", "rejected", "canceled"]:
    """Map alpaca-py order status strings to our enum."""
    s = alpaca_status.lower()
    if "fill" in s and "partial" in s:
        return "partially_filled"
    if "fill" in s:
        return "filled"
    if "reject" in s:
        return "rejected"
    if "cancel" in s:
        return "canceled"
    return "accepted"
