"""Tests for `bloasis.signal` — SignalGenerator + TradingSignal."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bloasis.config import ScorerConfig, SignalConfig
from bloasis.config.schema import ProfitTier as ProfitTierConfig
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.rationale import Rationale, ScoredCandidate
from bloasis.signal import (
    CandidateData,
    HeldPosition,
    SignalGenerator,
)

NOW = datetime.now(tz=UTC)


def _scored(symbol: str, score: float) -> ScoredCandidate:
    return ScoredCandidate(
        symbol=symbol,
        timestamp=NOW,
        score=score,
        rationale=Rationale(contributions=()),
    )


def _candidate(
    symbol: str,
    score: float,
    *,
    last_close: float = 100.0,
    atr: float = 2.0,
    sector: str | None = None,
) -> CandidateData:
    fv = FeatureVector(
        timestamp=NOW,
        symbol=symbol,
        feature_version=1,
        atr_14=atr,
    )
    return CandidateData(
        scored=_scored(symbol, score),
        feature_vector=fv,
        last_close=last_close,
        sector=sector,
    )


def _signal_cfg(**overrides: object) -> SignalConfig:
    base = dict(
        atr_stop_multiplier=2.0,
        atr_tp_multiplier=3.0,
        position_size_max_pct=0.10,
        profit_tiers=[
            ProfitTierConfig(fraction=0.5, type="target", atr_mult=1.5),
            ProfitTierConfig(fraction=0.5, type="trailing", atr_mult=2.0),
        ],
    )
    base.update(overrides)
    return SignalConfig(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# entries
# ---------------------------------------------------------------------------


def test_entry_signal_when_score_above_threshold() -> None:
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg())
    sigs = sgen.generate([_candidate("AAPL", 0.80)], held=())
    assert len(sigs) == 1
    assert sigs[0].action == "BUY"
    assert sigs[0].symbol == "AAPL"
    assert sigs[0].confidence == 0.80


def test_no_entry_when_score_below_entry_threshold() -> None:
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg())
    sigs = sgen.generate([_candidate("X", 0.50)], held=())
    assert sigs == []


def test_entry_size_scales_with_score() -> None:
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg(position_size_max_pct=0.10))
    low = sgen.generate([_candidate("L", 0.66)], held=())[0].target_size_pct
    high = sgen.generate([_candidate("H", 0.99)], held=())[0].target_size_pct
    assert high > low
    assert high <= 0.10  # capped at max


def test_entry_atr_based_stop_take() -> None:
    sgen = SignalGenerator(
        ScorerConfig(),
        _signal_cfg(atr_stop_multiplier=2.0, atr_tp_multiplier=3.0),
    )
    sig = sgen.generate([_candidate("X", 0.80, last_close=100.0, atr=1.0)], held=())[0]
    assert sig.stop_loss == pytest.approx(100.0 - 2.0)
    assert sig.take_profit == pytest.approx(100.0 + 3.0)


def test_entry_fallback_pct_when_atr_nan() -> None:
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg())
    sig = sgen.generate([_candidate("X", 0.80, last_close=100.0, atr=float("nan"))], held=())[0]
    # Falls back to small fixed % so SL/TP are still set.
    assert sig.stop_loss is not None
    assert sig.take_profit is not None
    assert sig.stop_loss < 100.0 < sig.take_profit


def test_entry_includes_profit_tiers() -> None:
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg())
    sig = sgen.generate([_candidate("X", 0.80)], held=())[0]
    assert len(sig.profit_tiers) == 2


def test_entry_passes_through_sector() -> None:
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg())
    sig = sgen.generate([_candidate("X", 0.80, sector="Technology")], held=())[0]
    assert sig.sector == "Technology"


# ---------------------------------------------------------------------------
# exits
# ---------------------------------------------------------------------------


def test_held_below_exit_threshold_emits_sell() -> None:
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg())
    held = [HeldPosition(symbol="OWNED", quantity=10, avg_cost=100)]
    sigs = sgen.generate([_candidate("OWNED", 0.30)], held=held)
    assert len(sigs) == 1
    assert sigs[0].action == "SELL"


def test_held_above_exit_threshold_no_sell_no_buy() -> None:
    """Score above exit but pyramiding-disabled means: no entry, no exit."""
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg())
    held = [HeldPosition(symbol="HELD", quantity=10, avg_cost=100)]
    sigs = sgen.generate([_candidate("HELD", 0.80)], held=held)
    assert sigs == []


def test_held_with_no_current_score_emits_sell() -> None:
    """Held symbol absent from scored list (delisted/filtered) → SELL."""
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg())
    held = [HeldPosition(symbol="DELISTED")]
    sigs = sgen.generate([], held=held)
    assert len(sigs) == 1
    assert sigs[0].action == "SELL"
    assert "no current score" in sigs[0].reason


def test_no_pyramiding_for_held_symbols() -> None:
    """Even with high score, never emit BUY for symbols already held."""
    sgen = SignalGenerator(ScorerConfig(), _signal_cfg())
    held = [HeldPosition(symbol="HELD")]
    sigs = sgen.generate([_candidate("HELD", 0.95), _candidate("NEW", 0.95)], held=held)
    actions = {s.symbol: s.action for s in sigs}
    assert "HELD" not in actions  # no BUY
    assert actions.get("NEW") == "BUY"


# ---------------------------------------------------------------------------
# size minimum
# ---------------------------------------------------------------------------


def test_entry_size_has_minimum_floor() -> None:
    """Even tiny scores must produce at least the minimum DB-friendly size."""
    cfg = ScorerConfig(entry_threshold=0.01, exit_threshold=0.005)
    sgen = SignalGenerator(cfg, _signal_cfg(position_size_max_pct=0.001))
    sig = sgen.generate([_candidate("X", 0.011)], held=())[0]
    assert sig.target_size_pct >= 0.0001
