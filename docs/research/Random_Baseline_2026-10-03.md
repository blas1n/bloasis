# No-skill baseline for the DD bar — pre-registration and result (2026-10-03)

Point-in-time record. Per `docs/research/README.md`, measurement logs are not
updated after the fact.

Issue: [#88](https://github.com/blas1n/bloasis/issues/88), reopened 2026-10-03.

## Why

Every signal measured in the `edgar-rolling2` portfolio frame has failed the
paper gate's DD bar of 0.85: EDGAR (0.873), JT residual (1.020), and both with
the volatility overlay (0.897 at best). A bar should be set from something
that does not depend on any candidate's result. A no-skill distribution is
such a thing: run the same frame with random selection and see where 0.85
falls in it.

## Pre-registration

Written and committed **before** the run. Driver:
`scripts/random-baseline-88.py`.

### Frame (fixed)

`configs/edgar-rolling2.yaml` unchanged: 2% positions, top-10% selection, 0.65
/ 0.40 entry/exit, monthly rebalance, ATR stops and take-profit tiers, no
sector cap, overlay off. Only the signal is replaced, by a deterministic
pseudo-random number (SHA-256 of kind, seed, symbol, period):

| kind | redrawn | stands in for |
|---|---|---|
| R1 | every rebalance | a signal with no persistence |
| R2 | once per symbol per calendar year | a signal that moves with annual filings, like EDGAR's |

Seeds 1–20 for each kind. Windows: development 2022-01..2024-10
(`sp500_at:2024-12-31`, 7 folds) and H2 2018-01..2021-12 (`sp500_at:2021-12-31`,
10 folds). H1 is not used: its lower coverage would confound the comparison.
Walk-forward 180 / 120 / 120.

### What is reported

For each window × kind: p10 / median / p90 of the 20 seeds' median DD ratio
and median α, and the share of seeds with DD ratio ≤ 0.85.

### Interpretation rule (fixed in advance)

Read per window, on the kind closer to the candidate's turnover (R2 for
EDGAR-like signals; both are reported):

- **Bar is out of the frame's reach**: random p10 > 0.85. Even the best tenth
  of random books miss it, so the bar demands more than any plausible
  selection skill within this frame.
- **Bar is not a skill test**: random median ≤ 0.85. A coin passes it.
- **Bar is a skill test**: p10 ≤ 0.85 < median.

This informs the #88 decision; it does not change the gate by itself. Where
the measured strategies (EDGAR 0.873, J0 1.020, J1 0.897 on development) fall
in the random distribution is reported as context.

## Results

<!-- filled in after the run -->
