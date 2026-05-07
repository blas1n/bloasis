"""Smoke tests for `bloasis ml train` CLI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import insert
from typer.testing import CliRunner

from bloasis.cli import app
from bloasis.scoring.features import FEATURE_COLUMNS
from bloasis.storage import create_all, feature_log, get_engine

runner = CliRunner()


@pytest.fixture
def smoke_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "smoke.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(db_path))
    engine = get_engine(db_path)
    create_all(engine)
    return db_path


def _seed_synthetic_feature_log(engine, n: int = 400, seed: int = 42) -> None:  # type: ignore[no-untyped-def]
    """Seed `n` rows with linear signal in `per`, label_20d = signal + noise."""
    rng = np.random.default_rng(seed)
    base = datetime(2023, 1, 1, tzinfo=UTC)
    feature_values = {col: rng.standard_normal(n) for col in FEATURE_COLUMNS}
    label = 0.5 * feature_values["per"] + rng.standard_normal(n) * 0.5
    rows = []
    for i in range(n):
        row: dict[str, object] = {
            "timestamp": base + timedelta(days=i),
            "symbol": f"S{i % 10}",
            "run_id": 1,
            "feature_version": 2,
            "created_at": datetime.now(tz=UTC),
            "label_filled_at": datetime.now(tz=UTC),
            "forward_return_20d": float(label[i]),
        }
        for col in FEATURE_COLUMNS:
            row[col] = float(feature_values[col][i])
        rows.append(row)
    with engine.begin() as conn:
        conn.execute(insert(feature_log), rows)


def test_ml_train_cli_loads_data_and_saves_model(smoke_db: Path, tmp_path: Path) -> None:
    """Full path: synthetic feature_log → CLI → model.pkl + sidecar.json."""
    engine = get_engine(smoke_db)
    _seed_synthetic_feature_log(engine, n=300)

    output = tmp_path / "models" / "test_model.pkl"
    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--feature-version",
            "2",
            "--label",
            "forward_return_20d",
            "--n-folds",
            "3",
            "--embargo-days",
            "5",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "mean IC" in result.output
    assert output.exists()
    assert output.with_suffix(".json").exists()


def test_ml_train_cli_errors_when_no_data(smoke_db: Path, tmp_path: Path) -> None:
    """Empty feature_log → CLI exits with helpful error."""
    output = tmp_path / "model.pkl"
    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--feature-version",
            "2",
            "--label",
            "forward_return_20d",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code != 0
    assert "no labeled rows" in result.output.lower() or "no data" in result.output.lower()


def test_ml_train_cli_invalid_label_column_rejected(smoke_db: Path, tmp_path: Path) -> None:
    output = tmp_path / "model.pkl"
    result = runner.invoke(
        app,
        [
            "ml",
            "train",
            "--feature-version",
            "2",
            "--label",
            "not_a_column",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code != 0
