"""Add currency column to positions and portfolios tables.

This migration adds currency support to portfolio tracking:
- positions.currency: Currency for each position (default USD)
- positions.created_at: Creation timestamp
- positions.updated_at: Last update timestamp

Also updates portfolios table to use string user_id instead of UUID
to match the service implementation.

Revision ID: 007
Revises: 006
Create Date: 2026-02-15

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, Sequence[str], None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add currency and timestamp columns to positions table.

    Also update portfolios table schema to match service implementation.
    """
    # Add currency column to positions table
    op.execute(
        """
        ALTER TABLE trading.positions
        ADD COLUMN IF NOT EXISTS currency VARCHAR(3) NOT NULL DEFAULT 'USD';
        """
    )

    # Add created_at column to positions table
    op.execute(
        """
        ALTER TABLE trading.positions
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
        """
    )

    # Add updated_at column to positions table
    op.execute(
        """
        ALTER TABLE trading.positions
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
        """
    )

    # Update positions to use string user_id (matching portfolios)
    # First, check if we need to change the column type
    op.execute(
        """
        DO $$
        BEGIN
            -- Drop existing foreign key constraint if it exists
            ALTER TABLE trading.positions
            DROP CONSTRAINT IF EXISTS positions_user_id_fkey;

            -- Change user_id column type from UUID to VARCHAR(255)
            ALTER TABLE trading.positions
            ALTER COLUMN user_id TYPE VARCHAR(255) USING user_id::text;

            -- Recreate index
            CREATE INDEX IF NOT EXISTS ix_positions_user_id
            ON trading.positions(user_id);
        END $$;
        """
    )

    # Update portfolios to use string user_id as well
    op.execute(
        """
        DO $$
        BEGIN
            -- Drop existing foreign key and unique constraints
            ALTER TABLE trading.portfolios
            DROP CONSTRAINT IF EXISTS portfolios_user_id_fkey;

            ALTER TABLE trading.portfolios
            DROP CONSTRAINT IF EXISTS portfolios_user_id_key;

            -- Change user_id column type from UUID to VARCHAR(255)
            ALTER TABLE trading.portfolios
            ALTER COLUMN user_id TYPE VARCHAR(255) USING user_id::text;

            -- Add currency column to portfolios if it doesn't exist
            ALTER TABLE trading.portfolios
            ADD COLUMN IF NOT EXISTS currency VARCHAR(3) NOT NULL DEFAULT 'USD';

            -- Add created_at if missing
            ALTER TABLE trading.portfolios
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

            -- Recreate unique constraint and index
            ALTER TABLE trading.portfolios
            ADD CONSTRAINT portfolios_user_id_unique UNIQUE (user_id);

            CREATE INDEX IF NOT EXISTS ix_portfolios_user_id
            ON trading.portfolios(user_id);
        END $$;
        """
    )


def downgrade() -> None:
    """Remove currency and timestamp columns from positions table."""
    # Remove added columns from positions
    op.execute(
        """
        ALTER TABLE trading.positions
        DROP COLUMN IF EXISTS currency,
        DROP COLUMN IF EXISTS created_at,
        DROP COLUMN IF EXISTS updated_at;
        """
    )

    # Remove added columns from portfolios
    op.execute(
        """
        ALTER TABLE trading.portfolios
        DROP COLUMN IF EXISTS currency,
        DROP COLUMN IF EXISTS created_at;
        """
    )

    # Note: Reverting user_id type changes is complex and may cause data loss
    # This is intentionally omitted as downgrades are rare in production
