"""Signal generation — `ScoredCandidate + state` -> `TradingSignal`.

Pure compute. The signal generator decides BUY/SELL/HOLD based on
`scorer.entry_threshold` and `scorer.exit_threshold`; ATR sizing and
SL/TP placement come from `signal:` config section.

Pyramiding is intentionally not supported in v1 — symbols already in the
portfolio receive at most an exit signal. This keeps position state
deterministic during PR5 backtests.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from bloasis.config import ScorerConfig, SignalConfig
from bloasis.scoring.features import FeatureVector
from bloasis.scoring.rationale import Rationale, ScoredCandidate

SignalAction = Literal["BUY", "SELL", "HOLD"]
ProfitTierType = Literal["target", "trailing"]

# Fallback fractional levels when ATR is NaN — small absolute %s by risk
# bucket. These mirror the cautious behavior of the legacy code path.
_FALLBACK_SL_PCT = 0.02
_FALLBACK_TP_PCT = 0.05


@dataclass(frozen=True, slots=True)
class ProfitTier:
    fraction: float
    type: ProfitTierType
    atr_mult: float


@dataclass(frozen=True, slots=True)
class TradingSignal:
    timestamp: datetime
    symbol: str
    action: SignalAction
    confidence: float

    # Sizing target as fraction of strategy capital (risk evaluator may shrink).
    target_size_pct: float

    # Entry levels — populated only for BUY.
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    profit_tiers: tuple[ProfitTier, ...] = ()

    sector: str | None = None
    score_breakdown: Rationale | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CandidateData:
    """Bundle of per-symbol inputs the signal generator needs.

    Bundling avoids the alternative — multiple parallel lookup callbacks
    threaded through every call site. Caller produces these from the
    feature extraction + close price source of their choice (live: yfinance,
    backtest: pre-fetched panel).
    """

    scored: ScoredCandidate
    feature_vector: FeatureVector
    last_close: float
    sector: str | None = None


@dataclass(frozen=True, slots=True)
class HeldPosition:
    """Open-position data the generator needs to emit exits."""

    symbol: str
    sector: str | None = None
    quantity: float = 0.0
    avg_cost: float = 0.0
    feature_vector: FeatureVector | None = None
    last_close: float | None = None


class SignalGenerator:
    """Produce BUY/SELL signals from scored candidates and held positions."""

    def __init__(self, scorer_cfg: ScorerConfig, signal_cfg: SignalConfig) -> None:
        self._scorer = scorer_cfg
        self._signal = signal_cfg
        self._tiers = tuple(
            ProfitTier(fraction=t.fraction, type=t.type, atr_mult=t.atr_mult)
            for t in signal_cfg.profit_tiers
        )

    def generate(
        self,
        candidates: Iterable[CandidateData],
        held: Iterable[HeldPosition] = (),
    ) -> list[TradingSignal]:
        candidate_list = list(candidates)
        held_list = list(held)
        held_symbols = {p.symbol for p in held_list}
        candidate_by_symbol = {c.scored.symbol: c for c in candidate_list}

        signals: list[TradingSignal] = []

        # 1. Exit decisions for held positions: score below threshold or absent.
        for pos in held_list:
            sc = candidate_by_symbol.get(pos.symbol)
            score = sc.scored.score if sc is not None else 0.0
            if score < self._scorer.exit_threshold:
                signals.append(self._exit_signal(pos, sc, score))

        # 2. Entry decisions for non-held candidates.
        for c in candidate_list:
            if c.scored.symbol in held_symbols:
                continue
            if c.scored.score < self._scorer.entry_threshold:
                continue
            signals.append(self._entry_signal(c))

        return signals

    # ------------------------------------------------------------------
    # entries
    # ------------------------------------------------------------------

    def _entry_signal(self, c: CandidateData) -> TradingSignal:
        atr = float(c.feature_vector.atr_14)
        entry = float(c.last_close)
        sl, tp = self._stop_take(entry, atr)
        size = self._signal.position_size_max_pct * c.scored.score
        size = max(0.0001, min(size, self._signal.position_size_max_pct))

        return TradingSignal(
            timestamp=c.scored.timestamp,
            symbol=c.scored.symbol,
            action="BUY",
            confidence=c.scored.score,
            target_size_pct=size,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            profit_tiers=self._tiers,
            sector=c.sector,
            score_breakdown=c.scored.rationale,
            reason=f"score {c.scored.score:.3f} >= entry {self._scorer.entry_threshold:.2f}",
        )

    def _stop_take(self, entry: float, atr: float) -> tuple[float, float]:
        """Compute (stop_loss, take_profit) levels from ATR or fallback %.

        Long-only in v1 — stops are below entry, targets above.
        """
        if _is_nan(atr) or atr <= 0:
            return (
                entry * (1 - _FALLBACK_SL_PCT),
                entry * (1 + _FALLBACK_TP_PCT),
            )
        sl = entry - self._signal.atr_stop_multiplier * atr
        tp = entry + self._signal.atr_tp_multiplier * atr
        return (sl, tp)

    # ------------------------------------------------------------------
    # exits
    # ------------------------------------------------------------------

    def _exit_signal(
        self,
        pos: HeldPosition,
        scored: CandidateData | None,
        score: float,
    ) -> TradingSignal:
        ts = scored.scored.timestamp if scored is not None else datetime.now().astimezone()
        reason = (
            f"score {score:.3f} < exit {self._scorer.exit_threshold:.2f}"
            if scored is not None
            else "no current score (delisted or filtered out)"
        )
        return TradingSignal(
            timestamp=ts,
            symbol=pos.symbol,
            action="SELL",
            confidence=1.0 - score,
            target_size_pct=0.0,
            sector=pos.sector,
            score_breakdown=scored.scored.rationale if scored is not None else None,
            reason=reason,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _is_nan(v: float) -> bool:
    return v != v
