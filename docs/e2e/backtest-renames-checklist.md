# E2E checklist — backtests resolve historical constituent tickers (#103)

`data.ticker_renames` (#80) was applied only on the live trade path. Backtests
over historical S&P 500 lists asked yfinance for retired tickers (ANTM, FB,
BLL, …), so those companies dropped out of the panel even though their price
history lives on under today's symbol. `prefetch_backtest_data` now applies
the table, and it gains 25 historical renames, each verified against SEC data.

## Pre-merge
- [x] Canonical `edgar-rolling2` baseline (2022-01..2024-10, `sp500_at:2024-12-31`)
      is unchanged (DD 0.873 / sharpe 1.013 / α +3.74% / 398 trades). That
      list already uses current tickers. 2026-10-02: identical, 7 folds.
- [x] Holdout coverage re-measured with the same driver as the #103 comment:
      scoreable share at each H1/H2 date goes up, and only by renamed names.
      The first re-run showed no change: the driver looked members up by
      their old ticker while the panel is keyed by the current one. After it
      looked them up through the rename table, the gain in names with bars
      equals the number of recovered renames at every date (+18, +18, +22,
      +22, +13, +13). Scoreable: 2013 66% → 69%, 2015 70% → 73%,
      2017 77% → 81%, 2018 79% → 83%, 2020 86% → 88%, 2021 88% → 90%.
- [x] A renamed company is actually in an H2 panel under its current symbol,
      with 10-K history (e.g. ELV for ANTM, META for FB). Prefetch of
      [ANTM, FB, AAPL] for 2018–2021 yields ELV and META with full bars
      (2017-03 → 2021-12), 10-Ks back to 2013, and sectors.
