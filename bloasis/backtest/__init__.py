"""Walk-forward backtest engine.

Pipeline:
    BacktestData (pre-fetched panel)
    -> Backtester.run() -> BacktestResult (with per-fold + aggregate metrics)
    -> AcceptanceEvaluator -> pass/fail vs config gate

All modules in this package are pure compute (no I/O) except `engine.py`,
which calls into `bloasis/storage/writers.py` to persist runs/trades/equity.
"""

from bloasis.backtest.acceptance import AcceptanceEvaluator, AcceptanceResult
from bloasis.backtest.engine import Backtester
from bloasis.backtest.fills import FillSimulator
from bloasis.backtest.metrics import compute_metrics
from bloasis.backtest.portfolio import Position, SimulatedPortfolio
from bloasis.backtest.result import BacktestData, BacktestResult, FoldResult
from bloasis.backtest.walk_forward import WalkForwardWindow, generate_folds

__all__ = [
    "AcceptanceEvaluator",
    "AcceptanceResult",
    "BacktestData",
    "BacktestResult",
    "Backtester",
    "FillSimulator",
    "FoldResult",
    "Position",
    "SimulatedPortfolio",
    "WalkForwardWindow",
    "compute_metrics",
    "generate_folds",
]
