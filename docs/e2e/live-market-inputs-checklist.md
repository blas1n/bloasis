# E2E checklist — live trade path gets real VIX + SPY returns (#91)

The `trade` commands called `execute_strategy_step` with `vix=0.0` and an
empty SPY return series. The VIX risk gates and the regime overlay could never
act in paper/live, while the backtest applied both every step. The values were
already in the panel `_build_live_candidates` prefetches; they are now passed
through, sliced as of the latest bar the way `Backtester` slices them.

## Pre-merge
- [x] Real data, cloned cache, `configs/edgar-rolling2.yaml`, the paper
      universe: `_build_live_candidates` returns a VIX equal to the `^VIX`
      close on the latest bar date, and at least `vol_lookback_days` (126)
      SPY returns ending on that date. 2026-10-01 run: 500 candidates, latest
      bar 2026-09-30, VIX 16.34 = cached `^VIX` close for 2026-09-30 (the
      2026-10-01 close 16.79 was in the panel and correctly excluded);
      454 SPY returns, 2024-12-06 → 2026-09-30.
- [x] `bloasis trade dry-run` with that config runs end to end (InMemoryPaperBroker,
      no Alpaca) and places orders — 20 large caps, 2 BUYs filled (AMZN, META).
- [x] The overlay is reachable live: the same real SPY series with
      `regime_overlay.enabled: true` gives a scale ≠ 1.0 from
      `compute_regime_scale` (before #91 it was 1.0 for any config) —
      0.9616 enabled, 1.0 disabled.
- [x] Today's effect on the running paper session: VIX on the latest bar vs
      `vix_high` 30 / `vix_extreme` 40, so the PR states whether tomorrow's
      paper run behaves any differently — VIX 16.34 is below both and
      `edgar-rolling2` keeps the overlay disabled, so the next paper run is
      unchanged. The difference appears only on days VIX closes above 30.
