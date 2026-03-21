#!/usr/bin/env python3
"""Monitor trading execution — check if orders are being created and executed."""

import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

import structlog

from app.config import settings
from app.repositories.order_repository import OrderRepository
from app.repositories.trade_repository import TradeRepository
from app.repositories.user_repository import UserRepository
from shared.utils.postgres_client import PostgresClient

logger = structlog.get_logger(__name__)


async def check_trading_state(db: PostgresClient) -> dict[str, Any]:
    """Check current trading state across all tables."""
    user_repo = UserRepository(postgres=db)
    order_repo = OrderRepository(postgres=db)
    trade_repo = TradeRepository(postgres=db)

    # Get active users
    active_users = await user_repo.get_active_trading_users(limit=5)

    if not active_users:
        return {"error": "No active trading users found"}

    user_id = active_users[0]

    # Check orders
    orders = await order_repo.get_pending_orders()
    all_orders = len(orders)

    # Check trades
    trades = await trade_repo.get_trades(user_id, limit=10)
    all_trades = len(trades)

    return {
        "user_id": str(user_id),
        "trading_enabled": True,
        "orders_pending": all_orders,
        "trades_total": all_trades,
        "timestamp": datetime.now(UTC).isoformat(),
        "trades_sample": [
            {
                "symbol": t.symbol,
                "action": t.action,
                "qty": str(t.quantity),
                "price": str(t.price),
                "executed_at": t.executed_at.isoformat() if t.executed_at else None,
            }
            for t in trades[:3]
        ],
    }


async def main() -> int:
    """Main monitoring entry point."""
    db = PostgresClient(settings.database_url)

    try:
        state = await check_trading_state(db)

        if "error" in state:
            logger.error("monitoring_failed", error=state["error"])
            return 1

        logger.info(
            "trading_state",
            user_id=state["user_id"],
            orders_pending=state["orders_pending"],
            trades_total=state["trades_total"],
        )

        for trade in state.get("trades_sample", []):
            logger.info(
                "recent_trade",
                symbol=trade["symbol"],
                action=trade["action"],
                qty=trade["qty"],
                price=trade["price"],
            )

        if state.get("trades_total", 0) > 0:
            logger.info("trading_status", status="active")
            return 0
        else:
            logger.warning("trading_status", status="no_trades_yet")
            return 1

    finally:
        await db.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
