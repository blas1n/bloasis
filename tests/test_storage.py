"""Tests for `bloasis.storage` — schema and DDL bootstrap."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from bloasis.storage import (
    backtest_runs,
    create_all,
    equity_curve,
    feature_log,
    fundamentals_cache,
    get_engine,
    metadata,
    news_sentiment_cache,
    positions,
    trades,
)

# ---------------------------------------------------------------------------
# DDL bootstrap
# ---------------------------------------------------------------------------


def test_create_all_creates_all_tables(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)

    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    expected = {
        "feature_log",
        "fundamentals_cache",
        "news_sentiment_cache",
        "backtest_runs",
        "trades",
        "positions",
        "equity_curve",
    }
    assert expected.issubset(names)


def test_create_all_is_idempotent(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    create_all(engine)  # second call should not raise


def test_metadata_table_count_matches() -> None:
    # Sanity: schema module exposes exactly the 7 tables in metadata
    assert len(metadata.tables) == 7


# ---------------------------------------------------------------------------
# feature_log — composite PK and constraints
# ---------------------------------------------------------------------------


def test_feature_log_composite_pk_allows_multiple_runs(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    base = {
        "timestamp": ts,
        "symbol": "AAPL",
        "feature_version": 1,
        "created_at": datetime.now(UTC),
    }
    with engine.begin() as conn:
        # Same (timestamp, symbol, feature_version) but different run_id should coexist.
        conn.execute(insert(feature_log).values(**base, run_id=None))
        conn.execute(insert(feature_log).values(**base, run_id=1))
        conn.execute(insert(feature_log).values(**base, run_id=2))

        rows = conn.execute(
            select(feature_log.c.run_id).where(
                feature_log.c.symbol == "AAPL",
                feature_log.c.timestamp == ts,
            )
        ).fetchall()

    assert {r[0] for r in rows} == {None, 1, 2}


def test_feature_log_duplicate_pk_rejected(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    base = {
        "timestamp": datetime(2024, 1, 2, tzinfo=UTC),
        "symbol": "AAPL",
        "run_id": None,
        "feature_version": 1,
        "created_at": datetime.now(UTC),
    }
    with engine.begin() as conn:
        conn.execute(insert(feature_log).values(**base))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(feature_log).values(**base))


# ---------------------------------------------------------------------------
# trades — side check, FK, user_id default
# ---------------------------------------------------------------------------


def test_trades_side_check_constraint(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            insert(trades).values(
                user_id=0,
                timestamp=datetime.now(UTC),
                symbol="AAPL",
                side="hold",  # invalid
                quantity=10,
                price=100,
                fees=0,
            )
        )


def test_trades_user_id_default_zero(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    with engine.begin() as conn:
        result = conn.execute(
            insert(trades)
            .values(
                timestamp=datetime.now(UTC),
                symbol="AAPL",
                side="buy",
                quantity=1,
                price=100,
            )
            .returning(trades.c.user_id)
        )
        user_id = result.scalar_one()
    assert user_id == 0


# ---------------------------------------------------------------------------
# positions — composite PK and quantity check
# ---------------------------------------------------------------------------


def test_positions_unique_per_user_symbol(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    now = datetime.now(UTC)
    base = {
        "user_id": 0,
        "symbol": "AAPL",
        "quantity": 10,
        "avg_cost": 150,
        "opened_at": now,
        "last_updated": now,
    }
    with engine.begin() as conn:
        conn.execute(insert(positions).values(**base))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(positions).values(**base))


# ---------------------------------------------------------------------------
# news_sentiment_cache — score range constraint
# ---------------------------------------------------------------------------


def test_news_sentiment_score_range(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    now = datetime.now(UTC)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            insert(news_sentiment_cache).values(
                symbol="AAPL",
                fetched_at=now,
                score=2.0,  # > 1.0 violates constraint
                article_count=3,
                expires_at=now,
            )
        )


# ---------------------------------------------------------------------------
# backtest_runs — status check, FK from trades
# ---------------------------------------------------------------------------


def test_backtest_runs_status_check(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            insert(backtest_runs).values(
                user_id=0,
                config_hash="abc",
                config_json="{}",
                scorer_type="rule",
                feature_version=1,
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 1, 31, tzinfo=UTC),
                initial_capital=10000.0,
                status="zombie",  # invalid
                started_at=datetime.now(UTC),
            )
        )


def test_trades_fk_to_backtest_runs(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    # Pointing at a non-existent run_id should fail with FK enforcement on
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            insert(trades).values(
                user_id=0,
                run_id=9999,  # no such backtest_run
                timestamp=datetime.now(UTC),
                symbol="AAPL",
                side="buy",
                quantity=1,
                price=100,
            )
        )


# ---------------------------------------------------------------------------
# equity_curve — composite PK
# ---------------------------------------------------------------------------


def test_equity_curve_composite_pk(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    ts = datetime(2024, 1, 2, tzinfo=UTC)
    base = {
        "user_id": 0,
        "run_id": None,
        "timestamp": ts,
        "cash": 1000,
        "invested": 0,
        "total_equity": 1000,
    }
    with engine.begin() as conn:
        conn.execute(insert(equity_curve).values(**base))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(equity_curve).values(**base))


# ---------------------------------------------------------------------------
# fundamentals_cache — basic insert smoke
# ---------------------------------------------------------------------------


def test_fundamentals_cache_insert(tmp_db_path: Path) -> None:
    engine = get_engine(tmp_db_path)
    create_all(engine)
    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            insert(fundamentals_cache).values(
                symbol="AAPL",
                fetched_at=now,
                sector="Technology",
                market_cap=3.0e12,
                pe_ratio_ttm=28.5,
                expires_at=now,
            )
        )
        rows = conn.execute(select(fundamentals_cache.c.sector)).fetchall()
    assert rows[0][0] == "Technology"
