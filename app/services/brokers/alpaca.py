"""Alpaca broker adapter — implements BrokerAdapter for Alpaca Trading API.

Consolidates all Alpaca-specific code from executor.py, portfolio.py, and user.py
into a single adapter behind the BrokerAdapter interface.
"""

from decimal import Decimal

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ...core.broker import BrokerAdapter
from ...core.models import BrokerAccountInfo, BrokerPosition, OrderResult, OrderSide, OrderStatus

logger = structlog.get_logger(__name__)

# Alpaca API status → OrderStatus mapping
_ALPACA_STATUS_MAP: dict[str, str] = {
    "new": OrderStatus.SUBMITTED,
    "accepted": OrderStatus.SUBMITTED,
    "pending_new": OrderStatus.SUBMITTED,
    "accepted_for_bidding": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "expired": OrderStatus.CANCELLED,
    "rejected": OrderStatus.FAILED,
    "suspended": OrderStatus.PENDING,
    "pending_cancel": OrderStatus.SUBMITTED,
    "pending_replace": OrderStatus.SUBMITTED,
    "stopped": OrderStatus.CANCELLED,
}


class AlpacaAdapter(BrokerAdapter):
    """Alpaca Trading API adapter.

    Encapsulates all Alpaca HTTP calls. No dependency on app settings —
    credentials and base_url are injected by the factory.
    """

    def __init__(self, api_key: str, secret_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url

    @property
    def broker_type(self) -> str:
        return "alpaca"

    @staticmethod
    def _normalize_status(alpaca_status: str) -> OrderStatus:
        """Map Alpaca order status to OrderStatus enum value."""
        return OrderStatus(_ALPACA_STATUS_MAP.get(alpaca_status, OrderStatus.SUBMITTED))

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_account(self) -> BrokerAccountInfo:
        """Fetch account info from Alpaca GET /v2/account."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            resp = await client.get("/v2/account", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return BrokerAccountInfo(
                equity=Decimal(data["equity"]),
                cash=Decimal(data["cash"]),
                buying_power=Decimal(data.get("buying_power", "0")),
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_positions(self) -> list[BrokerPosition]:
        """Fetch all open positions from Alpaca GET /v2/positions."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            resp = await client.get("/v2/positions", headers=self._headers())
            resp.raise_for_status()
            positions = resp.json()
            return [
                BrokerPosition(
                    symbol=pos["symbol"],
                    quantity=Decimal(pos["qty"]),
                    avg_entry_price=Decimal(pos["avg_entry_price"]),
                    current_price=Decimal(pos["current_price"]),
                    market_value=Decimal(pos["market_value"]),
                )
                for pos in positions
            ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def submit_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        order_type: str,
        client_order_id: str,
    ) -> OrderResult:
        """Submit order to Alpaca POST /v2/orders with idempotency key."""
        payload: dict[str, str] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": "day",
            "client_order_id": client_order_id,
        }
        if order_type == "limit":
            payload["limit_price"] = str(price)

        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            resp = await client.post("/v2/orders", json=payload, headers=self._headers())

        if resp.status_code not in (200, 201):
            logger.error(
                "alpaca_order_failed", status=resp.status_code, body=resp.text[:200]
            )
            return OrderResult(
                order_id="",
                symbol=symbol,
                side=OrderSide(side),
                qty=qty,
                status=OrderStatus.FAILED,
                error_message=f"Alpaca error: {resp.status_code}",
            )

        data = resp.json()
        return OrderResult(
            order_id=data["id"],
            client_order_id=data.get("client_order_id", client_order_id),
            symbol=data["symbol"],
            side=OrderSide(data["side"]),
            qty=Decimal(data["qty"]),
            status=self._normalize_status(data["status"]),
            filled_qty=Decimal(data.get("filled_qty") or "0"),
            filled_avg_price=(
                Decimal(data["filled_avg_price"]) if data.get("filled_avg_price") else None
            ),
            submitted_at=data.get("submitted_at", ""),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_order_status(self, broker_order_id: str) -> OrderResult:
        """Poll order status from Alpaca GET /v2/orders/{id}."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            resp = await client.get(f"/v2/orders/{broker_order_id}", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return OrderResult(
                order_id=data["id"],
                client_order_id=data.get("client_order_id", ""),
                symbol=data["symbol"],
                side=OrderSide(data["side"]),
                qty=Decimal(data["qty"]),
                status=self._normalize_status(data["status"]),
                filled_qty=Decimal(data.get("filled_qty") or "0"),
                filled_avg_price=(
                    Decimal(data["filled_avg_price"]) if data.get("filled_avg_price") else None
                ),
                submitted_at=data.get("submitted_at", ""),
                filled_at=data.get("filled_at"),
            )

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel order via Alpaca DELETE /v2/orders/{id} (Saga compensation)."""
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
                resp = await client.delete(f"/v2/orders/{broker_order_id}", headers=self._headers())
            if resp.status_code in (200, 204):
                return True
            # 404 or 422 means order already filled/cancelled — still considered success
            if resp.status_code in (404, 422):
                logger.warning(
                    "order_already_resolved",
                    broker_order_id=broker_order_id,
                    status=resp.status_code,
                )
                return True
            logger.error(
                "alpaca_cancel_failed", broker_order_id=broker_order_id, status=resp.status_code
            )
            return False
        except httpx.HTTPError:
            logger.error(
                "alpaca_cancel_http_error", broker_order_id=broker_order_id, exc_info=True
            )
            return False

    async def test_connection(self) -> bool:
        """Test Alpaca API connectivity."""
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10) as client:
                resp = await client.get("/v2/account", headers=self._headers())
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
