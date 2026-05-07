"""Forward-return labeling for the `feature_log` table.

For each (symbol, timestamp) row, compute close-to-close pct returns
over fixed lookahead horizons (5/20/60 trading days by default) and
populate `forward_return_*` + `label_filled_at`.

Designed as a stateless batch — re-running is idempotent (skips rows
where `label_filled_at IS NOT NULL`). Cron-friendly.

The DB writes happen here; the OHLCV source is injected as a callable
so the CLI can wire ParquetCache while tests pass synthetic series.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import select, update

from bloasis.storage import feature_log

if TYPE_CHECKING:
    from sqlalchemy import Engine

DEFAULT_LOOKBACKS: tuple[int, ...] = (5, 20, 60)

# `forward_return_<n>d` schema columns we update (PR9 storage/schema.py).
LOOKBACK_TO_COLUMN: dict[int, str] = {
    5: "forward_return_5d",
    20: "forward_return_20d",
    60: "forward_return_60d",
}


def compute_forward_returns(
    close: pd.Series,
    t: pd.Timestamp | datetime,
    lookbacks: list[int] | tuple[int, ...] = DEFAULT_LOOKBACKS,
) -> dict[int, float]:
    """Pct return from `close[t]` to `close[t + lookback]` for each horizon.

    `t` is normalized to the most recent trading bar at or before the given
    timestamp (so weekend / intraday timestamps map to Friday's close).
    Each horizon entry is `NaN` if there isn't enough forward data, the base
    price is zero/non-finite, or the forward bar itself is non-finite.

    A negative `lookback` is rejected with `ValueError`.
    """
    for lb in lookbacks:
        if lb < 0:
            raise ValueError(f"lookback must be >= 0, got {lb}")

    if not lookbacks or close is None or close.empty:
        return {lb: float("nan") for lb in lookbacks}

    ts = pd.Timestamp(t)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    sorted_close = close.sort_index()
    idx = pd.DatetimeIndex(sorted_close.index)
    if idx.tz is not None:
        sorted_close = sorted_close.copy()
        sorted_close.index = idx.tz_convert("UTC").tz_localize(None)

    # Find the integer index of the latest bar at or before `ts`.
    le_mask = sorted_close.index <= ts
    if not bool(le_mask.any()):
        return {lb: float("nan") for lb in lookbacks}
    base_idx = int(le_mask.sum()) - 1
    base = float(sorted_close.iloc[base_idx])
    if base == 0 or not math.isfinite(base):
        return {lb: float("nan") for lb in lookbacks}

    out: dict[int, float] = {}
    n = len(sorted_close)
    for lb in lookbacks:
        target = base_idx + lb
        if target >= n:
            out[lb] = float("nan")
            continue
        top = float(sorted_close.iloc[target])
        if not math.isfinite(top):
            out[lb] = float("nan")
            continue
        out[lb] = (top - base) / base
    return out


def label_unlabeled_features(
    engine: Engine,
    ohlcv_provider: Callable[[str], pd.Series | None],
    *,
    lookbacks: list[int] | tuple[int, ...] = DEFAULT_LOOKBACKS,
    batch_size: int = 1_000,
) -> int:
    """Fill forward-return labels for every `feature_log` row with
    `label_filled_at IS NULL`. Returns the number of rows labeled.

    Symbols are batched: for each unique symbol with pending rows we call
    `ohlcv_provider(symbol)` once, then label every row in that group.
    `ohlcv_provider` returning `None` skips the symbol entirely (rows stay
    pending for a future pass once the cache is populated).

    All rows for which the provider returns a series are marked
    `label_filled_at = now()` even if every horizon resolved to NaN —
    otherwise we'd re-attempt the same hopeless rows on every cron tick.
    """
    lookback_cols = {lb: LOOKBACK_TO_COLUMN[lb] for lb in lookbacks if lb in LOOKBACK_TO_COLUMN}
    if not lookback_cols:
        return 0

    # Pull every (symbol, timestamp, run_id, feature_version) needing labels.
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                feature_log.c.symbol,
                feature_log.c.timestamp,
                feature_log.c.run_id,
                feature_log.c.feature_version,
            ).where(feature_log.c.label_filled_at.is_(None))
        ).all()

    if not rows:
        return 0

    by_symbol: dict[str, list[tuple[datetime, int | None, int]]] = {}
    for row in rows:
        by_symbol.setdefault(row.symbol, []).append(
            (row.timestamp, row.run_id, row.feature_version)
        )

    labeled = 0
    now = datetime.now(tz=UTC)
    for symbol, pending in by_symbol.items():
        close = ohlcv_provider(symbol)
        if close is None:
            continue  # cache miss — leave label_filled_at NULL for retry
        # Buffer updates per symbol; flush in chunks to keep transactions short.
        updates: list[dict[str, object]] = []
        for ts, run_id, fv in pending:
            fwd = compute_forward_returns(close, ts, lookbacks=list(lookbacks))
            payload: dict[str, object] = {"label_filled_at": now}
            for lb, col in lookback_cols.items():
                v = fwd.get(lb, float("nan"))
                payload[col] = None if not math.isfinite(v) else v
            payload["timestamp"] = ts
            payload["symbol"] = symbol
            payload["run_id"] = run_id
            payload["feature_version"] = fv
            updates.append(payload)

        # Flush in chunks.
        for i in range(0, len(updates), batch_size):
            chunk = updates[i : i + batch_size]
            with engine.begin() as conn:
                for u in chunk:
                    stmt = (
                        update(feature_log)
                        .where(
                            feature_log.c.timestamp == u["timestamp"],
                            feature_log.c.symbol == u["symbol"],
                            feature_log.c.feature_version == u["feature_version"],
                        )
                        .values(
                            label_filled_at=u["label_filled_at"],
                            **{col: u[col] for col in lookback_cols.values()},
                        )
                    )
                    # SQLite NULL semantics for run_id: equality on NULL is FALSE.
                    rid = u["run_id"]
                    stmt = (
                        stmt.where(feature_log.c.run_id.is_(None))
                        if rid is None
                        else stmt.where(feature_log.c.run_id == rid)
                    )
                    conn.execute(stmt)
                    labeled += 1
    return labeled
