"""Read-side helpers — typed DataFrame loaders for ML training.

PR14: pulls labeled `feature_log` rows into a `pd.DataFrame` shaped for
the LightGBM trainer. Filters by `feature_version` and label-non-null;
excludes rows where the labeling job couldn't compute the requested
forward horizon.

PR17 adds optional `start_date` / `end_date` so callers can carve a
training window distinct from a held-out test window (avoids
in-sample bias when measuring the ML scorer).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pandas as pd
from sqlalchemy import select

from bloasis.scoring.features import FEATURE_COLUMNS
from bloasis.storage import feature_log

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.engine import Row

VALID_LABEL_COLUMNS = ("forward_return_5d", "forward_return_20d", "forward_return_60d")


def load_labeled_feature_log(
    engine: Engine,
    *,
    feature_version: int,
    label_column: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> pd.DataFrame:
    """Load `feature_log` rows ready for ML training.

    Returns a DataFrame with columns `[timestamp, symbol, *FEATURE_COLUMNS,
    <label_column>]` for every row matching `feature_version`, with
    `label_filled_at IS NOT NULL`, AND `<label_column> IS NOT NULL`.

    `start_date` / `end_date` (inclusive) bound the timestamp window — used
    by PR17 to train on early history and evaluate on later periods.
    """
    if label_column not in VALID_LABEL_COLUMNS:
        raise ValueError(f"label_column must be one of {VALID_LABEL_COLUMNS}, got {label_column!r}")

    cols = [
        feature_log.c.timestamp,
        feature_log.c.symbol,
        *(feature_log.c[name] for name in FEATURE_COLUMNS),
        feature_log.c[label_column],
    ]
    stmt = (
        select(*cols)
        .where(feature_log.c.feature_version == feature_version)
        .where(feature_log.c.label_filled_at.is_not(None))
        .where(feature_log.c[label_column].is_not(None))
        .order_by(feature_log.c.timestamp.asc(), feature_log.c.symbol.asc())
    )
    if start_date is not None:
        stmt = stmt.where(feature_log.c.timestamp >= start_date)
    if end_date is not None:
        stmt = stmt.where(feature_log.c.timestamp <= end_date)
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()

    if not rows:
        # Build empty DataFrame with the expected column shape.
        empty_cols = ["timestamp", "symbol", *FEATURE_COLUMNS, label_column]
        return pd.DataFrame(columns=empty_cols)

    df = pd.DataFrame(rows, columns=["timestamp", "symbol", *FEATURE_COLUMNS, label_column])
    # Coerce numeric features + label to float64 — SQLAlchemy returns Python
    # None for NULL, which leaves all-null columns as object dtype, and
    # LightGBM rejects non-numeric dtypes. `errors="coerce"` turns any odd
    # value into NaN (LightGBM's native missing-value representation).
    for col in (*FEATURE_COLUMNS, label_column):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Mention predictions (PR57)
# ---------------------------------------------------------------------------


def list_unsettled_mention_predictions(engine: Engine, *, as_of: date) -> list[Row[Any]]:
    """Rows where entry_date + horizon_days <= as_of AND settled_at IS NULL.

    Returns SQLAlchemy ``Row`` objects (mapped attribute access). The
    daily settle job iterates these to fill realized_fwd / baseline /
    excess from yfinance OHLCV.
    """
    from bloasis.storage import mention_predictions

    # SQLite-friendly date comparison: entry_date + horizon_days <= as_of_dt.
    # We do the math in Python via two-pass — first fetch unsettled, then
    # filter ripeness — to avoid dialect-specific date arithmetic.
    stmt = (
        select(mention_predictions)
        .where(mention_predictions.c.settled_at.is_(None))
        .order_by(mention_predictions.c.entry_date.asc())
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()
    out: list[Row[Any]] = []
    for r in rows:
        ed: datetime = r.entry_date
        ed_d = ed.date() if isinstance(ed, datetime) else ed
        if ed_d + timedelta(days=r.horizon_days) <= as_of:
            out.append(r)
    return out


def list_untracked_mentions(
    engine: Engine, *, extractor_version: int, horizon_days: int
) -> list[Row[Any]]:
    """Negative + (after_hours | overnight) mentions with NO prediction
    row at (extractor_version, horizon_days) yet. These are the
    candidates for the daily ``mentions-track`` predict pass.

    The bucket filter is done in Python so the timing classifier
    (``mention_timing``) stays the single source of truth — the DB does
    not store the bucket on the mention row.
    """
    from bloasis.analysis.mention_timing import MentionTiming, classify_mention_timing
    from bloasis.storage import mention_predictions, social_post_mentions, social_posts

    # Join mention + post to get posted_at, exclude rows already predicted
    # at this (extractor_version, horizon_days).
    existing = select(
        mention_predictions.c.post_id,
        mention_predictions.c.ticker,
    ).where(
        mention_predictions.c.extractor_version == extractor_version,
        mention_predictions.c.horizon_days == horizon_days,
    )
    stmt = (
        select(
            social_post_mentions.c.post_id,
            social_post_mentions.c.ticker,
            social_post_mentions.c.sentiment,
            social_post_mentions.c.extractor_version,
            social_posts.c.posted_at,
        )
        .select_from(
            social_post_mentions.join(
                social_posts,
                social_post_mentions.c.post_id == social_posts.c.post_id,
            )
        )
        .where(social_post_mentions.c.extractor_version == extractor_version)
        .where(social_post_mentions.c.sentiment == "negative")
    )
    out: list[Row[Any]] = []
    with engine.connect() as conn:
        existing_pairs = {(r.post_id, r.ticker) for r in conn.execute(existing).all()}
        rows = conn.execute(stmt).all()
    out_of_hours = {MentionTiming.AFTER_HOURS, MentionTiming.OVERNIGHT}
    for r in rows:
        if (r.post_id, r.ticker) in existing_pairs:
            continue
        if classify_mention_timing(r.posted_at) in out_of_hours:
            out.append(r)
    return out
