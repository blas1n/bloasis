"""Update market_data schema to align with ORM models.

This migration fixes schema mismatches between migration 002 and SQLAlchemy models:

1. ohlcv_data table changes:
   - Change precision from NUMERIC(15,2) to NUMERIC(18,8) for price fields
   - Change primary key from (id, timestamp) to (symbol, timestamp)
   - Add 'interval' column for timeframe support
   - Add 'adj_close' column for adjusted close prices
   - Expand symbol VARCHAR(10) to VARCHAR(20)

2. stock_info table (NEW):
   - Create market_data.stock_info for stock metadata
   - Symbol as primary key
   - Includes sector, industry, market cap, etc.

Revision ID: 005
Revises: 004
Create Date: 2026-02-01

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update market_data schema to match ORM models.

    Note: Since ohlcv_data is a TimescaleDB hypertable and we need to change
    the primary key structure, we drop and recreate the table. This is acceptable
    in development phase. For production, use a more careful migration strategy.
    """
    # =========================================================================
    # Step 1: Drop and recreate ohlcv_data with correct schema
    # =========================================================================
    # Drop the existing hypertable (TimescaleDB handles chunk cleanup)
    op.execute("DROP TABLE IF EXISTS market_data.ohlcv_data CASCADE;")

    # Recreate ohlcv_data with correct schema matching ORM model
    # Changes from original:
    # - Primary key: (symbol, timestamp) instead of (id, timestamp)
    # - Precision: NUMERIC(18,8) instead of NUMERIC(15,2)
    # - Added: interval column for timeframe (1d, 1h, etc.)
    # - Added: adj_close for split/dividend adjusted prices
    # - Symbol: VARCHAR(20) instead of VARCHAR(10)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_data.ohlcv_data (
            symbol VARCHAR(20) NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            interval VARCHAR(10) NOT NULL DEFAULT '1d',
            open NUMERIC(18, 8) NOT NULL,
            high NUMERIC(18, 8) NOT NULL,
            low NUMERIC(18, 8) NOT NULL,
            close NUMERIC(18, 8) NOT NULL,
            volume BIGINT NOT NULL,
            adj_close NUMERIC(18, 8),
            PRIMARY KEY (symbol, timestamp)
        );
        """
    )

    # Convert to hypertable for time-series optimization
    # Chunk interval: 1 day for high-frequency intraday data
    op.execute(
        """
        SELECT create_hypertable(
            'market_data.ohlcv_data',
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
        """
    )

    # Create indexes for common query patterns
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol
        ON market_data.ohlcv_data (symbol, timestamp DESC);
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_interval
        ON market_data.ohlcv_data (symbol, interval, timestamp DESC);
        """
    )

    # =========================================================================
    # Step 2: Create stock_info table (NEW)
    # =========================================================================
    # Purpose: Store stock metadata from yfinance
    # - Symbol as primary key (one record per stock)
    # - Contains company info, sector, industry, market cap
    # - Used for filtering and classification
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_data.stock_info (
            symbol VARCHAR(20) PRIMARY KEY,
            name VARCHAR(255),
            sector VARCHAR(100),
            industry VARCHAR(100),
            exchange VARCHAR(50),
            currency VARCHAR(10) NOT NULL DEFAULT 'USD',
            market_cap NUMERIC(20, 2),
            pe_ratio NUMERIC(10, 4),
            dividend_yield NUMERIC(10, 6),
            fifty_two_week_high NUMERIC(18, 8),
            fifty_two_week_low NUMERIC(18, 8),
            updated_at TIMESTAMPTZ
        );
        """
    )

    # Create index for sector-based queries
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_stock_info_sector
        ON market_data.stock_info (sector);
        """
    )


def downgrade() -> None:
    """Revert to original schema from migration 002.

    This restores the original ohlcv_data structure and drops stock_info.
    """
    # Drop stock_info table
    op.execute("DROP TABLE IF EXISTS market_data.stock_info;")

    # Drop updated ohlcv_data
    op.execute("DROP TABLE IF EXISTS market_data.ohlcv_data CASCADE;")

    # Recreate original ohlcv_data from migration 002
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_data.ohlcv_data (
            id UUID DEFAULT gen_random_uuid(),
            symbol VARCHAR(10) NOT NULL,
            open NUMERIC(15, 2) NOT NULL,
            high NUMERIC(15, 2) NOT NULL,
            low NUMERIC(15, 2) NOT NULL,
            close NUMERIC(15, 2) NOT NULL,
            volume BIGINT NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id, timestamp)
        );
        """
    )

    # Recreate hypertable
    op.execute(
        """
        SELECT create_hypertable(
            'market_data.ohlcv_data',
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
        """
    )
