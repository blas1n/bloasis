"""Feature engineering and scoring layer.

Pipeline:
    raw OHLCV + fundamentals + market context + sentiment
    -> FeatureExtractor.extract(ExtractionContext) -> FeatureVector  (per symbol)
    -> CompositeBuilder.build(list[FeatureVector]) -> list[CompositeVector]
       (cross-section z-score)

`bloasis/scoring/` has no I/O — it's pure compute. Same code path runs in
live and backtest (see `docs/limitations.md` L007).
"""

from bloasis.scoring.composites import CompositeBuilder, CompositeVector
from bloasis.scoring.extractor import ExtractionContext, FeatureExtractor
from bloasis.scoring.features import FEATURE_COLUMNS, FeatureVector
from bloasis.scoring.regime import classify_regime

__all__ = [
    "FEATURE_COLUMNS",
    "CompositeBuilder",
    "CompositeVector",
    "ExtractionContext",
    "FeatureExtractor",
    "FeatureVector",
    "classify_regime",
]
