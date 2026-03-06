"""Create analytics schema tables for BLOASIS Phase 1.

This migration creates the core tables for storing analytics and backtesting data:
- ai_strategies: AI-generated trading strategies
- backtest_results: TimescaleDB hypertable for backtest performance data
- backtest_metrics: Additional metrics from backtests
- risk_assessments: Risk analysis and decision records

Why TimescaleDB Hypertable for backtest_results:
- Backtest results are time-series data (timestamp-ordered)
- Need efficient querying by time range for performance analysis
- Benefits from automatic partitioning and compression
- Enables continuous aggregates for real-time dashboards

Why NOT hypertables for other tables:
- ai_strategies: Reference data, queried by user_id and strategy_id
- backtest_metrics: Child table, joins with backtest_results by backtest_id
- risk_assessments: Reference data, queried by strategy_id and user_id

Revision ID: 004
Revises: 003
Create Date: 2026-01-29

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create analytics schema tables.

    Tables created:
    1. analytics.ai_strategies - AI-generated trading strategies
    2. analytics.backtest_results - TimescaleDB hypertable for backtest data
    3. analytics.backtest_metrics - Additional backtest metrics
    4. analytics.risk_assessments - Risk analysis and decisions

    Financial data constraints:
    - NUMERIC types for all financial/metric values (NOT FLOAT - precision matters)
    - TIMESTAMPTZ for all timestamps (timezone-aware)
    - UUID primary keys with gen_random_uuid() for distributed uniqueness
    - CHECK constraints for data validation (confidence 0-1, risk_score 0-100)
    - JSONB for flexible structured data (signals, adjustments)
    """
    # =========================================================================
    # Table 1: analytics.ai_strategies
    # =========================================================================
    # Purpose: Store AI-generated trading strategies
    # - user_id: Owner of the strategy
    # - strategy_type: Type of strategy (e.g., momentum, mean_reversion)
    # - regime: Market regime when strategy was generated
    # - signals: JSONB containing buy/sell signals and parameters
    # - rationale: Human-readable explanation of strategy logic
    # - confidence: AI confidence score (0.0 to 1.0)
    # - created_at: When the strategy was generated
    #
    # NOT a hypertable because:
    # - Queried by user_id and strategy_id, not primarily by time range
    # - Reference data that other tables link to
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics.ai_strategies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            strategy_type VARCHAR(50) NOT NULL,
            regime VARCHAR(50) NOT NULL,
            signals JSONB NOT NULL,
            rationale TEXT,
            confidence NUMERIC(5, 4) CHECK (confidence >= 0 AND confidence <= 1),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )

    # =========================================================================
    # Table 2: analytics.backtest_results (TimescaleDB Hypertable)
    # =========================================================================
    # Purpose: Store backtest results from VectorBT, FinRL, or ensemble
    # - strategy_id: Links to ai_strategies table (CASCADE delete)
    # - user_id: Owner of the backtest
    # - engine: Backtesting engine used (vectorbt, finrl, ensemble)
    # - Performance metrics: total_return, sharpe_ratio, max_drawdown
    # - Trade stats: win_rate, total_trades, final_value
    # - timestamp: When the backtest was run
    #
    # Hypertable configuration:
    # - Chunk interval: 1 day (backtests may run frequently during development)
    # - Enables efficient time-range queries for performance analysis
    #
    # Note: Using PRIMARY KEY without DEFAULT because UUID is provided by app
    # to maintain referential integrity with other tables
    # =========================================================================
    # For TimescaleDB hypertables, the partitioning column must be part of any unique constraint
    # Using composite primary key (id, timestamp) to satisfy this requirement
    # Note: Foreign key to ai_strategies is removed because TimescaleDB hypertables
    # have limitations with foreign key references
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics.backtest_results (
            id UUID NOT NULL,
            strategy_id UUID NOT NULL,
            user_id UUID NOT NULL,
            engine VARCHAR(20) NOT NULL CHECK (engine IN ('vectorbt', 'finrl', 'ensemble')),
            total_return NUMERIC(10, 4),
            sharpe_ratio NUMERIC(10, 4),
            max_drawdown NUMERIC(10, 4),
            win_rate NUMERIC(5, 4),
            total_trades INTEGER,
            final_value NUMERIC(15, 2),
            timestamp TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id, timestamp)
        );
        """
    )

    # Convert to hypertable for time-series optimization
    # Chunk interval: 1 day (backtests are run frequently)
    op.execute(
        """
        SELECT create_hypertable(
            'analytics.backtest_results',
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
        """
    )

    # =========================================================================
    # Table 3: analytics.backtest_metrics
    # =========================================================================
    # Purpose: Store additional metrics from backtests (extensible)
    # - backtest_id: Links to backtest_results table
    # - metric_name: Name of the metric (e.g., 'calmar_ratio', 'sortino_ratio')
    # - metric_value: Value of the metric
    # - created_at: When the metric was recorded
    #
    # NOT a hypertable because:
    # - Child table, primarily joined with backtest_results
    # - Queried by backtest_id, not by time range
    # - Small number of metrics per backtest
    # =========================================================================
    # Note: Foreign key to backtest_results is removed because it's a hypertable
    # Referential integrity should be handled at the application level
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics.backtest_metrics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            backtest_id UUID NOT NULL,
            metric_name VARCHAR(50) NOT NULL,
            metric_value NUMERIC(15, 4),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )

    # =========================================================================
    # Table 4: analytics.risk_assessments
    # =========================================================================
    # Purpose: Store risk analysis results and decisions
    # - strategy_id: Links to ai_strategies table
    # - user_id: Owner of the assessment
    # - risk_score: Overall risk score (0.0 to 100.0)
    # - decision: Risk decision (APPROVE, ADJUST, REJECT)
    # - feedback: Human-readable feedback on the assessment
    # - adjustments: JSONB containing suggested position adjustments
    # - created_at: When the assessment was made
    #
    # NOT a hypertable because:
    # - Reference data, queried by strategy_id and user_id
    # - One assessment per strategy typically
    # =========================================================================
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics.risk_assessments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            strategy_id UUID REFERENCES analytics.ai_strategies(id),
            user_id UUID NOT NULL,
            risk_score NUMERIC(5, 2) CHECK (risk_score >= 0 AND risk_score <= 100),
            decision VARCHAR(20) NOT NULL CHECK (decision IN ('APPROVE', 'ADJUST', 'REJECT')),
            feedback TEXT,
            adjustments JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    )


def downgrade() -> None:
    """Drop all tables created by this migration.

    Drop order matters due to foreign key constraints:
    1. risk_assessments - references ai_strategies
    2. backtest_metrics - references backtest_results
    3. backtest_results - references ai_strategies, is a hypertable
    4. ai_strategies - parent table, no dependencies

    TimescaleDB hypertables should be dropped normally (DROP TABLE)
    TimescaleDB handles chunk cleanup automatically.
    """
    # Drop risk_assessments (references ai_strategies)
    op.execute("DROP TABLE IF EXISTS analytics.risk_assessments;")

    # Drop backtest_metrics (references backtest_results)
    op.execute("DROP TABLE IF EXISTS analytics.backtest_metrics;")

    # Drop backtest_results (hypertable - TimescaleDB handles chunk cleanup)
    op.execute("DROP TABLE IF EXISTS analytics.backtest_results;")

    # Drop ai_strategies (parent table)
    op.execute("DROP TABLE IF EXISTS analytics.ai_strategies;")
