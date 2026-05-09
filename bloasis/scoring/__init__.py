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
from bloasis.scoring.rationale import FactorContribution, Rationale, ScoredCandidate
from bloasis.scoring.regime import classify_regime
from bloasis.scoring.scorer import (
    EDGARTextDiffScorer,
    FundamentalLLMScorer,
    IntersectScorer,
    JTMomentumScorer,
    LightGBMScorer,
    PEADScorer,
    RuleBasedScorer,
    Scorer,
)

__all__ = [
    "FEATURE_COLUMNS",
    "CompositeBuilder",
    "CompositeVector",
    "EDGARTextDiffScorer",
    "ExtractionContext",
    "FactorContribution",
    "FeatureExtractor",
    "FeatureVector",
    "FundamentalLLMScorer",
    "IntersectScorer",
    "JTMomentumScorer",
    "LightGBMScorer",
    "PEADScorer",
    "Rationale",
    "RuleBasedScorer",
    "ScoredCandidate",
    "Scorer",
    "classify_regime",
]
