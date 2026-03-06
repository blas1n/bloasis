"""Change quantity columns from INTEGER to NUMERIC for fractional shares

Revision ID: 010
Revises: 009
Create Date: 2026-03-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | Sequence[str] | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Change quantity columns to NUMERIC(18, 8) for fractional share support."""
    op.alter_column(
        "positions",
        "quantity",
        type_=sa.Numeric(18, 8),
        existing_type=sa.Integer(),
        schema="trading",
    )
    op.alter_column(
        "trades",
        "quantity",
        type_=sa.Numeric(18, 8),
        existing_type=sa.Integer(),
        schema="trading",
    )


def downgrade() -> None:
    """Revert quantity columns to INTEGER."""
    op.alter_column(
        "positions",
        "quantity",
        type_=sa.Integer(),
        existing_type=sa.Numeric(18, 8),
        schema="trading",
    )
    op.alter_column(
        "trades",
        "quantity",
        type_=sa.Integer(),
        existing_type=sa.Numeric(18, 8),
        schema="trading",
    )
