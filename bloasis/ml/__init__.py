"""Machine-learning pipeline.

Phase 2: forward-return labeling (PR13), LightGBM training (PR14),
ML scorer (PR15), SHAP rationale (PR16).

Mission roadmap §Phase 2 — see ~/Docs/bloasis/Phase2_ML_Design_Lockin_2026-05-07.md.
"""

from bloasis.ml.labeling import (
    DEFAULT_LOOKBACKS,
    compute_forward_returns,
    label_unlabeled_features,
)

__all__ = [
    "DEFAULT_LOOKBACKS",
    "compute_forward_returns",
    "label_unlabeled_features",
]
