# E2E checklist — a sector cap of 1.0 never binds

`max_sector_concentration: 1.0` is the "no cap" setting (`edgar-rolling2`).
It still bound in two situations:
- on rotation steps, where #93 counts the step's buys but frees sells only at
  the next snapshot;
- on panels with no sector map, which prefetch builds for price-only scorers
  at cap 1.0 (#92 `sectors_needed`), so every holding sits in `_unknown`.

Measured 2026-10-04: in a price-only development panel, a random monthly-churn
book had 585 of 1,305 BUY decisions rejected and 21 clipped by that bucket.

## Pre-merge
- [x] The same probe (price-only dev panel, R1 seed 1) shows 0 sector
      rejections or clips after the fix, and its DD ratio is no longer 0.666.
      BUY decisions 1,216 approve + 46 adjust (VIX / order cap), 0 sector;
      DD 0.666 → 0.944, α +3.54% → −8.55%, trades 1,373 → 2,184.
- [x] `edgar-rolling2` development baseline unchanged (DD 0.873 / sharpe 1.013 /
      α +3.74% / 398 trades). Its panel has real sectors, so a cap of 1.0 never
      reached a bucket. Identical on 2026-10-04.

## Affected records (to re-measure after merge, separate PRs)
- `Random_Baseline_2026-10-03.md` (#108): price-only panel. R1 entirely, R2 at
  year boundaries.
- `JT_Residual_2026-10-03.md` (#107): price-only panel with monthly rotation.
