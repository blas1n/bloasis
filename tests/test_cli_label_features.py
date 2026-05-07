"""Smoke tests for `bloasis label-features` CLI."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import insert, select
from typer.testing import CliRunner

from bloasis.cli import app
from bloasis.storage import create_all, feature_log, get_engine

runner = CliRunner()


@pytest.fixture
def smoke_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "smoke.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(db_path))
    engine = get_engine(db_path)
    create_all(engine)
    return db_path


def _seed(engine: object, symbol: str, ts: datetime) -> None:  # type: ignore[no-untyped-def]
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            insert(feature_log).values(
                timestamp=ts,
                symbol=symbol,
                run_id=1,
                feature_version=2,
                created_at=datetime.now(tz=UTC),
            )
        )


def _write_parquet(parquet_dir: Path, symbol: str, prices: list[float]) -> None:
    parquet_dir.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range("2024-01-01", periods=len(prices), freq="B")
    df = pd.DataFrame({"close": prices}, index=idx)
    df.index.name = "timestamp"
    df.to_parquet(parquet_dir / f"{symbol}_2024-01-01_2024-12-31.parquet", index=True)


def test_label_features_cli_labels_rows(
    smoke_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: parquet cache + seeded feature_log → CLI fills labels."""
    cache_dir = tmp_path / "cache"
    parquet_dir = cache_dir / "parquet" / "ohlcv"
    _write_parquet(parquet_dir, "AAA", [100.0 + i for i in range(120)])

    engine = get_engine(smoke_db)
    _seed(engine, "AAA", datetime(2024, 1, 5, tzinfo=UTC))

    # Use config file pointing cache_dir to tmp_path
    import yaml

    cfg_yaml = {
        "data": {"cache_dir": str(cache_dir)},
    }
    cfg_path = tmp_path / "labeling.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg_yaml))

    result = runner.invoke(app, ["label-features", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "labeled" in result.output

    with engine.connect() as conn:
        row = conn.execute(select(feature_log).where(feature_log.c.symbol == "AAA")).first()
    assert row is not None
    assert row.label_filled_at is not None
    assert row.forward_return_5d is not None


def test_label_features_cli_skips_when_no_parquet(smoke_db: Path, tmp_path: Path) -> None:
    """Symbol with no cached parquet → row stays unlabeled, CLI succeeds."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()  # no parquet/ohlcv inside

    engine = get_engine(smoke_db)
    _seed(engine, "MISSING", datetime(2024, 1, 5, tzinfo=UTC))

    import yaml

    cfg_path = tmp_path / "labeling.yaml"
    cfg_path.write_text(yaml.safe_dump({"data": {"cache_dir": str(cache_dir)}}))

    result = runner.invoke(app, ["label-features", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output

    with engine.connect() as conn:
        row = conn.execute(select(feature_log).where(feature_log.c.symbol == "MISSING")).first()
    assert row is not None
    assert row.label_filled_at is None  # still pending


def test_label_features_cli_idempotent(smoke_db: Path, tmp_path: Path) -> None:
    """Running twice → second pass is a no-op (already-labeled rows skipped)."""
    cache_dir = tmp_path / "cache"
    parquet_dir = cache_dir / "parquet" / "ohlcv"
    _write_parquet(parquet_dir, "BBB", [100.0 + i for i in range(120)])

    engine = get_engine(smoke_db)
    _seed(engine, "BBB", datetime(2024, 1, 5, tzinfo=UTC))

    import yaml

    cfg_path = tmp_path / "labeling.yaml"
    cfg_path.write_text(yaml.safe_dump({"data": {"cache_dir": str(cache_dir)}}))

    r1 = runner.invoke(app, ["label-features", "--config", str(cfg_path)])
    r2 = runner.invoke(app, ["label-features", "--config", str(cfg_path)])
    assert r1.exit_code == 0 and r2.exit_code == 0
    assert "labeled 1" in r1.output
    assert "labeled 0" in r2.output
