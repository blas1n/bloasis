# `bloasis tune` — Bayesian / multi-objective config search (deferred)

`bloasis grid` (PR21) is the cheap, honest baseline for combinatorial
config measurement: a person enumerates the axis combinations they care
about and reads the leaderboard. When that approach starts to plateau —
typically once the meaningful knob count exceeds ~10, or when continuous
parameters need fine sweeps — automated search becomes the next step.

This doc captures the design so the future PR has a clear target. **It
is intentionally not implemented yet.**

## Why not now

1. **Search ⇒ overfit.** Every additional trial inflates the optimistic
   selection bias on walk-forward sharpe (Bailey-de Prado, 2014). Without
   a deflated-sharpe-ratio correction or nested-CV, picking "best by
   walk-forward sharpe" out of N trials makes the live result
   asymptotically worse, not better.
2. **Per-trial cost is expensive.** Full SP500 5-year walk-forward = 5–25
   minutes; 200 trials = 16–80 hours wall clock. The grid (PR21) maxes
   out at ~30 trials in practice — humans pick well in low dimensions.
3. **The current search space is small enough.** PR20 ships ~10
   meaningful knobs. Most live alpha-affecting interactions are
   discoverable by hand once the grid runner exists.

## Design intent (when built)

### Library

[Optuna](https://optuna.org/) — multi-objective via NSGA-II or TPE,
strong pruning, pickleable studies, native sqlite backend.

### Spec format (extension of grid spec)

```yaml
name: pr2X-tune-edgar
base: configs/edgar-rolling2.yaml
walk_forward: ...
universe: sp500
mode: tune                     # vs grid
sampler: nsga2                 # tpe | nsga2 | random
n_trials: 200
objectives:
  - {metric: median_alpha_annualized, direction: maximize}
  - {metric: median_sharpe_vs_spy,    direction: maximize}
  - {metric: median_max_dd_ratio_to_spy, direction: minimize}
search_space:
  - {path: scorer.edgar_rolling_window, type: int,        low: 1, high: 5}
  - {path: signal.rebalance_days,       type: int,        low: 1, high: 63}
  - {path: scorer.edgar_textdiff_top_pct, type: float,    low: 0.05, high: 0.30}
  - {path: scorer.continuous_score,     type: categorical, choices: [true, false]}
nested_walk_forward:
  outer_test_days: 240         # OOS — held out from search
  inner_train_days: 365
  inner_test_days: 120
  inner_step_days: 120
deflation:
  method: deflated_sharpe_ratio  # Bailey-de Prado 2014
```

### Pipeline

```
spec.outer_folds  ──► for each fold:
                       Optuna study on inner WF only (no outer touch)
                       → pick best trial by Pareto front + DSR
                       → run THAT config on outer test fold once
                       → record outer_result
report:
  per-outer-fold table
  Pareto plot (Optuna built-in)
  deflated sharpe ratio per shipped candidate
```

### Anti-overfit discipline

- **Outer test data never participates in trial selection.** Every trial
  scores on inner walk-forward only.
- **Deflated sharpe ratio** correction applied before declaring any trial
  "best": `DSR(trial) = sharpe × √(1 - skew/N + (kurt-1)/(4N²)) -
  Φ⁻¹(1 - α/N)` where N = number of trials.
- **A trial that wins on inner WF but degrades on outer test fold is the
  expected case** — that's the search-overfit signal. Report both
  numbers; don't paper over the gap.

### CLI surface

```bash
bloasis tune run  configs/grids/pr2X-tune-edgar.yaml
bloasis tune show pr2X-tune-edgar              # study leaderboard + Pareto
bloasis tune resume pr2X-tune-edgar --add-trials 100
bloasis tune outer-validate pr2X-tune-edgar    # run best trial on holdout
```

### Storage

- Optuna study DB at `~/.cache/bloasis/optuna/{study_name}.db` (sqlite,
  Optuna native, separate from `bloasis.db`).
- Each trial that passes inner-fold acceptance gets persisted as a
  normal `backtest_runs` row with `name = "{study}#trial={idx}"` so the
  existing `runs show` and `grid show` work unchanged.

### Out of scope even at tune time

- Online / live retraining loops.
- Multi-fidelity (Hyperband) — every trial runs full WF; the per-trial
  cost is bounded and pruning has limited gain when each fold is short.
- Distributed search — single-process is enough at 100–500 trials.

## Trigger to build this

Build `bloasis tune` when **at least two** of these are true:

1. `bloasis grid` regularly runs ≥ 50 combinations per investigation.
2. Active search axes ≥ 8 (combinatorial blowup on grid).
3. Continuous knobs (e.g. `top_pct`, `length_blend_weight`) need finer
   sweeps than the human-picked grid resolution.
4. Walk-forward backtest cost drops materially (cache warm + parallel
   so per-trial < 1 min).

Until then, `bloasis grid` + human judgment is the right tool.
