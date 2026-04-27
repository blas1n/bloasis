"""Smoke tests for the CLI commands implemented in PR1."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from bloasis.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "bloasis" in result.output


def test_init_db_creates_file(tmp_path: Path) -> None:
    db_path = tmp_path / "out.db"
    result = runner.invoke(app, ["init-db", "--db-path", str(db_path)])
    assert result.exit_code == 0, result.output
    assert db_path.exists()
    assert "database initialized" in result.output


def test_init_db_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "out.db"
    r1 = runner.invoke(app, ["init-db", "--db-path", str(db_path)])
    r2 = runner.invoke(app, ["init-db", "--db-path", str(db_path)])
    assert r1.exit_code == 0
    assert r2.exit_code == 0


def test_config_show_baseline(baseline_config_path: Path) -> None:
    result = runner.invoke(app, ["config", "show", str(baseline_config_path)])
    assert result.exit_code == 0, result.output
    assert "config_hash" in result.output
    assert "sp500" in result.output


def test_config_show_with_override(baseline_config_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "config",
            "show",
            str(baseline_config_path),
            "--set",
            "scorer.weights.momentum=0.30",
        ],
    )
    assert result.exit_code == 0, result.output


def test_config_show_invalid_override_returns_nonzero(
    baseline_config_path: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "config",
            "show",
            str(baseline_config_path),
            "--set",
            "scorer.exit_threshold=0.99",
        ],
    )
    assert result.exit_code != 0


def test_config_show_missing_file_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["config", "show", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0
