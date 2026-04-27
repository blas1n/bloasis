"""Persistence layer.

Uses SQLAlchemy core (Table definitions, no ORM mappers) on top of SQLite.
Same DDL targets PostgreSQL via a different dialect when we migrate.
"""

from bloasis.storage.db import create_all, get_engine
from bloasis.storage.schema import (
    backtest_runs,
    equity_curve,
    feature_log,
    fundamentals_cache,
    metadata,
    news_sentiment_cache,
    positions,
    trades,
)

__all__ = [
    "backtest_runs",
    "create_all",
    "equity_curve",
    "feature_log",
    "fundamentals_cache",
    "get_engine",
    "metadata",
    "news_sentiment_cache",
    "positions",
    "trades",
]
