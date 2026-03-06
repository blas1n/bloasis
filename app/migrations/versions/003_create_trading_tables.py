"""Create trading schema tables for BLOASIS Phase 1.

This migration creates the core tables for trading operations:
- users: User profiles with risk tolerance settings
- portfolios: User portfolio summaries with total value and returns
- positions: Individual stock positions per user
- orders: Trading orders (BUY/SELL with MARKET/LIMIT types)
- executions: Order execution records
- trades: Completed trade history

Why UUID Primary Keys:
- Distributed uniqueness without coordination
- No sequential ID exposure (security)
- gen_random_uuid() is fast and collision-resistant

Why NUMERIC for Financial Values:
- Float has precision issues (0.1 + 0.2 != 0.3)
- NUMERIC(15, 2) allows values up to 9,999,999,999,999.99
- Sufficient for any portfolio or trade value

Revision ID: 003
Revises: 002
Create Date: 2026-01-29

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create trading schema tables.

    Tables created:
    1. trading.users - User profiles with risk settings
    2. trading.portfolios - Portfolio summaries (one per user)
    3. trading.positions - Individual stock positions
    4. trading.orders - Trading orders
    5. trading.executions - Order execution records
    6. trading.trades - Completed trade history

    Foreign key constraints:
    - All user_id references use ON DELETE CASCADE
    - executions.order_id uses ON DELETE CASCADE
    - This ensures clean data removal when users/orders are deleted
    """
    # =========================================================================
    # Table 1: trading.users
    # =========================================================================
    # Purpose: Store user profiles with investment preferences
    # - profile_type: Investment style (conservative, moderate, aggressive)
    # - risk_tolerance: Numeric risk score from 0.00 to 1.00
    # - Timestamps: Created and updated tracking
    #
    # This is the root table - all other trading tables reference users
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trading.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) UNIQUE NOT NULL,
            profile_type VARCHAR(20) CHECK (
                profile_type IN ('conservative', 'moderate', 'aggressive')
            ),
            risk_tolerance NUMERIC(3, 2) CHECK (
                risk_tolerance >= 0 AND risk_tolerance <= 1
            ),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # =========================================================================
    # Table 2: trading.portfolios
    # =========================================================================
    # Purpose: Store portfolio summary for each user (one-to-one with users)
    # - total_value: Total portfolio value (cash + invested)
    # - cash_balance: Available cash for trading
    # - invested_value: Value currently in positions
    # - total_return: Absolute return in currency
    # - total_return_percent: Percentage return
    #
    # UNIQUE(user_id) ensures one portfolio per user
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trading.portfolios (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES trading.users(id) ON DELETE CASCADE,
            total_value NUMERIC(15, 2),
            cash_balance NUMERIC(15, 2),
            invested_value NUMERIC(15, 2),
            total_return NUMERIC(15, 2),
            total_return_percent NUMERIC(10, 4),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(user_id)
        );
        """
    )

    # =========================================================================
    # Table 3: trading.positions
    # =========================================================================
    # Purpose: Track individual stock positions per user
    # - symbol: Stock ticker (e.g., AAPL, MSFT)
    # - quantity: Number of shares held
    # - avg_cost: Average cost basis per share
    # - current_price: Latest market price
    # - current_value: quantity * current_price
    # - unrealized_pnl: Unrealized profit/loss in currency
    # - unrealized_pnl_percent: Percentage gain/loss
    #
    # UNIQUE(user_id, symbol) ensures one position per symbol per user
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trading.positions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES trading.users(id) ON DELETE CASCADE,
            symbol VARCHAR(10) NOT NULL,
            quantity INTEGER NOT NULL,
            avg_cost NUMERIC(15, 2),
            current_price NUMERIC(15, 2),
            current_value NUMERIC(15, 2),
            unrealized_pnl NUMERIC(15, 2),
            unrealized_pnl_percent NUMERIC(10, 4),
            UNIQUE(user_id, symbol)
        );
        """
    )

    # =========================================================================
    # Table 4: trading.orders
    # =========================================================================
    # Purpose: Store trading orders
    # - action: BUY or SELL
    # - order_type: MARKET (execute immediately) or LIMIT (at specified price)
    # - quantity: Number of shares to trade
    # - limit_price: Price limit for LIMIT orders (NULL for MARKET)
    # - status: Order lifecycle state
    # - strategy_id: Optional reference to AI strategy that generated this order
    #
    # Note: user_id reference without CASCADE - we want to keep order history
    # even if the order processing is complex
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trading.orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES trading.users(id) ON DELETE CASCADE,
            strategy_id UUID,
            symbol VARCHAR(10) NOT NULL,
            action VARCHAR(4) NOT NULL CHECK (action IN ('BUY', 'SELL')),
            order_type VARCHAR(6) NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT')),
            quantity INTEGER NOT NULL,
            limit_price NUMERIC(15, 2),
            status VARCHAR(10) NOT NULL CHECK (
                status IN ('PENDING', 'FILLED', 'REJECTED', 'CANCELLED')
            ),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # =========================================================================
    # Table 5: trading.executions
    # =========================================================================
    # Purpose: Store order execution details
    # - order_id: Reference to the parent order
    # - filled_quantity: Number of shares filled in this execution
    # - filled_price: Actual execution price
    # - commission: Trading commission/fee
    # - executed_at: Timestamp of execution
    #
    # One order can have multiple executions (partial fills)
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trading.executions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES trading.orders(id) ON DELETE CASCADE,
            filled_quantity INTEGER NOT NULL,
            filled_price NUMERIC(15, 2) NOT NULL,
            commission NUMERIC(15, 2),
            executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # =========================================================================
    # Table 6: trading.trades
    # =========================================================================
    # Purpose: Store completed trade records for history and analytics
    # - Denormalized from orders/executions for fast querying
    # - Contains all relevant trade information in one place
    # - Used for P&L reporting and trade history views
    #
    # This table is append-only - trades are never modified
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trading.trades (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES trading.users(id) ON DELETE CASCADE,
            symbol VARCHAR(10) NOT NULL,
            action VARCHAR(4) NOT NULL CHECK (action IN ('BUY', 'SELL')),
            quantity INTEGER NOT NULL,
            price NUMERIC(15, 2) NOT NULL,
            total_value NUMERIC(15, 2) NOT NULL,
            commission NUMERIC(15, 2),
            executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


def downgrade() -> None:
    """Drop all tables created by this migration.

    Drop order is the reverse of creation order to handle foreign key dependencies:
    1. trades - no dependencies on it
    2. executions - depends only on orders
    3. orders - depends only on users
    4. positions - depends only on users
    5. portfolios - depends only on users
    6. users - root table, drop last

    IF EXISTS ensures idempotency - safe to run even if some tables are missing.
    """
    # Drop trades (no dependencies on this table)
    op.execute("DROP TABLE IF EXISTS trading.trades;")

    # Drop executions (depends on orders)
    op.execute("DROP TABLE IF EXISTS trading.executions;")

    # Drop orders (depends on users)
    op.execute("DROP TABLE IF EXISTS trading.orders;")

    # Drop positions (depends on users)
    op.execute("DROP TABLE IF EXISTS trading.positions;")

    # Drop portfolios (depends on users)
    op.execute("DROP TABLE IF EXISTS trading.portfolios;")

    # Drop users (root table)
    op.execute("DROP TABLE IF EXISTS trading.users;")
