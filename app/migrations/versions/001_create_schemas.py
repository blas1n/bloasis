"""Create database schemas for BLOASIS Phase 1.

This migration creates the foundational database schemas that organize
tables by domain. Separating tables into schemas provides:
- Logical organization of related tables
- Independent permission management per schema
- Clear boundaries between service domains

Revision ID: 001
Revises:
Create Date: 2026-01-28

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the 3 database schemas for BLOASIS Phase 1.

    Schemas:
    - market_data: Stores market data including OHLCV, indicators, and regime data.
                   Used by Market Data Service for price feeds and analysis.
    - trading: Stores trading-related data including orders, positions, and portfolios.
               Used by Trading Service for order management and execution.
    - analytics: Stores analytics and backtesting results, performance metrics.
                 Used by Analytics Service for strategy evaluation.

    Using IF NOT EXISTS ensures idempotency - the migration can be safely
    re-run without errors if schemas already exist.
    """
    # Schema for market data: OHLCV, indicators, market regime data
    op.execute("CREATE SCHEMA IF NOT EXISTS market_data;")

    # Schema for trading: orders, positions, portfolios
    op.execute("CREATE SCHEMA IF NOT EXISTS trading;")

    # Schema for analytics: backtesting results, performance metrics
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics;")


def downgrade() -> None:
    """Drop all schemas created by this migration.

    CASCADE is required because:
    - Schemas may contain tables, views, functions, and other objects
    - Without CASCADE, DROP SCHEMA fails if the schema is not empty
    - CASCADE automatically drops all contained objects first
    - This ensures clean rollback regardless of what was created in the schema

    Order matters: drop in reverse order of potential dependencies.
    analytics -> trading -> market_data (analytics may reference trading data,
    trading may reference market data).
    """
    # Drop analytics schema and all its contents
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE;")

    # Drop trading schema and all its contents
    op.execute("DROP SCHEMA IF EXISTS trading CASCADE;")

    # Drop market_data schema and all its contents
    op.execute("DROP SCHEMA IF EXISTS market_data CASCADE;")
