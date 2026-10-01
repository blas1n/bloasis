# E2E checklist — backtest rejects a BUY it cannot pay for (#85 F3)

`execute_strategy_step` sizes a BUY on equity, not cash, and
`SimulatedPortfolio.place_market_order` handed every fill to `apply()`, which
raises `ValueError("insufficient cash")`. At `position_size_max_pct=0.03` the
first step whose BUYs outran cash aborted the whole walk-forward. `PaperBroker`
and Alpaca report the same situation as a rejected order, so the simulator now
does too; `apply()` keeps raising for direct callers.

## Pre-merge
- [x] `pos=0.03` arms of `scripts/dd-sweep-85.py` (full 17-arm run, cloned
      cache, 2026-10-01) run to completion — 3 rows, 7 folds each, no traceback.
- [x] Arms that never ran out of cash are unchanged: all 14 arms measured
      before the fix reproduce the 2026-10-01 sweep field for field (folds,
      DD, sharpe, α, trades, per-fold DD), including baseline 0.873 / 1.013 /
      398 and `pos=0.02 sector=0.2` 0.828 / 1.015 / 357. Each had zero
      rejected orders.
- [x] In a `pos=0.03` run, rejected BUYs actually occur (count > 0) — otherwise
      the run completing proves nothing about this path. Counted by wrapping
      `place_market_order`: sector 0.2 / 0.4 → 259 filled + 91 cash-rejected;
      sector 1.0 → 367 filled + 235 cash-rejected.
