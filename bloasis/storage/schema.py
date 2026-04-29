"""SQLAlchemy core table definitions.

Schema overview:
  - feature_log         per-(symbol,timestamp) features. Universe-level (no user_id).
  - fundamentals_cache  cached fundamentals from yf Screener / ticker.info.
  - news_sentiment_cache LLM-scored news sentiment, universe-level.
  - backtest_runs       metadata + final metrics for each backtest invocation.
  - trades              executed orders (live and simulated).
  - positions           open positions, live only.
  - equity_curve        portfolio mark-to-market timeseries.

User scoping: `user_id INTEGER NOT NULL DEFAULT 0` on user-scoped tables.
v1 always uses user_id=0; column exists to allow multi-user later without
schema migration.

Composite primary keys on `feature_log` allow same (symbol, timestamp) row
to coexist across multiple backtest runs (`run_id`) and feature versions.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
)

metadata = MetaData()


# ---------------------------------------------------------------------------
# feature_log — per-(symbol, timestamp) extracted features
# ---------------------------------------------------------------------------
# Universe-level: features depend only on market state, not user.
# `run_id` IS NULL  -> live extraction
# `run_id` NOT NULL -> backtest extraction tied to backtest_runs.run_id
#
# Forward returns (label_*) are filled by a post-write job after sufficient
# bars have elapsed. `label_filled_at IS NULL` partial index lets the
# labeling job efficiently scan unlabeled rows.
#
# `feature_version` lets us evolve extraction logic without losing old data;
# ML training filters by version.
feature_log = Table(
    "feature_log",
    metadata,
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("symbol", String(16), nullable=False),
    Column("run_id", Integer, nullable=True),
    Column("feature_version", Integer, nullable=False),
    # Fundamentals
    Column("per", Float, nullable=True),
    Column("pbr", Float, nullable=True),
    Column("market_cap", Float, nullable=True),
    Column("profit_margin", Float, nullable=True),
    Column("roe", Float, nullable=True),
    Column("debt_to_equity", Float, nullable=True),
    Column("current_ratio", Float, nullable=True),
    # Technicals
    Column("rsi_14", Float, nullable=True),
    Column("macd", Float, nullable=True),
    Column("macd_signal", Float, nullable=True),
    Column("macd_hist", Float, nullable=True),
    Column("adx_14", Float, nullable=True),
    Column("atr_14", Float, nullable=True),
    Column("bb_width", Float, nullable=True),
    # Price/volume derived
    Column("momentum_20d", Float, nullable=True),
    Column("momentum_60d", Float, nullable=True),
    Column("volatility_20d", Float, nullable=True),
    Column("volume_ratio_20d", Float, nullable=True),
    # Context (raw; classify_regime() applies for display)
    Column("sector", String(64), nullable=True),
    Column("vix", Float, nullable=True),
    Column("spy_above_sma200", Integer, nullable=True),
    Column("vix_zscore_60d", Float, nullable=True),
    # Sentiment (live only; NULL for backtest periods)
    Column("sentiment_score", Float, nullable=True),
    Column("news_count", Integer, nullable=True),
    # Forward labels (filled async by labeling job)
    Column("forward_return_5d", Float, nullable=True),
    Column("forward_return_20d", Float, nullable=True),
    Column("forward_return_60d", Float, nullable=True),
    Column("label_filled_at", DateTime(timezone=True), nullable=True),
    # Provenance
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint(
        "timestamp",
        "symbol",
        "run_id",
        "feature_version",
        name="pk_feature_log",
    ),
)

Index("idx_feature_log_symbol_ts", feature_log.c.symbol, feature_log.c.timestamp)
Index("idx_feature_log_run_ts", feature_log.c.run_id, feature_log.c.timestamp)
Index(
    "idx_feature_log_unlabeled",
    feature_log.c.label_filled_at,
    sqlite_where=feature_log.c.label_filled_at.is_(None),
)
# SQLite treats NULLs as distinct in composite PKs, so the (..., run_id=NULL, ...)
# slice would otherwise allow duplicates for live extractions. Enforce uniqueness
# via a partial index on the run_id IS NULL case.
Index(
    "uq_feature_log_live",
    feature_log.c.timestamp,
    feature_log.c.symbol,
    feature_log.c.feature_version,
    unique=True,
    sqlite_where=feature_log.c.run_id.is_(None),
)


# ---------------------------------------------------------------------------
# fundamentals_cache — bulk fetch from yf Screener
# ---------------------------------------------------------------------------
# Universe-level. Refreshed daily or on demand. Used by pre-filter stage
# without re-fetching per analysis.
fundamentals_cache = Table(
    "fundamentals_cache",
    metadata,
    Column("symbol", String(16), nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("sector", String(64), nullable=True),
    Column("industry", String(128), nullable=True),
    Column("market_cap", Float, nullable=True),
    Column("pe_ratio_ttm", Float, nullable=True),
    Column("pb_ratio", Float, nullable=True),
    Column("dollar_volume_avg", Float, nullable=True),
    Column("profit_margin", Float, nullable=True),
    Column("roe", Float, nullable=True),
    Column("debt_to_equity", Float, nullable=True),
    Column("current_ratio", Float, nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("symbol", "fetched_at", name="pk_fundamentals_cache"),
)

Index(
    "idx_fundamentals_cache_expiry",
    fundamentals_cache.c.symbol,
    fundamentals_cache.c.expires_at,
)


# ---------------------------------------------------------------------------
# news_sentiment_cache — LLM-scored sentiment, universe-level
# ---------------------------------------------------------------------------
news_sentiment_cache = Table(
    "news_sentiment_cache",
    metadata,
    Column("symbol", String(16), nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("score", Float, nullable=False),  # [-1, 1]
    Column("article_count", Integer, nullable=False),
    Column("headlines_json", Text, nullable=True),  # audit trail
    Column("expires_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("symbol", "fetched_at", name="pk_news_sentiment_cache"),
    CheckConstraint("score >= -1.0 AND score <= 1.0", name="ck_news_sentiment_score"),
)

Index(
    "idx_news_sentiment_expiry",
    news_sentiment_cache.c.symbol,
    news_sentiment_cache.c.expires_at,
)


# ---------------------------------------------------------------------------
# backtest_runs — one row per backtest invocation
# ---------------------------------------------------------------------------
# Stores both the immutable inputs (config_hash, config_json, period) and
# the computed outputs (final metrics, status). Status transitions:
# 'running' -> 'completed' | 'failed'.
backtest_runs = Table(
    "backtest_runs",
    metadata,
    Column("run_id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False, server_default="0"),
    Column("name", String(128), nullable=True),
    # Immutable run inputs
    Column("config_hash", String(16), nullable=False),
    Column("config_json", Text, nullable=False),
    Column("scorer_type", String(16), nullable=False),
    Column("feature_version", Integer, nullable=False),
    Column("git_sha", String(40), nullable=True),
    Column("start_date", DateTime(timezone=True), nullable=False),
    Column("end_date", DateTime(timezone=True), nullable=False),
    Column("initial_capital", Float, nullable=False),
    # Computed results
    Column("final_equity", Float, nullable=True),
    Column("total_return", Float, nullable=True),
    Column("annualized_return", Float, nullable=True),
    Column("sharpe", Float, nullable=True),
    Column("max_drawdown", Float, nullable=True),
    Column("win_rate", Float, nullable=True),
    Column("n_trades", Integer, nullable=True),
    Column("alpha_vs_spy", Float, nullable=True),
    # Acceptance gate result (machine-checked promotion criterion).
    # `passed_acceptance` is the boolean used by `bloasis trade live --from-run`
    # to gate live submissions; `acceptance_reasons_json` stores the per-criterion
    # PASS/FAIL strings from `AcceptanceEvaluator` for audit and `runs show`.
    Column("passed_acceptance", Boolean, nullable=True),  # NULL while running
    Column("acceptance_reasons_json", Text, nullable=True),
    # Status
    Column("status", String(16), nullable=False, server_default="running"),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error_message", Text, nullable=True),
    CheckConstraint(
        "status IN ('running', 'completed', 'failed')",
        name="ck_backtest_runs_status",
    ),
)

Index("idx_backtest_runs_user", backtest_runs.c.user_id, backtest_runs.c.started_at)
Index("idx_backtest_runs_hash", backtest_runs.c.config_hash)


# ---------------------------------------------------------------------------
# trades — every executed (or simulated) order
# ---------------------------------------------------------------------------
# `run_id` IS NULL  -> live trade
# `run_id` NOT NULL -> simulated trade in backtest_runs.run_id
trades = Table(
    "trades",
    metadata,
    Column("trade_id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False, server_default="0"),
    Column("run_id", Integer, ForeignKey("backtest_runs.run_id"), nullable=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("symbol", String(16), nullable=False),
    Column("side", String(4), nullable=False),
    Column("quantity", Float, nullable=False),
    Column("price", Float, nullable=False),
    Column("fees", Float, nullable=False, server_default="0"),
    Column("slippage_bps", Float, nullable=True),
    # Provenance — links trade back to features and rationale that produced it
    Column("feature_ts", DateTime(timezone=True), nullable=True),
    Column("rationale_json", Text, nullable=True),
    # Exit linkage (filled when this trade closes a prior open trade)
    Column("open_trade_id", Integer, ForeignKey("trades.trade_id"), nullable=True),
    Column("realized_pnl", Float, nullable=True),
    CheckConstraint("side IN ('buy', 'sell')", name="ck_trades_side"),
    CheckConstraint("quantity > 0", name="ck_trades_quantity"),
)

Index("idx_trades_user_run_ts", trades.c.user_id, trades.c.run_id, trades.c.timestamp)
Index("idx_trades_symbol", trades.c.symbol)


# ---------------------------------------------------------------------------
# positions — currently-held positions, live only
# ---------------------------------------------------------------------------
# Backtest runs maintain positions in memory; only live state persists here.
positions = Table(
    "positions",
    metadata,
    Column("user_id", Integer, nullable=False, server_default="0"),
    Column("symbol", String(16), nullable=False),
    Column("quantity", Float, nullable=False),
    Column("avg_cost", Float, nullable=False),
    Column("opened_at", DateTime(timezone=True), nullable=False),
    Column("stop_loss", Float, nullable=True),
    Column("take_profit", Float, nullable=True),
    Column("trailing_stop_pct", Float, nullable=True),
    Column("open_trade_id", Integer, ForeignKey("trades.trade_id"), nullable=True),
    Column("last_updated", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("user_id", "symbol", name="pk_positions"),
    CheckConstraint("quantity > 0", name="ck_positions_quantity"),
)


# ---------------------------------------------------------------------------
# equity_curve — portfolio mark-to-market timeseries
# ---------------------------------------------------------------------------
equity_curve = Table(
    "equity_curve",
    metadata,
    Column("user_id", Integer, nullable=False, server_default="0"),
    Column("run_id", Integer, ForeignKey("backtest_runs.run_id"), nullable=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("cash", Float, nullable=False),
    Column("invested", Float, nullable=False),
    Column("total_equity", Float, nullable=False),
    PrimaryKeyConstraint("user_id", "run_id", "timestamp", name="pk_equity_curve"),
)

# Partial unique index for the live (run_id IS NULL) slice — see feature_log
# comment above for rationale.
Index(
    "uq_equity_curve_live",
    equity_curve.c.user_id,
    equity_curve.c.timestamp,
    unique=True,
    sqlite_where=equity_curve.c.run_id.is_(None),
)
