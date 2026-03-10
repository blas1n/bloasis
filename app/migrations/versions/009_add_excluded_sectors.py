"""Add excluded_sectors to user_preferences table

Revision ID: 009
Revises: 008
Create Date: 2026-03-04
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | Sequence[str] | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add excluded_sectors column to user_preferences table."""
    op.execute(
        "ALTER TABLE user_data.user_preferences"
        " ADD COLUMN IF NOT EXISTS excluded_sectors TEXT[] DEFAULT '{}'::text[]"
    )


def downgrade() -> None:
    """Remove excluded_sectors column from user_preferences table."""
    op.drop_column("user_preferences", "excluded_sectors", schema="user_data")
