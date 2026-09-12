# PR20 All-Axes Grid Measurement (2026-05-09)

PR20 머지 후 6축 (rolling cosine / length signal / tolerance band / Form 4 /
8-K / Russell 2000) 코드 통합. 본 측정은 axis 별 효과를 분리해
combinatorial config 로 검증하는 것이 목적.

## Setup

- Universe: S&P 500 (constituent at 2024-12-31, 13 delistings skipped → 490 symbols)
- Backtest: walk-forward 7 folds, 2022-07-01 .. 2024-10-17
- Engine: `bloasis backtest --train-days 365 --test-days 120 --step-days 120`
- All EDGAR variants share `monthly rebalance (rebalance_days=21)` from PR19.
- Mission acceptance gate (paper): sharpe ≥ 0.7, alpha ≥ -0.5%, DD ≤ 0.85, folds ≥ 5

## Results — 7 variants

| Variant | Description                                       | α       | sharpe | DD/SPY | trades | gate |
|---------|---------------------------------------------------|---------|--------|--------|--------|------|
| A       | EDGAR rolling_window=2                            | +4.09%  | 1.334  | 0.80   | ~440   | **PASS (live)** |
| B       | EDGAR blend (cosine + length 0.3)                 | -0.53%  | 1.041  | 0.852  | ~440   | FAIL α/DD (margin) |
| C       | EDGAR tolerance band 0.2                          | +2.92%  | 1.015  | 0.80   | ~440   | PASS (= PR19 baseline) |
| D       | EDGAR length-only                                 | -2.25%  | 0.864  | 0.83   | ~440   | FAIL α |
| E       | EDGAR combo (rolling+blend+tolerance)             | -2.82%  | 0.824  | 0.83   | ~440   | FAIL α |
| F       | Form 4 insider cluster (window 60d)               | -1.03%  | 0.914  | 0.843  | 1357   | FAIL α |
| G       | 8-K event count (window 30d)                      | -11.50% | 0.708  | 0.867  | 1945   | FAIL α/DD |

## Findings

### 1. **A (rolling_window=2) is the new champion — sharpe 1.334, +4.09% alpha.**

PR19 baseline (sharpe 1.015, +2.92% alpha) → +0.32 sharpe lift, +1.17pp alpha
from a single config flag. Mechanism: averaging cosine across the two most
recent 10-K YoY pairs smooths out one-off filings dialect noise and keeps
the persistent disclosure-shift signal.

**Recommendation**: promote A to ship-ready config (`configs/edgar-rolling2.yaml`).

### 2. **EDGAR length signal (D) is alpha-destructive**, blend (B) dilutes.

The "Lazy Prices" length-change-pct ranking does not survive on this universe
(SP500 2022-2024). Pure cosine is the load-bearing signal; blend doesn't
help, length-only kills it. Combo (E) overfits.

### 3. **Form 4 / 8-K event scorers underperform on SP500.**

- F (insider): -1.03% alpha. Top decile insider clusters in mega-caps are
  too noisy — buy-back / 10b5-1 plan trades dominate Form 4 volume.
- G (8-K): -11.50% alpha. Turnover 1945 trades (3-4x EDGAR), and many 8-Ks
  are routine (Item 5.02 director appointments, Item 8.01 misc). Naive
  count-based ranking captures noise > signal at SP500 size.

**These code paths remain in repo** (event scorers + Russell 2000 universe)
for future tuning — possible directions: filter Form 4 by P (purchase) vs S
(sale), filter 8-K by Item-2.02 (earnings) / Item-1.01 (material agreement).
Russell 2000 universe also untested (cache cold; would take ~1h yfinance
prefetch).

### 4. **Tolerance band (C) is redundant on EDGAR low-turnover.**

C ≡ PR19 baseline. EDGAR portfolio already turns over slowly (monthly
rebalance + sticky 10-K filings); tolerance band has no churn to dampen.

## Decision: ship A

`configs/edgar-rolling2.yaml` based on PR19 ship config + `edgar_rolling_window: 2`.
Live-gate cleared (sharpe ≥ 1.0, α ≥ -0.5%, DD ≤ 0.85). Promotes from
paper-ready (PR18) → paper-passing (PR19) → live-eligible (PR20-A).

## Pending follow-ups

- Form 4 P/S filter (insider purchases only) — likely high-quality but
  rare events; reduce window size, top_pct.
- 8-K Item filter — keep 1.01, 2.02, 5.07; discard 5.02, 8.01.
- Intangible Value scorer (Eisfeldt-Kim-Papanikolaou 2020) — XBRL fetcher
  pending. Deferred to next PR.
- Russell 2000 measurement — small-cap universe yfinance prefetch pending.
- LightGBM scorer + axis features — Phase 2 ML revisit with PR20 features
  in feature_log.
