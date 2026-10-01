# E2E checklist — Item 1A span anchored on the section heading (#83)

`_extract_item_1a` maximized span length, so a forward-looking-statements
cross-reference to Item 1A — which sits before Item 1 Business — anchored the
span and swallowed the business description and the officer table.

## Pre-merge
- [ ] Every 10-K the `edgar-rolling2` runs read (SP500 walk-forward window +
      live window) re-extracted from the SEC HTML; count of filings whose
      extraction is byte-identical / shorter / lost entirely.
- [ ] PARA FY2021–FY2024 and PSKY FY2025 spans start at the `Item 1A` heading
      and contain no officer table.
- [ ] Per-filer adjacent-year span-length ratio distribution, before vs after.
- [ ] Live path (`_build_live_candidates`, SP500, `configs/edgar-rolling2.yaml`)
      re-ranked on a cloned cache: names with a changed cosine, new selection
      cutoff, selected-set diff (added / removed).
- [ ] PSKY↔Paramount and XOM pair cosines recomputed (#82 / #77).
- [ ] 2-year walk-forward re-run (`--train-days 365 --test-days 120
      --step-days 120`, 2022-07-01..2024-10-17, sp500_at:2024-12-31) and the
      Phase 1 exit gate in `docs/mission.md` re-evaluated: sharpe ≥ 1.0,
      α ≥ −0.5%, DD ratio ≤ 0.85 (baseline 1.334 / +4.09% / 0.80).
- [ ] CI gate: ruff check · ruff format --check · mypy · pytest.

## Post-merge
- [ ] First 08:00 KST `paper-rotate` run after merge re-fetches nothing it
      should not (`~/.cache/bloasis/edgar/risk_factors` texts are rewritten
      only as filings are refetched) and places orders without a traceback.
- [ ] The main session decides whether `edgar-rolling2-sp500-paper-2026-09`
      restarts, given the selected-set diff.
