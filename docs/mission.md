# BLOASIS Mission

## Phase 1 Goal — M2 (Risk-adjusted parity with SPY)

> **Match SPY annualized return with at least 20% lower max drawdown,
> via VIX-based regime de-risking on US large caps.**

This is the immediate, achievable goal. It requires no genuine alpha — only
disciplined risk management and regime adaptation.

## Long-term Aspiration — M1 (Sustained alpha)

> **Generate +1% to +3% annualized alpha vs SPY** through Signal edge
> (PEAD, analyst revisions) and Universe edge (Russell 1000 expansion),
> using free-tier or low-cost data only.

## Non-goals (explicit)

- High-frequency or intraday strategies
- Options, futures, crypto, FX in v1
- Generating > 5% annualized alpha — statistically unrealistic for retail
  with public data
- Multi-user / web service deployment
- Real-time streaming pipelines

## Acceptance Gates (locked, machine-checked)

A configuration cannot be promoted to live trading unless it passes its phase
gate via walk-forward backtest. Gates live in `configs/*.yaml` under
`acceptance_criteria` and are evaluated by `bloasis backtest`.

### Phase 1 → Phase 2 (M2 achievement)

```yaml
walk_forward_min_folds: 5            # at least 5 independent OOS periods
median_alpha_annualized: -0.005      # within 50 bps of SPY (parity)
median_sharpe_vs_spy: 1.0            # equal or better
median_max_dd_ratio_to_spy: 0.85     # ≤ 85% of SPY drawdown (DD edge)
```

### Phase 2 → Phase 3 (M2+)

```yaml
median_alpha_annualized: 0.015       # +1.5% sustained
bootstrap_alpha_p_value: 0.10        # statistically distinguishable
```

### Phase 3 → Phase 4 (M1 reach)

```yaml
median_alpha_annualized: 0.03        # +3%
white_reality_check_p: 0.05          # rigorous
forward_test_alpha_6mo: 0.01         # live paper-trade verification
```

## Halt Conditions (live trading)

If live deployment underperforms by margin or duration, the system halts and
reverts allocation to SPY-only:

| Trigger | Action |
|---------|--------|
| Live 6-month alpha < -2% | Halt strategy, revert to 100% SPY |
| Live 30-day max DD > 1.5× backtest median | Reduce strategy allocation 50% |
| Acceptance criteria broken on rolling backtest | Block new orders |

## Why these numbers?

- 20% DD reduction is the **lowest defensible** improvement that justifies
  active management complexity. Below that, just hold SPY.
- +1-3% alpha range matches **academic factor return decay estimates** for
  publicly known anomalies (value, momentum, quality) on liquid US equities.
- Halt at -2% / 6mo prevents extended underperformance from unverified ideas.

## What this mission **forbids**

- Reporting absolute return without SPY benchmark
- Promoting a config to live without walk-forward validation
- Optimizing on full-history (backtest must use train/test split)
- Adding a feature or scorer change without `feature_version` bump

## Mission revision

This file is the project's North Star. Any change here requires:

1. Documented reason in commit message
2. Re-evaluation of all `acceptance_criteria` against the change
3. Re-running canonical backtests under both old and new mission
