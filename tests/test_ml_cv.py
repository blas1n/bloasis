"""Tests for `bloasis.ml.cv` — purged walk-forward CV splitter.

Implements a simplified Lopez de Prado purged walk-forward split: data
is sorted chronologically, divided into (n_folds + 1) blocks, and each
fold trains on `[block 0 .. block k]` (with the last `embargo_days`
rows of training removed) and tests on `block k+1`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bloasis.ml.cv import purged_walk_forward_splits


def _ts_range(n: int, start: str = "2023-01-01") -> np.ndarray:
    """`n` business-day timestamps starting at `start`, sorted."""
    return pd.bdate_range(start, periods=n, freq="B").to_numpy()


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------


def test_yields_n_folds_pairs() -> None:
    """`n_folds=5` → 5 (train, test) pairs."""
    ts = _ts_range(60)
    splits = list(purged_walk_forward_splits(ts, n_folds=5, embargo_days=0))
    assert len(splits) == 5
    for tr, te in splits:
        assert isinstance(tr, np.ndarray)
        assert isinstance(te, np.ndarray)
        assert tr.size > 0
        assert te.size > 0


def test_test_blocks_are_disjoint() -> None:
    """No timestamp index appears in two test sets."""
    ts = _ts_range(60)
    seen: set[int] = set()
    for _tr, te in purged_walk_forward_splits(ts, n_folds=5, embargo_days=0):
        for i in te:
            assert i not in seen, f"index {i} appears in two test folds"
            seen.add(int(i))


def test_test_blocks_are_chronologically_ordered() -> None:
    """Each fold's test block ends before next fold's begins."""
    ts = _ts_range(60)
    prev_max = -1
    for _tr, te in purged_walk_forward_splits(ts, n_folds=5, embargo_days=0):
        cur_min = int(te.min())
        cur_max = int(te.max())
        assert cur_min > prev_max
        prev_max = cur_max


def test_train_strictly_before_test() -> None:
    """Train indices are all < test indices for that fold."""
    ts = _ts_range(60)
    for tr, te in purged_walk_forward_splits(ts, n_folds=5, embargo_days=0):
        assert int(tr.max()) < int(te.min())


# ---------------------------------------------------------------------------
# Embargo (purging)
# ---------------------------------------------------------------------------


def test_embargo_creates_gap_between_train_and_test() -> None:
    """`embargo_days=10` → at least 10 timestamps' gap between train_end
    and test_start. Avoids label leakage (label_20d looks 20d forward)."""
    ts = _ts_range(120)
    embargo = 10
    for tr, te in purged_walk_forward_splits(ts, n_folds=5, embargo_days=embargo):
        gap = int(te.min()) - int(tr.max()) - 1
        assert gap >= embargo, f"gap {gap} < embargo {embargo}"


def test_zero_embargo_no_gap() -> None:
    ts = _ts_range(60)
    for tr, te in purged_walk_forward_splits(ts, n_folds=5, embargo_days=0):
        # train_end + 1 == test_start (consecutive)
        assert int(te.min()) - int(tr.max()) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_growing_train_window() -> None:
    """Each subsequent fold's train set is larger than the previous."""
    ts = _ts_range(120)
    sizes = [tr.size for tr, _ in purged_walk_forward_splits(ts, n_folds=5, embargo_days=0)]
    assert sizes == sorted(sizes)
    assert sizes[-1] > sizes[0]


def test_negative_embargo_raises() -> None:
    ts = _ts_range(30)
    with pytest.raises(ValueError, match="embargo"):
        list(purged_walk_forward_splits(ts, n_folds=5, embargo_days=-1))


def test_n_folds_one_raises() -> None:
    """n_folds < 2 doesn't make sense for walk-forward CV."""
    ts = _ts_range(30)
    with pytest.raises(ValueError, match="n_folds"):
        list(purged_walk_forward_splits(ts, n_folds=1, embargo_days=0))


def test_too_few_samples_for_folds_raises() -> None:
    """Need at least `n_folds + 1` samples to construct (n_folds+1) blocks."""
    ts = _ts_range(3)
    with pytest.raises(ValueError, match="too few"):
        list(purged_walk_forward_splits(ts, n_folds=5, embargo_days=0))


def test_embargo_eats_all_train_skips_fold() -> None:
    """If embargo eats the entire train window for a fold, that fold is
    skipped (yields nothing for it). The function should not crash."""
    ts = _ts_range(20)
    # 4 folds × 5-row blocks. Embargo=10 wipes early train.
    splits = list(purged_walk_forward_splits(ts, n_folds=4, embargo_days=10))
    # First fold has block-0 train (5 rows) → embargo 10 leaves 0 → skipped.
    # Later folds may have enough train to survive.
    for tr, _te in splits:
        assert tr.size > 0  # any yielded fold must have non-empty train
