"""Persistence helpers for backtest runs.

Wrap the SQLAlchemy core inserts so the engine doesn't sprinkle SQL all
over the place. Each write is a small transaction; the backtester calls
these inline. For ~100 trading days × ~500 symbols this is fine; if the
volume grows, batch via `execute_many` here without the engine caring.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from bloasis.backtest.portfolio import Fill
from bloasis.backtest.result import BacktestResult
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.rationale import Rationale
from bloasis.storage.schema import backtest_runs, equity_curve, feature_log, trades

if TYPE_CHECKING:
    from sqlalchemy import Engine

USER_ID_DEFAULT = 0  # single-user CLI; column kept for future multi-user


def create_backtest_run(
    engine: Engine,
    *,
    name: str | None,
    config_hash: str,
    config_json: str,
    scorer_type: str,
    feature_version: int,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
    git_sha: str | None = None,
) -> int:
    """Insert a `running` backtest_runs row and return its run_id."""
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        result = conn.execute(
            insert(backtest_runs)
            .values(
                user_id=USER_ID_DEFAULT,
                name=name,
                config_hash=config_hash,
                config_json=config_json,
                scorer_type=scorer_type,
                feature_version=feature_version,
                git_sha=git_sha,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                status="running",
                started_at=now,
            )
            .returning(backtest_runs.c.run_id)
        )
        row = result.fetchone()
        assert row is not None
        return int(row[0])


def finalize_backtest_run(
    engine: Engine,
    run_id: int,
    result: BacktestResult,
) -> None:
    """Update the row with final metrics and status='completed'."""
    now = datetime.now(tz=UTC)
    final_equity = (
        result.fold_results[-1].final_equity if result.fold_results else result.initial_capital
    )
    reasons_json = json.dumps(list(result.acceptance_reasons))
    with engine.begin() as conn:
        conn.execute(
            update(backtest_runs)
            .where(backtest_runs.c.run_id == run_id)
            .values(
                final_equity=final_equity,
                total_return=result.median_total_return,
                annualized_return=_avg_annualized(result),
                sharpe=_avg_sharpe(result),
                max_drawdown=_avg_max_dd(result),
                win_rate=result.median_win_rate,
                n_trades=result.n_trades_total,
                alpha_vs_spy=result.median_alpha_annualized,
                passed_acceptance=result.passed_acceptance,
                acceptance_reasons_json=reasons_json,
                status="completed",
                finished_at=now,
            )
        )


def fail_backtest_run(engine: Engine, run_id: int, error_message: str) -> None:
    """Mark the run as failed."""
    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            update(backtest_runs)
            .where(backtest_runs.c.run_id == run_id)
            .values(status="failed", finished_at=now, error_message=error_message[:1000])
        )


def write_equity_curve(
    engine: Engine,
    run_id: int,
    rows: list[dict[str, object]],
) -> None:
    """Bulk-insert equity_curve rows.

    `rows` is a list of dicts with keys timestamp/cash/invested/total_equity.
    """
    if not rows:
        return
    payload = [
        {
            "user_id": USER_ID_DEFAULT,
            "run_id": run_id,
            **r,
        }
        for r in rows
    ]
    with engine.begin() as conn:
        conn.execute(insert(equity_curve), payload)


def write_trade(
    engine: Engine,
    run_id: int,
    fill: Fill,
    rationale: Rationale | None,
    feature_ts: datetime | None = None,
) -> None:
    """Insert one trade row, optionally with a serialized rationale."""
    rationale_json = json.dumps(_serialize_rationale(rationale)) if rationale is not None else None
    with engine.begin() as conn:
        conn.execute(
            insert(trades).values(
                user_id=USER_ID_DEFAULT,
                run_id=run_id,
                timestamp=fill.timestamp,
                symbol=fill.symbol,
                side=fill.side,
                quantity=fill.quantity,
                price=fill.price,
                fees=fill.fees,
                slippage_bps=fill.slippage_bps,
                feature_ts=feature_ts,
                rationale_json=rationale_json,
                realized_pnl=fill.realized_pnl,
            )
        )


def write_feature_log_batch(
    engine: Engine,
    run_id: int,
    vectors: list[FeatureVector],
) -> None:
    """Bulk-insert (upsert) extracted feature vectors keyed by run_id.

    PR13 adds this so the Phase 2 ML labeling job has data to label.
    Idempotent — re-running the same fold replaces existing rows on the
    composite primary key (timestamp, symbol, run_id, feature_version).

    Labels (`forward_return_*`, `label_filled_at`) are left untouched.
    """
    if not vectors:
        return
    now = datetime.now(tz=UTC)
    payload: list[dict[str, object | None]] = []
    for fv in vectors:
        row: dict[str, object | None] = dict(fv.to_db_row())
        row["run_id"] = run_id
        row["created_at"] = now
        payload.append(row)

    # SQLite caps the number of host parameters per statement at 32766
    # (older builds: 999). feature_log has ~33 columns × bulk insert
    # cardinality (a fold can be 60k+ rows on full S&P 500), which
    # blows past the limit. Chunk by row-count derived from the
    # column count to stay safely under the cap.
    n_cols = len(feature_log.columns)
    # ON CONFLICT DO UPDATE adds another set of bind params per chunk; keep
    # headroom well below SQLite's 32766 host-param cap. Using 15_000 lets
    # us add new columns without re-tuning.
    rows_per_chunk = max(1, 15_000 // n_cols)
    update_skip = {
        "timestamp",
        "symbol",
        "run_id",
        "feature_version",
        # Don't clobber labels populated by `bloasis label-features`.
        "forward_return_5d",
        "forward_return_20d",
        "forward_return_60d",
        "label_filled_at",
    }
    with engine.begin() as conn:
        for i in range(0, len(payload), rows_per_chunk):
            chunk = payload[i : i + rows_per_chunk]
            stmt = sqlite_insert(feature_log).values(chunk)
            update_cols = {
                c.name: stmt.excluded[c.name]
                for c in feature_log.columns
                if c.name not in update_skip
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["timestamp", "symbol", "run_id", "feature_version"],
                set_=update_cols,
            )
            conn.execute(stmt)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _serialize_rationale(rationale: Rationale) -> dict[str, object]:
    return {
        "contributions": [asdict(c) for c in rationale.contributions],
        "triggers": list(rationale.triggers),
        "risks": list(rationale.risks),
    }


def _avg_annualized(result: BacktestResult) -> float:
    if not result.fold_results:
        return 0.0
    return sum(f.annualized_return for f in result.fold_results) / len(result.fold_results)


def _avg_sharpe(result: BacktestResult) -> float:
    if not result.fold_results:
        return 0.0
    return sum(f.sharpe for f in result.fold_results) / len(result.fold_results)


def _avg_max_dd(result: BacktestResult) -> float:
    if not result.fold_results:
        return 0.0
    return sum(f.max_drawdown for f in result.fold_results) / len(result.fold_results)


# ---------------------------------------------------------------------------
# Paper trading writers (PR45)
# ---------------------------------------------------------------------------


def create_paper_session(
    engine: Engine,
    *,
    name: str,
    config_hash: str,
    config_json: str,
    user_id: int = 0,
) -> int:
    """Resolve `name` to a session_id, creating the row if it doesn't exist.

    Idempotent: re-running `bloasis trade paper --session X` resumes the
    existing session rather than spawning a duplicate. The (user_id, name)
    pair has a unique index — same name across users is allowed in case
    the schema later supports multi-user.
    """
    from bloasis.storage.schema import paper_sessions

    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        existing = conn.execute(
            select(paper_sessions.c.session_id).where(
                paper_sessions.c.user_id == user_id,
                paper_sessions.c.name == name,
            )
        ).fetchone()
        if existing is not None:
            return int(existing.session_id)

        result = conn.execute(
            insert(paper_sessions)
            .values(
                user_id=user_id,
                name=name,
                config_hash=config_hash,
                config_json=config_json,
                started_at=now,
                status="running",
            )
            .returning(paper_sessions.c.session_id)
        )
        row = result.fetchone()
        assert row is not None
        return int(row.session_id)


def close_paper_session(engine: Engine, *, session_id: int) -> None:
    """Mark the session as `closed` with `ended_at = now()`."""
    from bloasis.storage.schema import paper_sessions

    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            update(paper_sessions)
            .where(paper_sessions.c.session_id == session_id)
            .values(status="closed", ended_at=now)
        )


def write_paper_order(
    engine: Engine,
    *,
    session_id: int,
    ts: datetime,
    symbol: str,
    side: str,
    qty: float,
    target_capital: float,
    entry_price_hint: float | None,
    filled_qty: float,
    filled_avg_price: float,
    broker_status: str,
    broker_order_id: str | None,
    slippage_bps: float | None,
    fees: float,
    rationale_json: str | None,
) -> int:
    """Persist a submitted order with its broker response (filled or rejected)."""
    from bloasis.storage.schema import paper_orders

    with engine.begin() as conn:
        result = conn.execute(
            insert(paper_orders)
            .values(
                session_id=session_id,
                ts=ts,
                symbol=symbol,
                side=side,
                qty=qty,
                target_capital=target_capital,
                entry_price_hint=entry_price_hint,
                filled_qty=filled_qty,
                filled_avg_price=filled_avg_price,
                broker_status=broker_status,
                broker_order_id=broker_order_id,
                slippage_bps=slippage_bps,
                fees=fees,
                rationale_json=rationale_json,
            )
            .returning(paper_orders.c.order_id)
        )
        row = result.fetchone()
        assert row is not None
        return int(row.order_id)


def snapshot_paper_equity(
    engine: Engine,
    *,
    session_id: int,
    ts: datetime,
    cash: float,
    positions_value: float,
    equity: float,
    n_positions: int,
) -> None:
    """Append a daily mark-to-market snapshot from broker.get_account()."""
    from bloasis.storage.schema import paper_equity_snapshots

    with engine.begin() as conn:
        conn.execute(
            insert(paper_equity_snapshots).values(
                session_id=session_id,
                ts=ts,
                cash=cash,
                positions_value=positions_value,
                equity=equity,
                n_positions=n_positions,
            )
        )


def update_paper_order_fill(
    engine: Engine,
    *,
    client_order_id: str,
    broker_status: str,
    filled_qty: float,
    filled_avg_price: float,
    slippage_bps: float | None,
) -> None:
    """Backfill a paper_orders row with the realised fill data.

    The submit-time write captures `broker_status='accepted'` and zero
    filled quantities because the cron fires before US market open. The
    reconcile step queries Alpaca by `client_order_id` hours later and
    updates the row with the actual fill outcome — required for friction
    analysis and per-order PnL.

    No-op when `client_order_id` doesn't match any DB row.
    """
    from bloasis.storage.schema import paper_orders

    with engine.begin() as conn:
        conn.execute(
            update(paper_orders)
            .where(paper_orders.c.broker_order_id == client_order_id)
            .values(
                broker_status=broker_status,
                filled_qty=filled_qty,
                filled_avg_price=filled_avg_price,
                slippage_bps=slippage_bps,
            )
        )


# ---------------------------------------------------------------------------
# Social-post mention pipeline (PR55)
# ---------------------------------------------------------------------------


def upsert_social_post(
    engine: Engine,
    *,
    post_id: str,
    source: str,
    posted_at: datetime,
    content: str,
    url: str | None,
) -> None:
    """Insert-or-ignore a post by post_id. Re-fetching the same archive
    is idempotent — same post_id won't duplicate, content / engagement
    fields are NOT updated (we trust the first capture)."""
    from bloasis.storage.schema import social_posts

    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        existing = conn.execute(
            select(social_posts.c.post_id).where(social_posts.c.post_id == post_id)
        ).fetchone()
        if existing is not None:
            return
        conn.execute(
            insert(social_posts).values(
                post_id=post_id,
                source=source,
                posted_at=posted_at,
                content=content,
                url=url,
                fetched_at=now,
            )
        )


def write_mention(
    engine: Engine,
    *,
    post_id: str,
    ticker: str,
    sentiment: str,
    confidence: float,
    extractor_version: int,
) -> None:
    """Insert one (post, ticker, version) mention row. Composite PK
    (post_id, ticker, extractor_version) makes re-extraction with a
    newer model additive rather than destructive."""
    from bloasis.storage.schema import social_post_mentions

    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        existing = conn.execute(
            select(social_post_mentions).where(
                social_post_mentions.c.post_id == post_id,
                social_post_mentions.c.ticker == ticker,
                social_post_mentions.c.extractor_version == extractor_version,
            )
        ).fetchone()
        if existing is not None:
            return
        conn.execute(
            insert(social_post_mentions).values(
                post_id=post_id,
                ticker=ticker,
                sentiment=sentiment,
                confidence=confidence,
                extracted_at=now,
                extractor_version=extractor_version,
            )
        )


def mark_post_extracted(engine: Engine, *, post_id: str, extractor_version: int) -> None:
    """Stamp a post as extracted so the batch job skips it next time.
    Used even when zero tickers were detected — null result is still a
    result and shouldn't be re-processed by the same extractor."""
    from bloasis.storage.schema import social_posts

    now = datetime.now(tz=UTC)
    with engine.begin() as conn:
        conn.execute(
            update(social_posts)
            .where(social_posts.c.post_id == post_id)
            .values(mentions_extracted_at=now, extractor_version=extractor_version)
        )
