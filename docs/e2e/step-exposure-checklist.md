# E2E checklist — sector cap counts BUYs placed earlier in the same step (#93)

The engine builds `PortfolioState` once per rebalance step and
`execute_strategy_step` evaluated every signal of that step against it. BUYs
accepted earlier in the step were invisible to the sector cap, so a step could
add any number of positions to a sector that opened just under the cap. The
runner now grows a private copy of the exposure as BUYs go out; a rejected
order adds nothing, and SELLs free room only at the next step's snapshot.

## Pre-merge
- [x] `edgar-rolling2` (cap 1.0) reproduces the #92 sweep re-run baseline
      exactly (DD 0.873 / sharpe 1.013 / α +3.74% / 398 trades) — a 1.0 cap
      on real sectors cannot bind even with in-step accumulation. Full
      17-arm re-run 2026-10-02: the baseline and every arm with a 0.4 or 1.0
      cap are identical to the #92 run field for field (per-fold DD too).
- [x] The sector-cap arms of the #85 sweep move where the cap can now bind
      within a step (`sector=0.2` at `pos=0.02/0.03`), and the change goes the
      way the fix says: fewer or smaller BUYs, not more. Only those two moved:
      `pos=0.02 sector=0.2` 394 → 393 trades, DD 0.873 → 0.833, sharpe
      1.013 → 0.995, α +3.74% → +1.90%; `pos=0.03 sector=0.2` 308 → 307
      trades, DD 0.936 → 0.999, α +8.15% → +0.48%. Still 0 of 17 qualify
      (the first arm's DD now passes but sharpe drops under 1.0).
- [x] `baseline.yaml` (cap 0.30) re-measured on the same cache, so the PR
      states the effect on configs whose cap binds. Before (main, post-#92):
      DD ratio 1.474 / sharpe −0.20 / α −22.9% / 1,258 trades — reproduces
      the #92 E2E exactly. After: 1.372 / −0.47 / −24.7% / 1,223 trades.
