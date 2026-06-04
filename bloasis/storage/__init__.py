"""Persistence layer.

Uses SQLAlchemy core (Table definitions, no ORM mappers) on top of SQLite.
Same DDL targets PostgreSQL via a different dialect when we migrate.
"""

from bloasis.storage import writers  # noqa: E402  — must come after schema/db
from bloasis.storage.db import create_all, get_engine
from bloasis.storage.schema import (
    backtest_runs,
    equity_curve,
    feature_log,
    fundamentals_cache,
    mention_predictions,
    metadata,
    news_sentiment_cache,
    paper_equity_snapshots,
    paper_orders,
    paper_sessions,
    positions,
    social_post_mentions,
    social_posts,
    trades,
)

__all__ = [
    "backtest_runs",
    "create_all",
    "equity_curve",
    "feature_log",
    "fundamentals_cache",
    "get_engine",
    "mention_predictions",
    "metadata",
    "news_sentiment_cache",
    "paper_equity_snapshots",
    "paper_orders",
    "paper_sessions",
    "positions",
    "social_post_mentions",
    "social_posts",
    "trades",
    "writers",
]
