#!/usr/bin/env python3
"""Monitor trading execution — check if orders are being created and executed."""

import asyncio
import sys
from datetime import UTC, datetime

from app.config import settings
from app.repositories.order_repository import OrderRepository
from app.repositories.trade_repository import TradeRepository
from app.repositories.user_repository import UserRepository
from shared.utils.postgres_client import PostgresClient


async def check_trading_state(db: PostgresClient) -> dict:
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


async def main():
    """Main monitoring loop."""
    db = PostgresClient(settings.database_url)

    try:
        state = await check_trading_state(db)
        print("\n=== Trading State ===")
        for key, value in state.items():
            if key != "trades_sample":
                print(f"{key}: {value}")

        if state.get("trades_sample"):
            print("\nRecent Trades:")
            for trade in state["trades_sample"]:
                print(f"  {trade['symbol']} {trade['action']} {trade['qty']} @ {trade['price']}")

        if state.get("trades_total", 0) > 0:
            print("\n✓ Trades detected! Trading is working.")
            return 0
        else:
            print("\n✗ No trades yet. Waiting for scheduler cycle...")
            return 1

    finally:
        await db.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
