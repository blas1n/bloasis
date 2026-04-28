"""Walk-forward window iterator.

Given (start, end, train_window, test_window, step), yield successive
(train_start, train_end, test_start, test_end) tuples that cover the full
backtest period.

The whole point of walk-forward (vs. full-history backtest) is that each
test window is OOS relative to the train window that "trains" the scorer
on it. For Phase 1 (RuleBasedScorer with fixed weights) the train slice
is informational — but the iterator is wired up now so Phase 3 ML drops
in without engine surgery.

Default policy: 3y train, 6mo test, 6mo step. A 5-year backtest yields
~4 folds. Smaller `step` increases overlap (more folds, less independence).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

DEFAULT_TRAIN_DAYS = 365 * 3
DEFAULT_TEST_DAYS = 180
DEFAULT_STEP_DAYS = 180


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    fold_index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date


def generate_folds(
    start: date,
    end: date,
    train_days: int = DEFAULT_TRAIN_DAYS,
    test_days: int = DEFAULT_TEST_DAYS,
    step_days: int = DEFAULT_STEP_DAYS,
) -> Iterator[WalkForwardWindow]:
    """Yield successive walk-forward windows covering [start, end].

    The first fold's `train_start` is `start`. Subsequent folds advance
    `train_start` by `step_days`. We stop when the next fold's `test_end`
    would exceed `end`.

    If the requested period is shorter than `train_days + test_days`,
    yield a single degenerate fold using whatever data is available.
    """
    if train_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("train_days/test_days/step_days must be positive")
    if start >= end:
        raise ValueError(f"start ({start}) must be < end ({end})")

    total_days = (end - start).days
    if total_days < train_days + test_days:
        # Degenerate — give back the whole period split 70/30.
        train_end = start + timedelta(days=int(total_days * 0.7))
        yield WalkForwardWindow(
            fold_index=0,
            train_start=start,
            train_end=train_end,
            test_start=train_end + timedelta(days=1),
            test_end=end,
        )
        return

    fold = 0
    cursor_train_start = start
    while True:
        train_end = cursor_train_start + timedelta(days=train_days)
        test_start = train_end + timedelta(days=1)
        test_end = test_start + timedelta(days=test_days - 1)
        if test_end > end:
            break
        yield WalkForwardWindow(
            fold_index=fold,
            train_start=cursor_train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        )
        fold += 1
        cursor_train_start = cursor_train_start + timedelta(days=step_days)
