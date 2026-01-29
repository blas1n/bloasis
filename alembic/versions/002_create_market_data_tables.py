"""Create market_data schema tables for BLOASIS Phase 1.

This migration creates the core tables for storing market data:
- market_regimes: Time-series data for market regime classifications
- ohlcv_data: Time-series OHLCV (Open/High/Low/Close/Volume) price data
- sector_strategies: Tier 2 sector allocation strategies

Why TimescaleDB Hypertables:
- market_regimes and ohlcv_data are time-series data (append-heavy, time-ordered)
- Hypertables provide automatic partitioning by time (chunks)
- Query performance: 10-100x faster for time-range queries
- Automatic data retention policies can be applied
- Compression: 90%+ compression for historical data
- Continuous aggregates for real-time materialized views

Why NOT hypertable for sector_strategies:
- sector_strategies is reference data, not time-series
- Updated infrequently (when market regime changes)
- Queried by regime/sector, not by time range
- Regular PostgreSQL table is more appropriate

Revision ID: 002
Revises: 001
Create Date: 2026-01-29

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create market_data schema tables.

    Tables created:
    1. market_data.market_regimes - TimescaleDB hypertable for regime classifications
    2. market_data.ohlcv_data - TimescaleDB hypertable for price data
    3. sector_strategies - Regular table for Tier 2 sector allocations

    Financial data constraints:
    - NUMERIC types for all financial values (NOT FLOAT - precision matters)
    - TIMESTAMPTZ for all timestamps (timezone-aware)
    - UUID primary keys with gen_random_uuid() for distributed uniqueness
    - CHECK constraints for data validation (e.g., confidence 0-1)

    Hypertable configuration:
    - Chunk interval: 7 days for market_regimes (regime changes infrequently)
    - Chunk interval: 1 day for ohlcv_data (high-frequency intraday data)
    - if_not_exists: true for idempotent migrations
    """
    # =========================================================================
    # Table 1: market_data.market_regimes (TimescaleDB Hypertable)
    # =========================================================================
    # Purpose: Store market regime classifications from Tier 1 analysis
    # - Regime: Current market state (crisis, normal_bull, normal_bear, etc.)
    # - Confidence: ML model confidence score (0.0 to 1.0)
    # - Trigger: What triggered the regime classification (scheduled, event, manual)
    # - Timestamp: When the regime was classified
    #
    # This is Tier 1 shared data - cached for 6 hours across all users
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_data.market_regimes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regime VARCHAR(50) NOT NULL,
            confidence NUMERIC(5, 4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            trigger VARCHAR(50) NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL
        );
        """
    )

    # Convert to hypertable for time-series optimization
    # Chunk interval: 7 days (regime changes are infrequent)
    op.execute(
        """
        SELECT create_hypertable(
            'market_data.market_regimes',
            'timestamp',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        """
    )

    # =========================================================================
    # Table 2: market_data.ohlcv_data (TimescaleDB Hypertable)
    # =========================================================================
    # Purpose: Store OHLCV (Open/High/Low/Close/Volume) price data
    # - Symbol: Stock/asset ticker symbol (e.g., AAPL, MSFT)
    # - OHLCV: Standard candlestick data with NUMERIC precision
    # - Volume: Trading volume as BIGINT (can exceed 2^31 for popular stocks)
    # - Timestamp: Candle timestamp (supports multiple timeframes)
    #
    # NUMERIC(15, 2) allows prices up to 9,999,999,999,999.99
    # Sufficient for any stock price including BRK.A (~$600,000+)
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_data.ohlcv_data (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol VARCHAR(10) NOT NULL,
            open NUMERIC(15, 2) NOT NULL,
            high NUMERIC(15, 2) NOT NULL,
            low NUMERIC(15, 2) NOT NULL,
            close NUMERIC(15, 2) NOT NULL,
            volume BIGINT NOT NULL,
            timestamp TIMESTAMPTZ NOT NULL
        );
        """
    )

    # Convert to hypertable for time-series optimization
    # Chunk interval: 1 day (high-frequency intraday data)
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

    # =========================================================================
    # Table 3: market_data.sector_strategies (Regular PostgreSQL Table)
    # =========================================================================
    # Purpose: Store Tier 2 sector allocation strategies
    # - Regime: Market regime this strategy applies to
    # - Sector: Sector name (Technology, Healthcare, Energy, etc.)
    # - Strategy: Allocation strategy (overweight, underweight, neutral)
    # - Confidence: Strategy confidence score (0.0 to 1.0)
    # - Top Symbols: Array of recommended symbols for this sector/regime
    # - Created At: When the strategy was generated
    #
    # NOT a hypertable because:
    # - Reference data, not time-series (updated on regime change, not continuously)
    # - Queried by regime/sector combination, not time ranges
    # - Small table size (11 sectors x 6 regimes = 66 rows max)
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_data.sector_strategies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regime VARCHAR(50) NOT NULL,
            sector VARCHAR(50) NOT NULL,
            strategy VARCHAR(50) NOT NULL,
            confidence NUMERIC(5, 4) CHECK (confidence >= 0 AND confidence <= 1),
            top_symbols TEXT[],
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


def downgrade() -> None:
    """Drop all tables created by this migration.

    Drop order matters for hypertables:
    - TimescaleDB hypertables should be dropped normally (DROP TABLE)
    - TimescaleDB handles chunk cleanup automatically
    - No need to explicitly drop hypertable metadata

    Drop in reverse order of creation to handle any potential dependencies.
    """
    # Drop sector_strategies (regular table)
    op.execute("DROP TABLE IF EXISTS market_data.sector_strategies;")

    # Drop ohlcv_data (hypertable - TimescaleDB handles chunk cleanup)
    op.execute("DROP TABLE IF EXISTS market_data.ohlcv_data;")

    # Drop market_regimes (hypertable - TimescaleDB handles chunk cleanup)
    op.execute("DROP TABLE IF EXISTS market_data.market_regimes;")
