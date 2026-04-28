"""Tests for `bloasis.backtest.walk_forward`."""

from __future__ import annotations

from datetime import date

import pytest

from bloasis.backtest.walk_forward import generate_folds


def test_generate_folds_yields_expected_count() -> None:
    folds = list(
        generate_folds(
            start=date(2020, 1, 1),
            end=date(2025, 1, 1),
            train_days=365 * 3,
            test_days=180,
            step_days=180,
        )
    )
    # 5 years total, 3y train + 6mo test = 3.5y minimum, step 6mo
    # First fold ends 2023-06-30 (3y train + 6mo test). Subsequent advance by 6mo.
    assert len(folds) >= 3
    for f in folds:
        assert f.train_start < f.train_end < f.test_start <= f.test_end


def test_generate_folds_train_test_no_overlap() -> None:
    folds = list(
        generate_folds(
            start=date(2020, 1, 1),
            end=date(2024, 1, 1),
            train_days=365 * 2,
            test_days=180,
            step_days=180,
        )
    )
    for f in folds:
        assert f.test_start > f.train_end


def test_generate_folds_advances_by_step() -> None:
    folds = list(
        generate_folds(
            start=date(2020, 1, 1),
            end=date(2024, 1, 1),
            train_days=365 * 2,
            test_days=180,
            step_days=180,
        )
    )
    if len(folds) < 2:
        pytest.skip("not enough folds for this assertion")
    delta = (folds[1].train_start - folds[0].train_start).days
    assert delta == 180


def test_generate_folds_short_period_yields_single_fold() -> None:
    """If period < train + test, return a degenerate single fold (70/30)."""
    folds = list(
        generate_folds(
            start=date(2024, 1, 1),
            end=date(2024, 6, 1),
            train_days=365 * 3,
            test_days=180,
        )
    )
    assert len(folds) == 1
    assert folds[0].train_start == date(2024, 1, 1)
    assert folds[0].test_end == date(2024, 6, 1)


def test_generate_folds_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        list(generate_folds(date(2024, 1, 1), date(2024, 1, 1)))
    with pytest.raises(ValueError):
        list(generate_folds(date(2024, 1, 1), date(2024, 6, 1), train_days=0))
