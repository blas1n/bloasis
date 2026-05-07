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

from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
from sqlalchemy import select

from bloasis.scoring.features import FEATURE_COLUMNS
from bloasis.storage import feature_log

if TYPE_CHECKING:
    from sqlalchemy import Engine

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
