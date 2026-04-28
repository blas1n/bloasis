"""BacktestData input + BacktestResult / FoldResult output dataclasses.

Kept separate from engine.py so tests and reporting code can import the
result types without pulling in the full engine + DB dependency graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class BacktestData:
    """Pre-fetched panel for a backtest run.

    Built by the CLI from yfinance + universe loader; tests build synthetic
    panels. Bars must include a sufficient warmup before `start_date` so
    the first day of the backtest has 200+ bars of history (SMA200, etc.).

    `universe_by_date` lets callers rebalance the universe over time
    (sp500_historical). When None, `symbols` is used for every date.

    Sectors map symbol -> sector name (from fundamentals_cache or yfinance
    info). Missing sectors are passed through as None and skip sector
    concentration in risk evaluation.
    """

    symbols: list[str]
    bars: dict[str, pd.DataFrame]  # symbol -> daily OHLCV indexed by datetime
    vix_series: pd.Series
    spy_close_series: pd.Series
    sectors: dict[str, str | None] = field(default_factory=dict)
    universe_by_date: dict[date, list[str]] | None = None

    def universe_at(self, d: date) -> list[str]:
        """Return symbols tradable on `d`. Falls back to `self.symbols` if no
        rebalance map was provided."""
        if self.universe_by_date is None:
            return self.symbols
        # Use the most recent rebalance entry with date <= d
        eligible = [k for k in self.universe_by_date if k <= d]
        if not eligible:
            return self.symbols
        return self.universe_by_date[max(eligible)]


@dataclass(frozen=True, slots=True)
class FoldResult:
    """Per-fold backtest output.

    A "fold" is one train+test pair from `WalkForwardWindow`. For Phase 1
    the train window is informational (RuleBasedScorer doesn't actually
    train); for Phase 3 ML, the model is fit on the train slice.

    All metric fields are scalars; equity_curve is a Series indexed by
    test-period trading days for plotting / further analysis.
    """

    fold_index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    final_equity: float
    spy_final_equity: float
    total_return: float
    spy_total_return: float
    annualized_return: float
    annualized_alpha: float
    sharpe: float
    spy_sharpe: float
    sortino: float
    max_drawdown: float
    spy_max_drawdown: float
    max_dd_ratio_to_spy: float
    win_rate: float
    n_trades: int
    months_beating_spy: int
    months_total: int

    equity_curve: pd.Series  # daily test-period equity values


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Aggregate output of a Backtester.run() call.

    Aggregate metrics use the **median** across folds (per design — the
    acceptance gate also uses median so a single bad fold doesn't disqualify
    the strategy).

    `passed_acceptance` is filled in by `AcceptanceEvaluator` after the run
    completes; the engine attaches it before persisting the row.
    """

    run_id: int
    config_hash: str
    start_date: date
    end_date: date
    initial_capital: float

    fold_results: list[FoldResult]

    # Aggregate (median across folds).
    median_alpha_annualized: float
    median_sharpe_vs_spy: float
    median_max_dd_ratio_to_spy: float
    median_total_return: float
    median_spy_total_return: float
    median_win_rate: float
    median_months_beating_spy_pct: float

    n_folds: int
    n_trades_total: int

    # Acceptance evaluation (set after construction).
    passed_acceptance: bool = False
    acceptance_reasons: tuple[str, ...] = ()

    # Limitations active for this run (e.g., L001 survivorship).
    delisted_symbol_ratio: float = 0.0
