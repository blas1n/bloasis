"""Backtester — walk-forward simulator that ties everything together.

For each fold:
  1. Initialize SimulatedPortfolio at `initial_capital`. Track SPY benchmark
     in parallel (buy-and-hold from fold start).
  2. For each trading day in the test window:
     a. Resolve universe at that date (BacktestData.universe_at).
     b. Build ExtractionContext per symbol (time-sliced; look-ahead enforced
        by ExtractionContext itself).
     c. Cross-section composite, score, generate signals.
     d. Risk-evaluate each signal against current portfolio + market state.
     e. Simulate fills (FillSimulator on next bar).
     f. Apply fills, attach SL/TP levels.
     g. SL/TP enforcement on today's bar (after fills, since today's signals
        fill on next day).
     h. Mark to market, persist equity curve row.
  3. Compute fold metrics (alpha, sharpe, max DD) vs SPY benchmark.

Aggregate fold metrics use the median across folds (per design — single
unlucky fold shouldn't disqualify). Acceptance evaluator runs on the
aggregate to set `passed_acceptance`.

Look-ahead bias is structurally prevented by:
  - Pre-fetching is global, but per-day `bars[sym].loc[:date]` slicing in
    ExtractionContext + the assertion in ExtractionContext.__post_init__.
  - Fills always go to `bars.loc[bars.index > signal_date]` (next bar).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, cast

import numpy as np
import pandas as pd

from bloasis.backtest.acceptance import AcceptanceEvaluator
from bloasis.backtest.fills import FillSimulator
from bloasis.backtest.metrics import (
    annualized_return,
    max_drawdown,
    months_beating_benchmark,
    safe_ratio,
    sharpe_ratio,
    sortino_ratio,
    total_return,
)
from bloasis.backtest.portfolio import Fill, SimulatedPortfolio
from bloasis.backtest.result import BacktestData, BacktestResult, FoldResult
from bloasis.backtest.walk_forward import WalkForwardWindow, generate_folds
from bloasis.config import StrategyConfig
from bloasis.risk import MarketState, PortfolioState, RiskEvaluator
from bloasis.scoring.composites import CompositeBuilder
from bloasis.scoring.extractor import ExtractionContext, FeatureExtractor
from bloasis.scoring.scorer import RuleBasedScorer, Scorer
from bloasis.signal import CandidateData, HeldPosition, SignalGenerator, TradingSignal

if TYPE_CHECKING:
    from sqlalchemy import Engine

WARMUP_DAYS = 300  # SMA200 needs at least 200 bars; 300 leaves slack
MIN_BARS_FOR_FEATURES = 60  # below this, features will be all-NaN — skip


@dataclass(frozen=True, slots=True)
class _BarToday:
    """Subset of today's bar used for SL/TP checks."""

    high: float
    low: float
    close: float


class Backtester:
    """Walk-forward backtest engine.

    Inputs are deliberately abstract:
      - `data` is a pre-fetched BacktestData panel (mockable in tests).
      - `scorer_factory` builds a Scorer per fold (Phase 3 ML retraining).
      - `db_writer` is None for headless test runs; the CLI passes a writer
        to persist `backtest_runs`, `equity_curve`, `trades` rows.
    """

    def __init__(
        self,
        cfg: StrategyConfig,
        data: BacktestData,
        scorer_factory: type[Scorer] | None = None,
        db_engine: Engine | None = None,
    ) -> None:
        self._cfg = cfg
        self._data = _normalize_tz(data)
        self._scorer_factory = scorer_factory or RuleBasedScorer
        self._db = db_engine
        self._extractor = FeatureExtractor()
        self._composer = CompositeBuilder()
        self._signal_gen = SignalGenerator(cfg.scorer, cfg.signal)
        self._risk = RiskEvaluator(cfg.risk)
        self._fills = FillSimulator(cfg.execution)

    # ------------------------------------------------------------------
    # public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        start: date,
        end: date,
        *,
        run_id: int = 0,
        train_days: int = 365 * 3,
        test_days: int = 180,
        step_days: int = 180,
    ) -> BacktestResult:
        """Run the backtest over [start, end] and return the result.

        `run_id` is the FK reference for trades/equity_curve rows when DB
        persistence is wired (PR6); tests pass 0 as a sentinel.
        """
        if start >= end:
            raise ValueError(f"start ({start}) must be < end ({end})")

        folds = list(generate_folds(start, end, train_days, test_days, step_days))
        fold_results: list[FoldResult] = []
        n_trades_total = 0
        delisted_count = 0

        for window in folds:
            scorer = self._build_scorer(window.train_start, window.train_end)
            fold_result, fold_trades, fold_delisted = self._run_fold(
                window=window,
                scorer=scorer,
                run_id=run_id,
            )
            fold_results.append(fold_result)
            n_trades_total += fold_trades
            delisted_count += fold_delisted

        # Aggregate (median across folds).
        agg = _aggregate(fold_results) if fold_results else _empty_aggregate()

        delisted_ratio = (
            delisted_count / max(1, len(self._data.symbols) * len(fold_results))
            if fold_results
            else 0.0
        )

        result = BacktestResult(
            run_id=run_id,
            config_hash="",  # filled by caller (CLI hashes the config)
            start_date=start,
            end_date=end,
            initial_capital=self._cfg.execution.initial_capital,
            fold_results=fold_results,
            median_alpha_annualized=agg["alpha"],
            median_sharpe_vs_spy=agg["sharpe_ratio_vs_spy"],
            median_max_dd_ratio_to_spy=agg["max_dd_ratio_to_spy"],
            median_total_return=agg["total_return"],
            median_spy_total_return=agg["spy_total_return"],
            median_win_rate=agg["win_rate"],
            median_months_beating_spy_pct=agg["months_beating_spy_pct"],
            n_folds=len(fold_results),
            n_trades_total=n_trades_total,
            delisted_symbol_ratio=delisted_ratio,
        )

        acceptance = AcceptanceEvaluator(self._cfg.acceptance_criteria).evaluate(result)
        return _with_acceptance(result, acceptance.passed, acceptance.reasons)

    # ------------------------------------------------------------------
    # per-fold execution
    # ------------------------------------------------------------------

    def _run_fold(
        self,
        *,
        window: WalkForwardWindow,
        scorer: Scorer,
        run_id: int,
    ) -> tuple[FoldResult, int, int]:
        capital = self._cfg.execution.initial_capital
        portfolio = SimulatedPortfolio(initial_capital=capital)

        # Trading days in test window (intersect with SPY index for safety).
        trading_days = self._trading_days(window.test_start, window.test_end)
        if not trading_days:
            return self._empty_fold(window), 0, 0

        equity_curve_strategy: list[float] = []
        equity_curve_spy: list[float] = []

        # SPY benchmark = lump-sum buy at fold start, hold to end.
        spy_initial_close = self._spy_close_at(window.test_start)
        spy_qty = capital / spy_initial_close if spy_initial_close > 0 else 0.0

        delisted_seen: set[str] = set()

        for d in trading_days:
            # 1. Build candidates for today.
            candidates = self._build_candidates(d, scorer)

            # 2. Generate signals.
            held = [
                HeldPosition(
                    symbol=p.symbol,
                    sector=p.sector,
                    quantity=p.quantity,
                    avg_cost=p.avg_cost,
                    last_close=p.last_price,
                )
                for p in portfolio.positions.values()
            ]
            signals = self._signal_gen.generate(candidates, held=held)

            # 3. Risk evaluation + fills.
            today_dt = _to_dt(d)
            vix_today = float(self._data.vix_series.loc[: cast(pd.Timestamp, today_dt)].iloc[-1])
            market_state = MarketState(timestamp=today_dt, vix=vix_today)
            equity_for_sizing = portfolio.total_equity()

            for sig in signals:
                portfolio_state = PortfolioState(
                    total_value=equity_for_sizing,
                    sector_concentrations=portfolio.sector_concentrations(),
                )
                decision = self._risk.evaluate(sig, portfolio_state, market_state)
                if decision.action == "REJECT":
                    continue
                size_pct = (
                    decision.adjusted_size_pct
                    if decision.adjusted_size_pct is not None
                    else sig.target_size_pct
                )

                if sig.action == "BUY":
                    self._execute_buy(
                        sig=sig,
                        size_pct=size_pct,
                        equity=equity_for_sizing,
                        portfolio=portfolio,
                        signal_date=today_dt,
                    )
                elif sig.action == "SELL":
                    self._execute_sell(sig, today_dt, portfolio)

            # 4. SL/TP enforcement on today's bar (after fills above).
            bars_today = self._bars_today(portfolio.held_symbols(), d)
            portfolio.check_stops(
                bars_today,
                today_dt,
                slippage_bps=self._cfg.execution.market_slippage_bps,
            )

            # 5. Mark-to-market.
            close_today = self._closes_at(portfolio.held_symbols(), d)
            portfolio.mark(close_today)

            equity_curve_strategy.append(portfolio.total_equity())
            spy_close = self._spy_close_at(d)
            equity_curve_spy.append(spy_qty * spy_close)

        idx = pd.DatetimeIndex([pd.Timestamp(t).tz_localize(None) for t in trading_days])
        eq_strategy = pd.Series(equity_curve_strategy, index=idx, dtype=float)
        eq_spy = pd.Series(equity_curve_spy, index=idx, dtype=float)

        result = self._fold_result(window, eq_strategy, eq_spy, portfolio)
        delisted_count = len(delisted_seen)
        return result, portfolio.trade_count, delisted_count

    # ------------------------------------------------------------------
    # candidate construction
    # ------------------------------------------------------------------

    def _build_candidates(self, d: date, scorer: Scorer) -> list[CandidateData]:
        ts = _to_dt(d)
        universe = self._data.universe_at(d)

        feature_vectors = []
        last_closes: dict[str, float] = {}
        ts_pd = cast(pd.Timestamp, ts)
        for sym in universe:
            if sym not in self._data.bars:
                continue
            bars = self._data.bars[sym]
            sliced = bars.loc[:ts_pd]
            if len(sliced) < MIN_BARS_FOR_FEATURES:
                continue
            try:
                ctx = ExtractionContext(
                    timestamp=ts,
                    symbol=sym,
                    feature_version=FeatureExtractor.VERSION,
                    sector=self._data.sectors.get(sym),
                    ohlcv=sliced,
                    fundamentals={},
                    vix_series=self._data.vix_series.loc[:ts_pd],
                    spy_close_series=self._data.spy_close_series.loc[:ts_pd],
                )
            except ValueError:
                # Skip symbols that fail look-ahead assertions (data weirdness).
                continue
            fv = self._extractor.extract(ctx)
            feature_vectors.append(fv)
            last_closes[sym] = float(sliced["close"].iloc[-1])

        if len(feature_vectors) < 2:
            return []  # cross-section z-score needs ≥2

        composites = self._composer.build(feature_vectors)
        cv_by_sym = {c.symbol: c for c in composites}

        candidates: list[CandidateData] = []
        for fv in feature_vectors:
            if fv.symbol not in cv_by_sym:
                continue
            scored = scorer.score(fv, cv_by_sym[fv.symbol])
            candidates.append(
                CandidateData(
                    scored=scored,
                    feature_vector=fv,
                    last_close=last_closes[fv.symbol],
                    sector=fv.sector,
                )
            )
        return candidates

    # ------------------------------------------------------------------
    # order execution helpers
    # ------------------------------------------------------------------

    def _execute_buy(
        self,
        *,
        sig: TradingSignal,
        size_pct: float,
        equity: float,
        portfolio: SimulatedPortfolio,
        signal_date: datetime,
    ) -> None:
        target_dollars = equity * size_pct
        if target_dollars <= 0 or sig.entry_price is None:
            return
        quantity = target_dollars / float(sig.entry_price)
        if quantity <= 0:
            return
        bars = self._data.bars.get(sig.symbol)
        if bars is None or bars.empty:
            return
        fill = self._fills.simulate_buy(
            symbol=sig.symbol,
            quantity=quantity,
            signal_date=signal_date,
            signal_close=float(sig.entry_price),
            bars=bars,
            sector=sig.sector,
            reason=sig.reason,
        )
        if fill is None:
            return
        # Refuse if the fill would overdraw cash (slack from risk-eval rounding).
        cost = fill.quantity * fill.price + fill.fees
        if cost > portfolio.cash + 1e-6:
            return
        portfolio.apply(fill)
        portfolio.attach_levels(
            sig.symbol,
            stop_loss=sig.stop_loss,
            take_profit=sig.take_profit,
        )

    def _execute_sell(
        self,
        sig: TradingSignal,
        timestamp: datetime,
        portfolio: SimulatedPortfolio,
    ) -> None:
        pos = portfolio.positions.get(sig.symbol)
        if pos is None:
            return
        # SELL the entire position at next-day open + slippage.
        bars = self._data.bars.get(sig.symbol)
        if bars is None:
            return
        forward = bars.loc[bars.index > timestamp]
        if forward.empty:
            return
        next_bar = forward.iloc[0]
        open_price = float(next_bar["open"])
        slippage = open_price * self._cfg.execution.market_slippage_bps / 10_000
        executed = open_price - slippage
        fill = Fill(
            timestamp=_to_dt_from_ts(next_bar.name),
            symbol=sig.symbol,
            side="sell",
            quantity=pos.quantity,
            price=executed,
            fees=pos.quantity * executed * self._cfg.execution.fees_bps / 10_000,
            slippage_bps=self._cfg.execution.market_slippage_bps,
            sector=pos.sector,
            reason=sig.reason,
        )
        portfolio.apply(fill)

    # ------------------------------------------------------------------
    # data-access helpers
    # ------------------------------------------------------------------

    def _trading_days(self, start: date, end: date) -> list[date]:
        idx = self._data.spy_close_series.index
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        # Match index tz to comparand tz so naive/aware mixing doesn't raise.
        if isinstance(idx, pd.DatetimeIndex) and idx.tz is not None:
            start_ts = start_ts.tz_localize(idx.tz)
            end_ts = end_ts.tz_localize(idx.tz)
        in_range = idx[(idx >= start_ts) & (idx <= end_ts)]
        return [_ts_to_date(t) for t in in_range]

    def _spy_close_at(self, d: date) -> float:
        ts = cast(pd.Timestamp, _to_dt(d))
        series = self._data.spy_close_series.loc[:ts]
        if series.empty:
            return 0.0
        return float(series.iloc[-1])

    def _closes_at(self, symbols: Iterable[str], d: date) -> dict[str, float]:
        ts = cast(pd.Timestamp, _to_dt(d))
        out: dict[str, float] = {}
        for sym in symbols:
            bars = self._data.bars.get(sym)
            if bars is None:
                continue
            sliced = bars.loc[:ts]
            if sliced.empty:
                continue
            out[sym] = float(sliced["close"].iloc[-1])
        return out

    def _bars_today(self, symbols: Iterable[str], d: date) -> dict[str, dict[str, float]]:
        ts = _to_dt(d)
        out: dict[str, dict[str, float]] = {}
        for sym in symbols:
            bars = self._data.bars.get(sym)
            if bars is None or ts not in bars.index:
                continue
            row = bars.loc[ts]
            out[sym] = {
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        return out

    # ------------------------------------------------------------------
    # scorer factory + fold metrics
    # ------------------------------------------------------------------

    def _build_scorer(self, train_start: date, train_end: date) -> Scorer:
        # Phase 1 RuleBasedScorer ignores train window. Phase 3 ML scorer
        # will fit a model here on feature_log entries in [train_start, train_end].
        return self._scorer_factory(self._cfg.scorer)  # type: ignore[call-arg]

    def _fold_result(
        self,
        window: WalkForwardWindow,
        eq_strategy: pd.Series,
        eq_spy: pd.Series,
        portfolio: SimulatedPortfolio,
    ) -> FoldResult:
        sharpe_strategy = sharpe_ratio(eq_strategy)
        sharpe_spy = sharpe_ratio(eq_spy)
        dd_strategy = max_drawdown(eq_strategy)
        dd_spy = max_drawdown(eq_spy)
        months_beating, months_total = months_beating_benchmark(eq_strategy, eq_spy)

        win_total = portfolio.win_count + portfolio.loss_count
        win_rate = portfolio.win_count / win_total if win_total else 0.0

        return FoldResult(
            fold_index=window.fold_index,
            train_start=window.train_start,
            train_end=window.train_end,
            test_start=window.test_start,
            test_end=window.test_end,
            final_equity=float(eq_strategy.iloc[-1]) if not eq_strategy.empty else 0.0,
            spy_final_equity=float(eq_spy.iloc[-1]) if not eq_spy.empty else 0.0,
            total_return=total_return(eq_strategy),
            spy_total_return=total_return(eq_spy),
            annualized_return=annualized_return(eq_strategy),
            annualized_alpha=annualized_return(eq_strategy) - annualized_return(eq_spy),
            sharpe=sharpe_strategy,
            spy_sharpe=sharpe_spy,
            sortino=sortino_ratio(eq_strategy),
            max_drawdown=dd_strategy,
            spy_max_drawdown=dd_spy,
            max_dd_ratio_to_spy=safe_ratio(abs(dd_strategy), abs(dd_spy)),
            win_rate=win_rate,
            n_trades=portfolio.trade_count,
            months_beating_spy=months_beating,
            months_total=months_total,
            equity_curve=eq_strategy,
        )

    def _empty_fold(self, window: WalkForwardWindow) -> FoldResult:
        empty = pd.Series(dtype=float)
        return FoldResult(
            fold_index=window.fold_index,
            train_start=window.train_start,
            train_end=window.train_end,
            test_start=window.test_start,
            test_end=window.test_end,
            final_equity=self._cfg.execution.initial_capital,
            spy_final_equity=self._cfg.execution.initial_capital,
            total_return=0.0,
            spy_total_return=0.0,
            annualized_return=0.0,
            annualized_alpha=0.0,
            sharpe=0.0,
            spy_sharpe=0.0,
            sortino=0.0,
            max_drawdown=0.0,
            spy_max_drawdown=0.0,
            max_dd_ratio_to_spy=0.0,
            win_rate=0.0,
            n_trades=0,
            months_beating_spy=0,
            months_total=0,
            equity_curve=empty,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _to_dt(d: date) -> datetime:
    """date -> naive datetime at midnight.

    The engine works in naive timestamps internally for consistent pandas
    slicing (`_normalize_tz` strips tz from all data indices). When we
    hand off to ExtractionContext, its own tz handling absorbs naive vs
    tz-aware mixing.
    """
    return datetime(d.year, d.month, d.day)


def _normalize_tz(data: BacktestData) -> BacktestData:
    """Strip tz from all data indices for consistent naive comparison.

    Modifies the wrapped DataFrames/Series in place — they're mutable even
    though BacktestData is frozen. Downstream code can rely on naive
    indices across the board.
    """
    spy = data.spy_close_series
    if isinstance(spy.index, pd.DatetimeIndex) and spy.index.tz is not None:
        spy.index = spy.index.tz_localize(None)
    vix = data.vix_series
    if isinstance(vix.index, pd.DatetimeIndex) and vix.index.tz is not None:
        vix.index = vix.index.tz_localize(None)
    for df in data.bars.values():
        if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
    return data


def _to_dt_from_ts(value: object) -> datetime:
    ts = pd.Timestamp(value)  # type: ignore[arg-type]
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.to_pydatetime()


def _ts_to_date(value: object) -> date:
    ts = pd.Timestamp(value)  # type: ignore[arg-type]
    return date(ts.year, ts.month, ts.day)


def _aggregate(fold_results: list[FoldResult]) -> dict[str, float]:
    """Compute medians across fold results (per design — see acceptance.py)."""
    alphas = [f.annualized_alpha for f in fold_results]
    sharpe_ratios = [
        safe_ratio(f.sharpe, f.spy_sharpe) if f.spy_sharpe != 0 else 0.0 for f in fold_results
    ]
    dd_ratios = [f.max_dd_ratio_to_spy for f in fold_results]
    total_rets = [f.total_return for f in fold_results]
    spy_total_rets = [f.spy_total_return for f in fold_results]
    win_rates = [f.win_rate for f in fold_results]
    months_pcts = [
        f.months_beating_spy / f.months_total if f.months_total else 0.0 for f in fold_results
    ]

    return {
        "alpha": float(np.median(alphas)),
        "sharpe_ratio_vs_spy": float(np.median(sharpe_ratios)),
        "max_dd_ratio_to_spy": float(np.median(dd_ratios)),
        "total_return": float(np.median(total_rets)),
        "spy_total_return": float(np.median(spy_total_rets)),
        "win_rate": float(np.median(win_rates)),
        "months_beating_spy_pct": float(np.median(months_pcts)),
    }


def _empty_aggregate() -> dict[str, float]:
    return {
        "alpha": 0.0,
        "sharpe_ratio_vs_spy": 0.0,
        "max_dd_ratio_to_spy": 0.0,
        "total_return": 0.0,
        "spy_total_return": 0.0,
        "win_rate": 0.0,
        "months_beating_spy_pct": 0.0,
    }


def _with_acceptance(
    result: BacktestResult, passed: bool, reasons: tuple[str, ...]
) -> BacktestResult:
    """Return a copy of `result` with acceptance fields set."""
    from dataclasses import replace

    return replace(result, passed_acceptance=passed, acceptance_reasons=reasons)
