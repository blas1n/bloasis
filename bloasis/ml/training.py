"""LightGBM walk-forward training pipeline (PR14).

Loads (X, y, timestamps), runs purged walk-forward CV via
`bloasis.ml.cv.purged_walk_forward_splits`, computes per-fold IC
(Spearman-style: pearson on numerical predictions vs labels), then
refits the final model on all training data.

Mission Phase 2 §PR14 — see ~/Docs/bloasis/Phase2_ML_Design_Lockin_2026-05-07.md.
"""

from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from bloasis.ml.cv import purged_walk_forward_splits

if TYPE_CHECKING:
    import pandas as pd

# Default LightGBM params (Phase 2 design §PR14):
# minimal hyperparam tuning until PR17 measurement informs whether ML
# beats rule scorer. Aggressive tuning is the LAST step, not the first.
DEFAULT_LGBM_PARAMS: dict[str, Any] = {
    "objective": "regression",
    "metric": "rmse",
    "max_depth": 6,
    "num_leaves": 31,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "min_data_in_leaf": 20,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "verbose": -1,
}

EARLY_STOPPING_ROUNDS = 50


@dataclass(frozen=True, slots=True)
class TrainingResult:
    """Output of `train_walk_forward`."""

    fold_ics: list[float]
    mean_ic: float
    feature_names: list[str]
    feature_importance: dict[str, float]
    n_train_rows: int
    n_test_rows_total: int
    params: dict[str, Any]
    model: Any  # LightGBM Booster (refit on all train data)
    metadata: dict[str, Any] = field(default_factory=dict)


def information_coefficient(predictions: np.ndarray, labels: np.ndarray) -> float:
    """Pearson correlation between predictions and labels.

    Returns NaN when either array has zero variance (no signal can be
    detected, ill-defined). For ML factor models the IC is the canonical
    out-of-fold quality metric — rule of thumb: IC > 0.05 is a real
    signal, IC > 0.1 is excellent (Kelly-Pruitt-Su 2020 citing AQR).
    """
    p = np.asarray(predictions, dtype=np.float64).ravel()
    label = np.asarray(labels, dtype=np.float64).ravel()
    if p.size != label.size or p.size < 2:
        return float("nan")
    mask = np.isfinite(p) & np.isfinite(label)
    if int(mask.sum()) < 2:
        return float("nan")
    p, label = p[mask], label[mask]
    if float(np.std(p, ddof=1)) == 0 or float(np.std(label, ddof=1)) == 0:
        return float("nan")
    coef = float(np.corrcoef(p, label)[0, 1])
    if math.isnan(coef):
        return float("nan")
    return coef


def train_walk_forward(
    X: pd.DataFrame,
    y: pd.Series,
    timestamps: pd.Series,
    *,
    n_folds: int = 5,
    embargo_days: int = 21,
    params: dict[str, Any] | None = None,
) -> TrainingResult:
    """Train LightGBM via purged walk-forward CV.

    `X`, `y`, `timestamps` must have aligned length. The function sorts
    by timestamp internally — caller doesn't need to pre-sort, but every
    row must have a valid timestamp.

    Per-fold workflow:
      1. Train on `[: train_end - embargo_days]`.
      2. Predict on `[test_start : test_end]`.
      3. Compute IC = corr(predictions, labels).
    Final model is refit on ALL training data (no holdout). Use it for
    inference; use `fold_ics` for honest performance estimates.

    Raises `ValueError` for too-few-samples or invalid params.
    """
    import lightgbm as lgb

    if len(X) != len(y) or len(X) != len(timestamps):
        raise ValueError(f"length mismatch: X={len(X)} y={len(y)} ts={len(timestamps)}")
    if len(X) < (n_folds + 1) * 5:
        raise ValueError(
            f"too few samples ({len(X)}) for {n_folds} folds (need ≥ {(n_folds + 1) * 5})"
        )

    # Sort by timestamp.
    order = np.argsort(timestamps.to_numpy(), kind="stable")
    X_sorted = X.iloc[order].reset_index(drop=True)
    y_sorted = y.iloc[order].reset_index(drop=True)
    ts_sorted = timestamps.iloc[order].reset_index(drop=True).to_numpy()

    used_params = dict(params) if params is not None else dict(DEFAULT_LGBM_PARAMS)

    fold_ics: list[float] = []
    n_test_total = 0
    feature_names = list(X_sorted.columns)
    n_estimators = int(used_params.pop("n_estimators", 500))

    for tr_idx, te_idx in purged_walk_forward_splits(
        ts_sorted, n_folds=n_folds, embargo_days=embargo_days
    ):
        # Carve out a small validation slice from the tail of train for
        # early stopping (deterministic — last 10%).
        n_tr = int(tr_idx.size)
        n_val = max(20, n_tr // 10)
        if n_val >= n_tr:
            continue
        val_slice = tr_idx[-n_val:]
        train_slice = tr_idx[:-n_val]
        if train_slice.size < 20:
            continue

        train_set = lgb.Dataset(X_sorted.iloc[train_slice], label=y_sorted.iloc[train_slice])
        val_set = lgb.Dataset(
            X_sorted.iloc[val_slice], label=y_sorted.iloc[val_slice], reference=train_set
        )

        booster = lgb.train(
            used_params,
            train_set,
            num_boost_round=n_estimators,
            valid_sets=[val_set],
            callbacks=[
                lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                lgb.log_evaluation(0),
            ],
        )
        preds = booster.predict(X_sorted.iloc[te_idx])
        labels = y_sorted.iloc[te_idx].to_numpy()
        fold_ics.append(information_coefficient(np.asarray(preds), labels))
        n_test_total += int(te_idx.size)

    if not fold_ics:
        raise ValueError("no folds produced — check n_folds / embargo_days vs data size")

    mean_ic = float(np.nanmean(fold_ics))

    # Final refit on all in-sample data (no holdout for production model).
    final_train = lgb.Dataset(X_sorted, label=y_sorted)
    final_model = lgb.train(
        used_params,
        final_train,
        num_boost_round=n_estimators,
        callbacks=[lgb.log_evaluation(0)],
    )

    importance = final_model.feature_importance(importance_type="gain")
    feature_importance = {
        name: float(score) for name, score in zip(feature_names, importance, strict=True)
    }

    used_params_full = dict(used_params)
    used_params_full["n_estimators"] = n_estimators
    return TrainingResult(
        fold_ics=fold_ics,
        mean_ic=mean_ic,
        feature_names=feature_names,
        feature_importance=feature_importance,
        n_train_rows=int(len(X_sorted)),
        n_test_rows_total=n_test_total,
        params=used_params_full,
        model=final_model,
    )


def save_model(
    result: TrainingResult,
    path: Path,
    *,
    feature_version: int,
    label_name: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Pickle the LightGBM model + write a JSON sidecar with metadata.

    Metadata includes feature_version (filter for ML training data
    integrity), label_name (which forward-return horizon was learned),
    fold_ics, mean_ic, feature_importance, and any caller-supplied
    `extra` mapping.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(result.model, f)
    sidecar = path.with_suffix(".json")
    metadata = {
        "feature_version": feature_version,
        "label_name": label_name,
        "fold_ics": [float(ic) for ic in result.fold_ics],
        "mean_ic": float(result.mean_ic),
        "feature_names": result.feature_names,
        "feature_importance": result.feature_importance,
        "n_train_rows": result.n_train_rows,
        "n_test_rows_total": result.n_test_rows_total,
        "params": result.params,
        "extra": extra or {},
    }
    sidecar.write_text(json.dumps(metadata, indent=2))


def load_model(path: Path) -> Any:
    """Load the pickled LightGBM Booster (predict-ready)."""
    with path.open("rb") as f:
        return pickle.load(f)
