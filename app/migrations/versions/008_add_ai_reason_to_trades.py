"""Add ai_reason to trades table

Revision ID: 008
Revises: 007
Create Date: 2026-02-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, Sequence[str], None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ai_reason column to trades table."""
    # Add ai_reason column for AI decision reasoning (max 500 chars)
    op.execute(
        """
        ALTER TABLE trading.trades
        ADD COLUMN IF NOT EXISTS ai_reason VARCHAR(500);
        """
    )

    # Create partial index for trades with AI reasons (more efficient than full index)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trades_ai_reason
        ON trading.trades(user_id, executed_at DESC)
        WHERE ai_reason IS NOT NULL;
        """
    )

    # Add comment
    op.execute(
        """
        COMMENT ON COLUMN trading.trades.ai_reason
        IS 'AI-generated reasoning for this trade decision (max 500 characters)';
        """
    )


def downgrade() -> None:
    """Remove ai_reason column from trades table."""
    op.execute("DROP INDEX IF EXISTS trading.idx_trades_ai_reason;")
    op.execute("ALTER TABLE trading.trades DROP COLUMN IF EXISTS ai_reason;")
