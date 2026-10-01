# E2E checklist — sectors from EDGAR SIC codes (#92)

Nothing outside a unit test filled `BacktestData.sectors`, and live passed an
empty concentration map. Every holding was bucketed under `_unknown`, so
`risk.max_sector_concentration` capped total invested fraction in backtest
(default 0.30) and could only clip one order live. Prefetch now maps each
symbol's EDGAR SIC code to a GICS-like sector (`bloasis/data/sectors.py`), and
live buckets held market value by that map.

## Pre-merge
- [x] Mapping vs an authored classification: current S&P 500 (Wikipedia
      constituents table, GICS Sector column) — coverage and agreement,
      reported before and after the carve-outs, with the in-sample caveat.
      2026-10-01: 503/503 have a SIC and map to a sector. Agreement 82.9%
      (417/503) with the first table; 85.7% (431/503) after five parent-code
      carve-outs (6324, 4400/448x, 4700/472x, 3020-3021, 7900). Those were
      chosen from this same sample's mismatches, so 85.7% is in-sample; each
      follows a GICS sub-industry definition, not a per-company fix. Remaining
      misses are mixed codes left on one sector: 7389 (13, mostly payments →
      Financials), 7370 (GOOGL/META → Communication Services), 381x/382x/7374.
      Per-sector recall ranges from 15/23 (Communication Services) to 29/30
      (Real Estate).
- [x] `edgar-rolling2` (cap 1.0) reproduces the #85 sweep baseline exactly
      (DD 0.873 / sharpe 1.013 / α +3.74% / 398 trades): the sector is
      pass-through in scoring, and a 1.0 cap cannot bind on a real sector.
      Identical field for field, including per-fold DD. Three other cap-1.0
      arms did move (overlay σ=0.12 clip=1.5: DD 0.662 → 0.685; `pos=0.03
      sector=1.0`: 0.912 → 0.930): with every holding in one `_unknown`
      bucket, a 1.0 cap bound once total invested neared 100% — which the
      1.5 lever-up and 3% sizing reach. On real sectors it no longer binds.
- [x] The sweep's sensor now reports a populated sector map, and the
      `sector=0.2/0.4` arms produce different numbers from each other (they
      were byte-identical when the cap was a gross-exposure gate).
      `sector map: 493 entries, 11 distinct non-null sectors`. `pos=0.02`:
      sector 0.2 → DD 0.873 / 394 trades, sector 0.4 → identical to baseline
      (398). The two #85 "qualifying" arms (DD 0.828) are gone; 0 of 17 arms
      qualify.
- [x] A default-cap config (`baseline.yaml`, cap 0.30) measured before and
      after on the same panel, so the PR states how much configs that relied
      on the default change. Same cloned cache, canonical 7 folds:
      before DD ratio 0.518 / sharpe −0.33 / α −23.4% / 867 trades;
      after DD ratio 1.474 / sharpe −0.20 / α −22.9% / 1,258 trades.
      The old run was held near 30% invested by the `_unknown` bucket.
- [x] Live: `_build_live_candidates` on the sp500 paper universe returns a
      sector for (nearly) every candidate. 500/500 candidates carry a sector;
      the map has 503 entries over 11 sectors.
