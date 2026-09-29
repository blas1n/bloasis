# E2E checklist — `trade paper --universe`

Paper cron switched from a hard-coded 50-name list to the SP500 universe
that `configs/edgar-rolling2.yaml` was validated on.

## Pre-merge
- [x] `--universe sp500` resolves the live constituent list (503 names) and
      the scorer produces candidates for them (497; 3 skipped by yfinance,
      25 NaN cosine) — measured 2026-09-29, cold cache 276 s.
- [x] Top decile = 47 names (≈94% invested at 2%/name) vs 4 names (≈8%) on
      the old 50-name list.
- [x] The 4 currently held names (ABBV AMZN KO LIN) remain selected → no
      forced SELL on the first run.
- [x] `-s` together with `--universe`, and an unknown universe, both exit
      non-zero before any order is placed (unit tests).
- [x] CI gate: ruff check · ruff format --check · mypy · pytest (771 passed, 84%).

## Post-deploy (first 08:00 KST run after merge)
- [ ] Old session `edgar-rolling2-paper-2026-05` closed (`bloasis paper close`).
- [ ] `logs/paper-rotate.log` shows `paper session: edgar-rolling2-sp500-paper-2026-09`
      and roughly 40–45 BUY rows, no traceback.
- [ ] Run finishes well before US open (START→END < 15 min).
- [ ] Next Monday BStockReport shows Bloasis with long MV ≈ 90%+ of equity.
