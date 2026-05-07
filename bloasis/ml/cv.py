"""Purged walk-forward cross-validation splitter.

Simplified Lopez de Prado purged walk-forward (`Advances in Financial
Machine Learning` Ch. 7). The data is sorted chronologically and divided
into `(n_folds + 1)` contiguous blocks. Fold `k` (0-indexed) trains on
blocks 0..k and tests on block k+1. The `embargo_days` last rows of each
fold's training set are dropped to avoid label leakage when the label
looks forward (e.g. `label_20d` requires embargo ≥ 20).

For a true purge we'd also drop training samples whose label intervals
overlap the test set's timestamps. With contiguous blocks + embargo this
collapses to "remove the last `embargo` rows of train" — equivalent
under the assumption that label horizons are uniform.

This is PR14 (development-grade). PR17 will introduce full CPCV with
multiple paths and combinatorial blocks.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np


def purged_walk_forward_splits(
    timestamps: np.ndarray,
    *,
    n_folds: int = 5,
    embargo_days: int = 21,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield `(train_idx, test_idx)` arrays for `n_folds` folds.

    Indices are positions into the sorted-by-time `timestamps` array
    (caller is responsible for the sort). Each `train_idx` is strictly
    less than the corresponding `test_idx.min()` by at least `embargo_days`.

    Folds whose training window is fully consumed by the embargo are
    silently skipped (early-block + large-embargo cases).
    """
    if n_folds < 2:
        raise ValueError(f"n_folds must be >= 2, got {n_folds}")
    if embargo_days < 0:
        raise ValueError(f"embargo_days must be >= 0, got {embargo_days}")

    n = len(timestamps)
    if n < n_folds + 1:
        raise ValueError(f"too few samples ({n}) for n_folds={n_folds} (need at least n_folds + 1)")

    # Block boundaries: split into n_folds + 1 chronological chunks.
    block_size = n // (n_folds + 1)
    block_edges = [i * block_size for i in range(n_folds + 1)] + [n]

    for k in range(n_folds):
        train_end_excl = block_edges[k + 1]
        test_start = block_edges[k + 1]
        test_end_excl = block_edges[k + 2]
        # Apply embargo: drop the last `embargo_days` rows of train.
        train_end_with_embargo = max(0, train_end_excl - embargo_days)
        if train_end_with_embargo == 0:
            continue  # embargo wiped the entire train window for this fold
        train_idx = np.arange(0, train_end_with_embargo, dtype=np.int64)
        test_idx = np.arange(test_start, test_end_excl, dtype=np.int64)
        if test_idx.size == 0:
            continue
        yield train_idx, test_idx
