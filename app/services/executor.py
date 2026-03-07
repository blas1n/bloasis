"""Executor Service — Order execution with risk checks.

Replaces: services/executor/ (1072 lines gRPC + Redpanda → ~100 lines direct)
Key simplifications:
- Risk check via core/risk_rules.py (no gRPC call to Risk Committee)
- Portfolio update via portfolio.record_trade() (no Redpanda event)
"""

import logging
import uuid
from decimal import Decimal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.utils.redis_client import RedisClient

from ..config import settings
from ..core.models import OrderRequest, OrderResult, RiskLimits
from ..core.risk_rules import evaluate_risk
from ..repositories.user_repository import UserRepository
from .market_data import MarketDataService
from .portfolio import PortfolioService

logger = logging.getLogger(__name__)


class ExecutorService:
    """Order execution with integrated risk checks."""

    def __init__(
        self,
        redis: RedisClient,
        portfolio_svc: PortfolioService,
        market_data_svc: MarketDataService,
        user_repo: UserRepository | None = None,
    ) -> None:
        self.redis = redis
        self.portfolio_svc = portfolio_svc
        self.market_data_svc = market_data_svc
        self.user_repo = user_repo

    async def execute_order(
        self,
        user_id: uuid.UUID,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal | None = None,
        order_type: str = "market",
        sector: str = "Unknown",
        ai_reason: str = "",
    ) -> OrderResult:
        """Execute an order with risk checks."""
        # Get current price if not provided
        if price is None or price == 0:
            bars = await self.market_data_svc.get_ohlcv(symbol, period="1d", interval="1d")
            if bars:
                price = Decimal(str(bars[-1]["close"]))
            else:
                return OrderResult(
                    order_id="",
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    status="rejected",
                    error_message="Cannot determine price",
                )

        # Risk check (pure function — no gRPC call)
        portfolio = await self.portfolio_svc.get_portfolio(user_id)
        vix = await self.market_data_svc.get_vix()

        order = OrderRequest(
            user_id=str(user_id),
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            sector=sector,
        )

        limits = RiskLimits(
            max_position_size=settings.max_position_size,
            max_single_order=settings.max_single_order,
            max_sector_concentration=settings.max_sector_concentration,
            vix_high_threshold=settings.vix_high_threshold,
            vix_extreme_threshold=settings.vix_extreme_threshold,
        )

        risk_result = evaluate_risk(order, portfolio, vix, limits)

        if risk_result.action == "reject":
            return OrderResult(
                order_id="",
                symbol=symbol,
                side=side,
                qty=qty,
                status="rejected",
                error_message=risk_result.reasoning,
            )

        # Adjust size if needed
        effective_qty = qty
        if risk_result.adjusted_size is not None:
            effective_qty = risk_result.adjusted_size

        # Submit to Alpaca
        result = await self._submit_to_alpaca(
            symbol=symbol,
            side=side,
            qty=effective_qty,
            price=price,
            order_type=order_type,
        )

        # Record trade in portfolio (direct call — no Redpanda)
        if result.status == "filled":
            fill_price = result.filled_avg_price or price
            try:
                await self.portfolio_svc.record_trade(
                    user_id=user_id,
                    order_id=result.order_id,
                    symbol=symbol,
                    side=side,
                    qty=effective_qty,
                    price=fill_price,
                    ai_reason=ai_reason,
                )
            except ValueError as e:
                logger.error("Trade recording failed: %s", e)
                return OrderResult(
                    order_id=result.order_id,
                    symbol=symbol,
                    side=side,
                    qty=effective_qty,
                    status="error",
                    error_message=str(e),
                )

        return result

    async def _submit_to_alpaca(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        order_type: str,
    ) -> OrderResult:
        """Submit order to Alpaca paper trading API.

        Falls back to mock mode if API keys not configured.
        """
        if not settings.alpaca_api_key or not settings.alpaca_secret_key:
            if not settings.mock_broker_enabled:
                return OrderResult(
                    order_id="",
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    status="rejected",
                    error_message="Alpaca API keys not configured",
                )
            return self._mock_order(symbol, side, qty, price)

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
        async def _call_alpaca() -> OrderResult:
            headers = {
                "APCA-API-KEY-ID": settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
            }
            payload: dict = {
                "symbol": symbol,
                "qty": str(qty),
                "side": side,
                "type": order_type,
                "time_in_force": "day",
            }
            if order_type == "limit":
                payload["limit_price"] = str(price)

            async with httpx.AsyncClient(base_url=settings.alpaca_base_url, timeout=30) as client:
                resp = await client.post("/v2/orders", json=payload, headers=headers)

            if resp.status_code not in (200, 201):
                logger.error("Alpaca order failed", extra={"status": resp.status_code})
                logger.debug("Alpaca error detail", extra={"body": resp.text[:200]})
                return OrderResult(
                    order_id="",
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    status="rejected",
                    error_message=f"Alpaca error: {resp.status_code}",
                )

            data = resp.json()
            return OrderResult(
                order_id=data["id"],
                client_order_id=data.get("client_order_id", ""),
                symbol=data["symbol"],
                side=data["side"],
                qty=Decimal(data["qty"]),
                status=data["status"],
                filled_qty=Decimal(data.get("filled_qty") or "0"),
                filled_avg_price=Decimal(data["filled_avg_price"])
                if data.get("filled_avg_price")
                else None,
                submitted_at=data.get("submitted_at", ""),
            )

        return await _call_alpaca()

    @staticmethod
    def _mock_order(symbol: str, side: str, qty: Decimal, price: Decimal) -> OrderResult:
        """Mock order for development when Alpaca keys are not configured.

        Note: The trade will be recorded in the portfolio DB by execute_order(),
        allowing full end-to-end testing without a live broker connection.
        """
        order_id = str(uuid.uuid4())
        logger.info(
            "Mock order submitted (MOCK_BROKER_ENABLED=true) — trade will be recorded in DB",
            extra={"symbol": symbol, "side": side, "qty": str(qty)},
        )

        return OrderResult(
            order_id=order_id,
            client_order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            status="filled",
            filled_qty=qty,
            filled_avg_price=price,
        )

    async def get_trading_status(self, user_id: uuid.UUID) -> dict:
        """Get automated trading status for a user.

        Checks Redis first (fast path), falls back to DB for durability.
        """
        status = await self.redis.get(f"trading:{user_id}:status")
        if status is not None:
            return {
                "tradingEnabled": status == "active",
                "status": status,
                "lastChanged": "",
            }

        # Fallback to DB when Redis has no data (e.g., after restart)
        if self.user_repo:
            enabled = await self.user_repo.get_trading_enabled(user_id)
            db_status = "active" if enabled else "inactive"
            await self.redis.setex(f"trading:{user_id}:status", 86400, db_status)
            return {
                "tradingEnabled": enabled,
                "status": db_status,
                "lastChanged": "",
            }

        return {"tradingEnabled": False, "status": "inactive", "lastChanged": ""}

    async def start_trading(self, user_id: uuid.UUID) -> dict:
        """Start automated trading for a user."""
        await self.redis.setex(f"trading:{user_id}:status", 86400, "active")
        if self.user_repo:
            await self.user_repo.update_trading_enabled(user_id, True)
        return {"tradingEnabled": True, "status": "active"}

    async def stop_trading(self, user_id: uuid.UUID, mode: str = "soft") -> dict:
        """Stop automated trading for a user."""
        status = f"{mode}_stopped"
        await self.redis.setex(f"trading:{user_id}:status", 86400, status)
        if self.user_repo:
            await self.user_repo.update_trading_enabled(user_id, False)
        return {"tradingEnabled": False, "status": status}
