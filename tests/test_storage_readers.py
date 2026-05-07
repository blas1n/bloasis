"""Tests for `bloasis.storage.readers` — feature_log → DataFrame."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert

from bloasis.scoring.features import FEATURE_COLUMNS
from bloasis.storage import create_all, feature_log, get_engine
from bloasis.storage.readers import load_labeled_feature_log


def _seed_row(
    engine,  # type: ignore[no-untyped-def]
    *,
    timestamp: datetime,
    symbol: str,
    feature_version: int = 2,
    label_filled: bool = True,
    forward_return_20d: float | None = 0.05,
    per: float | None = 10.0,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            insert(feature_log).values(
                timestamp=timestamp,
                symbol=symbol,
                run_id=1,
                feature_version=feature_version,
                created_at=datetime.now(tz=UTC),
                per=per,
                forward_return_20d=forward_return_20d,
                label_filled_at=datetime.now(tz=UTC) if label_filled else None,
            )
        )


def test_load_returns_only_labeled_rows(tmp_path: Path) -> None:
    """Rows with `label_filled_at IS NULL` excluded; rows with NULL label
    column also excluded (you can't train on missing y)."""
    engine = get_engine(tmp_path / "db")
    create_all(engine)
    # Three rows: 1 fully-labeled, 1 unfilled, 1 filled-but-NULL-label
    _seed_row(
        engine, timestamp=datetime(2024, 1, 5, tzinfo=UTC), symbol="A", forward_return_20d=0.05
    )
    _seed_row(
        engine,
        timestamp=datetime(2024, 1, 6, tzinfo=UTC),
        symbol="B",
        label_filled=False,
        forward_return_20d=None,
    )
    _seed_row(
        engine, timestamp=datetime(2024, 1, 7, tzinfo=UTC), symbol="C", forward_return_20d=None
    )

    df = load_labeled_feature_log(engine, feature_version=2, label_column="forward_return_20d")
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "A"


def test_load_returns_feature_columns_plus_timestamp_label(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "db")
    create_all(engine)
    _seed_row(engine, timestamp=datetime(2024, 1, 5, tzinfo=UTC), symbol="X", per=12.0)
    df = load_labeled_feature_log(engine, feature_version=2, label_column="forward_return_20d")
    # All FEATURE_COLUMNS present + timestamp + label
    for col in FEATURE_COLUMNS:
        assert col in df.columns
    assert "timestamp" in df.columns
    assert "forward_return_20d" in df.columns
    assert df.iloc[0]["per"] == 12.0


def test_load_filters_by_feature_version(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "db")
    create_all(engine)
    _seed_row(engine, timestamp=datetime(2024, 1, 5, tzinfo=UTC), symbol="V1", feature_version=1)
    _seed_row(engine, timestamp=datetime(2024, 1, 6, tzinfo=UTC), symbol="V2", feature_version=2)
    df_v1 = load_labeled_feature_log(engine, feature_version=1, label_column="forward_return_20d")
    df_v2 = load_labeled_feature_log(engine, feature_version=2, label_column="forward_return_20d")
    assert list(df_v1["symbol"]) == ["V1"]
    assert list(df_v2["symbol"]) == ["V2"]


def test_load_invalid_label_column_raises(tmp_path: Path) -> None:
    import pytest

    engine = get_engine(tmp_path / "db")
    create_all(engine)
    with pytest.raises(ValueError, match="label_column"):
        load_labeled_feature_log(engine, feature_version=2, label_column="not_a_column")


def test_load_empty_db_returns_empty_df(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "db")
    create_all(engine)
    df = load_labeled_feature_log(engine, feature_version=2, label_column="forward_return_20d")
    assert df.empty
    # Still has expected columns even when empty (callers can branch on shape).
    assert "timestamp" in df.columns
    assert "forward_return_20d" in df.columns


# ---------------------------------------------------------------------------
# PR17 — date filters for honest train/test split
# ---------------------------------------------------------------------------


def test_load_respects_start_date(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "db")
    create_all(engine)
    _seed_row(engine, timestamp=datetime(2023, 6, 1, tzinfo=UTC), symbol="EARLY")
    _seed_row(engine, timestamp=datetime(2024, 1, 5, tzinfo=UTC), symbol="LATE")

    df = load_labeled_feature_log(
        engine,
        feature_version=2,
        label_column="forward_return_20d",
        start_date=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert list(df["symbol"]) == ["LATE"]


def test_load_respects_end_date(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "db")
    create_all(engine)
    _seed_row(engine, timestamp=datetime(2023, 6, 1, tzinfo=UTC), symbol="EARLY")
    _seed_row(engine, timestamp=datetime(2024, 1, 5, tzinfo=UTC), symbol="LATE")

    df = load_labeled_feature_log(
        engine,
        feature_version=2,
        label_column="forward_return_20d",
        end_date=datetime(2023, 12, 31, tzinfo=UTC),
    )
    assert list(df["symbol"]) == ["EARLY"]


def test_load_respects_both_dates(tmp_path: Path) -> None:
    engine = get_engine(tmp_path / "db")
    create_all(engine)
    _seed_row(engine, timestamp=datetime(2022, 1, 1, tzinfo=UTC), symbol="OLD")
    _seed_row(engine, timestamp=datetime(2023, 6, 1, tzinfo=UTC), symbol="MID")
    _seed_row(engine, timestamp=datetime(2024, 6, 1, tzinfo=UTC), symbol="NEW")

    df = load_labeled_feature_log(
        engine,
        feature_version=2,
        label_column="forward_return_20d",
        start_date=datetime(2023, 1, 1, tzinfo=UTC),
        end_date=datetime(2023, 12, 31, tzinfo=UTC),
    )
    assert list(df["symbol"]) == ["MID"]
