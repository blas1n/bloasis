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

Run 2026-10-03, one cloned cache, 80 backtests. Coverage: development 493/503
names with bars, H2 468/505.

| window / kind | DD ratio p10 / median / p90 | seeds ≤ 0.85 | α p10 / median / p90 | median trades |
|---|---|---|---|---|
| dev / R1 | 0.543 / 0.640 / 0.682 | **20/20** | −9.0% / −3.3% / +3.3% | 1,354 |
| dev / R2 | **0.865** / 0.952 / 1.108 | 1/20 | −10.6% / −3.6% / +4.3% | 434 |
| H2 / R1 | 0.551 / 0.629 / 0.695 | **20/20** | −15.5% / −9.6% / −6.2% | 1,870 |
| H2 / R2 | **0.868** / 0.907 / 1.006 | 0/20 | −5.3% / −2.8% / −0.8% | 599 |

Measured strategies against the development R2 distribution: EDGAR DD 0.873
is better than 85% of random books (J1 0.897: 80%, J0 1.020: 30%). EDGAR's
α +3.74% is better than 85% of them, which is below the random p90 (+4.3%).

### Verdict under the pre-registered rule

- **R2, the turnover EDGAR-like signals actually have: the bar is out of the
  frame's reach** in both windows (random p10 0.865 and 0.868 > 0.85).
- R1: the bar is **not a skill test** (random median 0.64 and 0.63 ≤ 0.85).

### What this says about the DD criterion

1. **The DD ratio mostly measures turnover, not selection.** The same random
   selection passes 0.85 every time when it churns monthly (R1) and almost
   never when it holds for a year (R2). R1 buys low drawdown with time out of
   the market, and pays for it in α (median −3.3% / −9.6%). A strategy can
   meet the bar by churning, and a low-turnover strategy with real skill can
   miss it.
2. **For low-turnover books, 0.85 asks for more than the frame allows.** The
   best tenth of random persistent books lands at about 0.87. EDGAR's 0.873 is
   already near that edge. That is consistent with every signal measured so
   far failing the bar by a small margin.
3. **EDGAR's development α is not distinguishable from luck at the usual
   level.** About one random persistent book in seven to ten matches it. This
   agrees with the out-of-window result (#102).

These are inputs to the #88 decision. Nothing here changes the gate.

Raw output: the driver's JSON (`--out`), not committed.
