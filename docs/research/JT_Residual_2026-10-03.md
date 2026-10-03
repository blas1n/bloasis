# JT residual momentum under protocol v2 — pre-registration and result (2026-10-03)

Point-in-time record. Per `docs/research/README.md`, measurement logs are not
updated after the fact.

First candidate under research protocol v2
([#103](https://github.com/blas1n/bloasis/issues/103), `docs/mission.md`
"Holdout and fragility conditions").

## Why this candidate

- **Data**: it needs prices only, so it can run on both holdouts. Candidates
  that need point-in-time small-cap membership, delisted prices or long
  fundamentals history cannot (#103 coverage notes). An LLM-based scorer is
  excluded because historical windows may sit inside the model's training data.
- **Prior**: residual 12-1 momentum (Blitz–Hanauer–Vidojevic 2020) is a
  published, long-only-friendly signal. The overlay this round pairs with it,
  Barroso–Santa-Clara volatility targeting, was designed for momentum crashes,
  which is a stronger fit than it was for the EDGAR signal in #85.
- **What earlier numbers are worth**: PR19 measured "JT residual + monthly" at
  α +8.99% / DD 1.20. That run used `baseline-v3-jt`, whose 0.30 sector cap
  was, before #92, a cap on total invested. Those numbers are not comparable
  and are not used here.

## Pre-registration

Written and committed **before** any run. Driver: `scripts/jt-residual-103.py`.

### Arms (fixed)

Portfolio construction is `configs/edgar-rolling2.yaml` unchanged: 2%
positions, `max_single_order_pct` 0.02, monthly rebalance (21 days), no sector
cap. Only the signal changes: `scorer.type: jt_momentum`,
`jt_residual: true`, `jt_top_pct: 0.10`.

| arm | overlay |
|---|---|
| J0 residual | off |
| J1 residual + vol target | on: σ_target 0.12, bear_scale 0.5, `scale_clip [0, 1.0]` (de-risk only) |

### Stages and gates (fixed, applied mechanically by the driver)

1. **Development** 2022-01-01..2024-10-17, `sp500_at:2024-12-31`, 7 folds.
   Paper gate: α ≥ −0.5%, sharpe vs SPY ≥ 0.7, DD ratio ≤ 0.85, folds = 7.
2. **Fragility**, only for arms that pass stage 1. Drop a random 5% of the
   universe (seeds 1, 2, 3) and re-run the development window. Passes if α > 0
   in all three runs and the median is ≥ 0.5 × the stage-1 α.
3. **Holdouts**, only for arms that pass stage 2, each run once:
   H1 2013-01-01..2017-12-31 (`sp500_at:2017-12-31`, 13 folds) and
   H2 2018-01-01..2021-12-31 (`sp500_at:2021-12-31`, 10 folds).
   Each passes if folds ≥ 5, α > 0 and DD ratio ≤ 0.85.

Walk-forward 180 / 120 / 120 throughout. One prefetch per window, shared by the
arms.

### Decision

- An arm that passes all three stages is a **paper candidate**. The founder
  then decides whether to move it to paper. If both arms pass, the one with
  the lower development DD ratio is proposed. Both are reported.
- If no arm passes, that is the result. No third arm, no parameter change
  and no re-run of a holdout follows from it.
- Holdout results are reported with their coverage: H1 has roughly 69–81% of
  the index scoreable after #106, and acquired or delisted names are missing
  in every window.

## Results

<!-- filled in after the run -->
