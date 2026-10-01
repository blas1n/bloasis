# E2E checklist — Item 1A span anchored on the section heading (#83)

`_extract_item_1a` maximized span length, so a forward-looking-statements
cross-reference to Item 1A — which sits before Item 1 Business — anchored the
span and swallowed the business description and the officer table.

## Pre-merge
- [x] All 4,395 10-Ks the `edgar-rolling2` runs read (SP500 walk-forward window
      + live window) re-extracted from the SEC HTML on a cloned cache:
      1,137 byte-identical · 3,066 shorter (median −36.2%) · 27 longer
      (truncations repaired) · 18 lost · 147 extracted by neither parser.
      Total ranked text 469.5M → 320.4M chars (−31.8%). The recomputed
      pre-fix text matched the 3,907 texts already in the cache byte for
      byte, so the baseline run is a true baseline.
- [x] All 18 lost filings were cross-reference-anchored before (0 of 18 had a
      heading-anchored start) — e.g. USB FY2020 and HON FY2023 incorporate
      Item 1A by reference, so `None` is the correct answer.
- [x] PARA FY2021–FY2024 and PSKY FY2025 start at the `Item 1A` heading;
      `Chief Executive Officer` / `Executive Officers` no longer in the span.
      PARA FY2024 176,872 → 128,905 · FY2023 94,948 → 48,302 chars.
- [x] Adjacent-year span-length ratio (3,726 pairs): p90 1.251 → 1.212,
      p95 1.449 → 1.300, p99 2.642 → 1.637, max 548x → 5.1x;
      ≥1.5x 163 (4.4%) → 62 (1.7%), ≥2x 67 (1.8%) → 13 (0.3%).
- [x] Live path (`_build_live_candidates`, SP500 503 names, cloned cache,
      identical OHLCV): 379/500 names changed cosine, eligible 484 → 482
      (GEV, NTAP now NaN), cutoff 0.9962 → 0.9967, selected 48 → 48 with
      **13 added / 13 removed** (35 kept).
- [x] XOM FY2024↔FY2023 (#77) cosine 0.5292 → 0.9918; FY2023↔FY2022
      0.9939 → 0.9923. PSKY FY2025↔PARA FY2024 (#82) 0.8261 → 0.7513
      (that pair is still NaN in the pipeline — PSKY has one 10-K under its
      own CIK).
- [x] Walk-forward re-run on the canonical protocol of
      `configs/grids/pr21-edgar-rolling.yaml` (2022-01-01..2024-10-17,
      train 180 / test 120 / step 120, sp500_at:2024-12-31 → 7 folds; the
      `--train-days 365` line in `docs/research/PR20_Grid_Measurement_…` is
      stale and gives 3 folds). Both arms: same 487 symbols, same OHLCV.
      | arm | folds | α/yr | sharpe | DD ratio | trades |
      |---|---|---|---|---|---|
      | documented 2026-05-09 | 7 | +4.09% | 1.334 | 0.80 | ~440 |
      | before | 7 | +5.62% | 1.107 | 0.883 | 394 |
      | after | 7 | +3.74% | 1.013 | 0.873 | 398 |
- [x] **Phase 1 exit gate FAILS after the fix — and already fails before it.**
      α and sharpe pass in both arms (after: +3.74%, 1.013); the drawdown
      ratio fails in both (0.883 before, 0.873 after, bar 0.85), so the
      failure is data drift since May 2026, not this change. The fix moves DD
      slightly down and costs −0.094 sharpe / −1.88pp α.
- [x] All 4,230 extracted texts start at an Item 1A heading;
      `Chief Executive Officer` appears in 1,774 before-texts vs 555 after
      (the remainder are genuine risk-factor mentions).
- [x] CI gate: ruff check · ruff format --check · mypy · pytest (844 passed,
      85.7% coverage).

## Post-merge
- [ ] The first 08:00 KST `paper-rotate` run after merge re-downloads every
      10-K once — `risk_factors/v2/` starts empty in `~/.cache/bloasis`, and
      the pre-#83 texts beside it are never read again. Measured ~1 filing/s,
      so expect roughly an hour of SEC fetching (US open is 13.5 h after the
      cron fires). It can be pre-warmed by copying the verified v2 texts from
      this measurement instead; that is the main session's call, since it
      writes the shared cache.
- [ ] `logs/paper-rotate.log` shows ~48 selected names, the 12 held names that
      lost selection (ACGL APO ARES CVS DUK ETR HST ODFL PCG SNA WAB WRB)
      sold, and no traceback.
- [ ] The main session decides whether `edgar-rolling2-sp500-paper-2026-09`
      restarts, given the 13-added / 13-removed selected-set diff.
- [ ] Phase 1 gate follow-up: the DD-ratio failure reproduces on the unchanged
      code too, so it belongs in its own issue (re-measure `edgar-rolling2`
      against today's data, or re-tune) rather than in this PR.
