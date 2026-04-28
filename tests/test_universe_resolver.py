"""Tests for backtest.universe_resolver — monthly S&P 500 rebalance map."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from bloasis.backtest import universe_resolver as uv


def _patch_list(monkeypatch: pytest.MonkeyPatch, mapping: dict[date, list[str]]) -> list[date]:
    """Replace `list_sp500_at` with an in-memory lookup; record call dates."""
    called: list[date] = []

    def fake(d: date, *, cache_dir: Path) -> list[str]:
        called.append(d)
        if d not in mapping:
            raise ValueError(f"date {d} predates dataset")
        return list(mapping[d])

    monkeypatch.setattr(uv, "list_sp500_at", fake)
    return called


def test_build_monthly_universe_one_entry_per_month(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Three months: Jan, Feb, Mar 2024.
    mapping: dict[date, list[str]] = {
        date(2024, 1, 1): ["AAPL", "MSFT"],
        date(2024, 2, 1): ["AAPL", "MSFT", "NVDA"],
        date(2024, 3, 1): ["AAPL", "NVDA"],
    }
    _patch_list(monkeypatch, mapping)

    out = uv.build_monthly_universe(date(2024, 1, 15), date(2024, 3, 20), cache_dir=tmp_path)
    # Keys are first-of-month for each month touched, including Jan even
    # though `start` was mid-month.
    assert sorted(out.keys()) == [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)]
    assert out[date(2024, 1, 1)] == ["AAPL", "MSFT"]
    assert out[date(2024, 2, 1)] == ["AAPL", "MSFT", "NVDA"]
    assert out[date(2024, 3, 1)] == ["AAPL", "NVDA"]


def test_skip_dates_predating_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Only Feb is in the dataset; Jan should be skipped without raising.
    mapping = {date(2024, 2, 1): ["X"]}
    _patch_list(monkeypatch, mapping)

    out = uv.build_monthly_universe(date(2024, 1, 1), date(2024, 2, 5), cache_dir=tmp_path)
    assert list(out.keys()) == [date(2024, 2, 1)]


def test_year_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mapping = {
        date(2023, 12, 1): ["A"],
        date(2024, 1, 1): ["B"],
    }
    _patch_list(monkeypatch, mapping)
    out = uv.build_monthly_universe(date(2023, 12, 15), date(2024, 1, 10), cache_dir=tmp_path)
    assert sorted(out.keys()) == [date(2023, 12, 1), date(2024, 1, 1)]
    assert out[date(2024, 1, 1)] == ["B"]


def test_start_must_be_before_end(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="start"):
        uv.build_monthly_universe(date(2024, 1, 5), date(2024, 1, 5), cache_dir=tmp_path)


def test_latest_membership_picks_most_recent_le() -> None:
    universe_map = {
        date(2024, 1, 1): ["A"],
        date(2024, 2, 1): ["A", "B"],
        date(2024, 3, 1): ["B"],
    }
    assert uv.latest_membership_at(universe_map, date(2024, 2, 15)) == ["A", "B"]
    assert uv.latest_membership_at(universe_map, date(2024, 3, 1)) == ["B"]


def test_latest_membership_returns_empty_when_no_eligible() -> None:
    universe_map = {date(2024, 5, 1): ["X"]}
    assert uv.latest_membership_at(universe_map, date(2024, 4, 30)) == []


def test_next_month_first_year_rollover() -> None:
    assert uv._next_month_first(date(2024, 12, 1)) == date(2025, 1, 1)
    assert uv._next_month_first(date(2024, 6, 15)) == date(2024, 7, 1)


def test_build_uses_cache_dir_passed_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[Path] = []

    def fake(d: date, *, cache_dir: Path) -> list[str]:
        captured.append(cache_dir)
        return ["X"]

    monkeypatch.setattr(uv, "list_sp500_at", fake)
    custom = tmp_path / "custom-cache"
    uv.build_monthly_universe(date(2024, 1, 1), date(2024, 1, 15), cache_dir=custom)
    assert captured  # at least one call
    assert all(c == custom for c in captured)


def test_unexpected_exception_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(d: date, *, cache_dir: Path) -> Any:
        raise RuntimeError("network down")

    monkeypatch.setattr(uv, "list_sp500_at", fake)
    with pytest.raises(RuntimeError, match="network down"):
        uv.build_monthly_universe(date(2024, 1, 1), date(2024, 2, 1), cache_dir=tmp_path)
