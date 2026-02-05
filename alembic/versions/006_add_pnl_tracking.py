"""Add P&L tracking columns to trades table.

This migration extends the trades table with:
- order_id: Alpaca order ID for correlation
- realized_pnl: Realized P&L for sell trades

Revision ID: 006
Revises: 005
Create Date: 2026-02-05

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add P&L tracking columns to trades table."""
    # Add order_id column for Alpaca order correlation
    op.execute(
        """
        ALTER TABLE trading.trades
        ADD COLUMN IF NOT EXISTS order_id VARCHAR(100) UNIQUE;
        """
    )

    # Add realized_pnl column for P&L tracking
    op.execute(
        """
        ALTER TABLE trading.trades
        ADD COLUMN IF NOT EXISTS realized_pnl NUMERIC(15, 2) DEFAULT 0;
        """
    )

    # Create index on order_id for fast lookups
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trades_order_id
        ON trading.trades (order_id);
        """
    )

    # Create index on user_id and symbol for trade history queries
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trades_user_symbol
        ON trading.trades (user_id, symbol);
        """
    )

    # Create index on user_id and executed_at for date range queries
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trades_user_date
        ON trading.trades (user_id, executed_at DESC);
        """
    )


def downgrade() -> None:
    """Remove P&L tracking columns from trades table."""
    op.execute("DROP INDEX IF EXISTS trading.idx_trades_user_date;")
    op.execute("DROP INDEX IF EXISTS trading.idx_trades_user_symbol;")
    op.execute("DROP INDEX IF EXISTS trading.idx_trades_order_id;")
    op.execute("ALTER TABLE trading.trades DROP COLUMN IF EXISTS realized_pnl;")
    op.execute("ALTER TABLE trading.trades DROP COLUMN IF EXISTS order_id;")
