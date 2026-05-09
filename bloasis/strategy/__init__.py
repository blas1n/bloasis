"""Per-step strategy runner shared by backtester and live trade path (PR49).

`bloasis/strategy/runner.py:execute_strategy_step` is the single function
that drives one step of a strategy. The backtester calls it once per
trading day in a fold; the live CLI calls it once per cron invocation.
The only difference is which `BrokerAdapter` is passed — `SimulatedPortfolio`
for backtest, `AlpacaBrokerAdapter` for paper / live.
"""

from bloasis.strategy.runner import StepResult, execute_strategy_step

__all__ = ["StepResult", "execute_strategy_step"]
