"""Add order outbox table and per-user broker config.

Replaces the old trading.orders/executions tables (unused by ORM) with
a new orders table that serves as a transactional outbox for the Saga pattern.

Also adds user_id and broker_type to broker_config for multi-user/multi-broker support.

Revision ID: 012
Revises: 011
Create Date: 2026-03-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "012"
down_revision: str | Sequence[str] | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create order outbox table and update broker_config for multi-user support."""
    # 1. Drop old unused tables (no ORM models, no app code references)
    op.execute("DROP TABLE IF EXISTS trading.executions;")
    op.execute("DROP TABLE IF EXISTS trading.orders;")

    # 2. Create new orders table (Outbox + Saga)
    op.execute(
        """
        CREATE TABLE trading.orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            client_order_id VARCHAR(100) UNIQUE NOT NULL,
            broker_order_id VARCHAR(100),
            broker_type VARCHAR(50) NOT NULL DEFAULT 'alpaca',
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
            qty NUMERIC(18, 8) NOT NULL CHECK (qty > 0),
            price NUMERIC(15, 2) NOT NULL,
            order_type VARCHAR(20) NOT NULL DEFAULT 'market',
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            filled_qty NUMERIC(18, 8) DEFAULT 0,
            filled_avg_price NUMERIC(15, 2),
            error_message TEXT,
            ai_reason TEXT,
            risk_limits_snapshot JSONB,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            submitted_at TIMESTAMPTZ,
            filled_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    # Partial index for active orders (outbox consumer query)
    op.execute(
        """
        CREATE INDEX idx_orders_active_status
            ON trading.orders(status)
            WHERE status IN ('pending', 'submitted', 'partially_filled');
        """
    )

    # User + time index for order history queries
    op.execute(
        """
        CREATE INDEX idx_orders_user_created
            ON trading.orders(user_id, created_at DESC);
        """
    )

    # 3. Update broker_config: add user_id and broker_type columns
    op.execute(
        """
        ALTER TABLE user_data.broker_config
            ADD COLUMN user_id UUID,
            ADD COLUMN broker_type VARCHAR(50) DEFAULT 'alpaca';
        """
    )

    # Remove existing rows without user_id (orphaned global config)
    op.execute("DELETE FROM user_data.broker_config WHERE user_id IS NULL;")

    # Drop old PK and create composite PK
    op.execute(
        """
        ALTER TABLE user_data.broker_config
            DROP CONSTRAINT broker_config_pkey;
        """
    )
    op.execute(
        """
        ALTER TABLE user_data.broker_config
            ADD PRIMARY KEY (user_id, broker_type, config_key);
        """
    )

    # Make user_id NOT NULL after clearing orphaned rows
    op.execute(
        """
        ALTER TABLE user_data.broker_config
            ALTER COLUMN user_id SET NOT NULL;
        """
    )

    # Update trigger for orders
    op.execute(
        """
        CREATE TRIGGER update_orders_updated_at
            BEFORE UPDATE ON trading.orders
            FOR EACH ROW
            EXECUTE FUNCTION user_data.update_updated_at_column();
        """
    )


def downgrade() -> None:
    """Revert to old schema."""
    # Drop new orders table
    op.execute("DROP TABLE IF EXISTS trading.orders;")

    # Revert broker_config: drop new columns, restore old PK
    op.execute(
        """
        ALTER TABLE user_data.broker_config
            DROP CONSTRAINT broker_config_pkey;
        """
    )
    op.execute(
        """
        ALTER TABLE user_data.broker_config
            DROP COLUMN IF EXISTS user_id,
            DROP COLUMN IF EXISTS broker_type;
        """
    )
    op.execute(
        """
        ALTER TABLE user_data.broker_config
            ADD PRIMARY KEY (config_key);
        """
    )

    # Recreate old orders and executions tables (from migration 003)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trading.orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
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
