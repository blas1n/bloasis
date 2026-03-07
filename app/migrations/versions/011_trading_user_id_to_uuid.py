"""Change positions and portfolios user_id from VARCHAR back to UUID

Revision ID: 011
Revises: 010
Create Date: 2026-03-07
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | Sequence[str] | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Change user_id columns from VARCHAR to UUID for type consistency."""
    op.execute(
        """
        ALTER TABLE trading.positions
            ALTER COLUMN user_id TYPE UUID USING user_id::uuid;
        """
    )
    op.execute(
        """
        ALTER TABLE trading.portfolios
            ALTER COLUMN user_id TYPE UUID USING user_id::uuid;
        """
    )


def downgrade() -> None:
    """Revert user_id columns to VARCHAR."""
    op.execute(
        """
        ALTER TABLE trading.positions
            ALTER COLUMN user_id TYPE VARCHAR(255) USING user_id::text;
        """
    )
    op.execute(
        """
        ALTER TABLE trading.portfolios
            ALTER COLUMN user_id TYPE VARCHAR(255) USING user_id::text;
        """
    )
