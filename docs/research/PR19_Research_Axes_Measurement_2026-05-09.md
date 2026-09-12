# Bloasis PR19 Research Axes — Measurement (2026-05-09)

> **Status**: 🎯 **EDGAR clean + monthly rebalance = first config to clear
> live-gate sharpe AND paper-gate alpha+sharpe+DD simultaneously.**

After PR18 (paper-gate first pass with EDGAR daily), academic research
agent identified 5 actionable improvements (`Modern_Alpha_Research_2026-05-09.md`).
PR19 implements the top 2 + 1 axis from internal plan and measures.

## Code axes shipped

| # | Axis | Config knob | Source |
|---|---|---|---|
| 1 | Rebalance every N trading days | `signal.rebalance_days` (default 1) | internal — turnover ↓ hypothesis |
| 2 | Residual / idiosyncratic momentum | `scorer.jt_residual: bool` | Blitz-Hanauer-Vidojevic 2020 (academic agent #1) |
| 3 | Continuous score (hysteresis) | `scorer.continuous_score: bool` | internal — entry/exit threshold gap |

## Measurements (SP500, 2022-2024, 7 walk-forward folds)

| Config | sharpe | alpha | DD/SPY | paper-gate |
|---|---:|---:|---:|:---:|
| _PR18 baseline_ | | | | |
| JT vanilla daily | 0.860 | +5.32% | 1.46 | DD fail |
| EDGAR daily | 0.997 | +1.49% | **0.802** | ✅ all 4 |
| _PR19 axes_ | | | | |
| JT residual daily | 1.019 | +2.00% | 1.24 | DD fail |
| JT residual + monthly | 1.068 | **+8.99%** | 1.20 | DD fail |
| JT residual + pos05 | **1.122** | +6.61% | 1.27 | DD fail |
| EDGAR continuous | 1.121 | +0.96% | 0.97 | DD fail |
| **EDGAR + monthly** | **1.015** | **+2.92%** | **0.800** | ✅ **all 4 + live-gate sharpe** |

## Best new config — `configs/edgar-clean-monthly.yaml`

EDGAR cosine + monthly rebalance:
- alpha **+2.92%** ✅ (2× of daily)
- sharpe **1.015** ✅ (clears live-gate 1.0 by 0.015)
- DD/SPY **0.800** ✅ (unchanged from daily, gate 0.85)
- passes all 4 paper-gate criteria + live-gate sharpe

## Key findings

1. **Rebalance smoothing (PR19 axis #1) lifts alpha 2× without DD cost** —
   exactly matches Chitsiripanich-Paolella 2024 finding. Cheapest sharpe
   improvement we measured: 30 lines of engine change.

2. **Residual momentum (academic agent #1) trades alpha for sharpe + DD on
   JT** — sharpe 0.86 → 1.02 (+18%), DD 1.46 → 1.24 (-15%), but alpha 5.3%
   → 2.0% (-3.3pp). **Halves vol but doesn't fix DD-fail on its own** —
   baseline JT problem is concentration (50 stocks tech-cluster), not just
   beta.

3. **Residual + monthly compounds well on JT**: alpha 2.0% → 8.99% (4.5×),
   sharpe 1.02 → 1.07. DD still 1.20 (not fixed).

4. **Continuous score hurts EDGAR more than helps** — sharpe ↑ 0.997 → 1.12
   but DD ↑ 0.80 → 0.97 (held positions ride down through threshold gap).
   Binary mode preserves DD discipline.

5. **EDGAR is more friction-resilient than JT** (PR18 finding) AND more
   smoothing-responsive than JT (PR19 finding) — lifecycle of an annual
   filing makes monthly rebalance natural.

## Production status

| Config | use case |
|---|---|
| `edgar-clean.yaml` (PR18) | baseline paper-gate config |
| **`edgar-clean-monthly.yaml`** (PR19) | **best ship-ready: all paper-gates + live-gate sharpe** |

Live-gate alpha (`median_alpha_annualized >= 0.0`) cleared at +2.92%.
**6-month paper trading required** for full live-gate per mission §Live-trading
gate; otherwise this config is ready for paper deployment.

## Deferred axes (next PR)

From research agent + internal plan:
- Tolerance-band rebalancing (academic #2) — overlay on rebalance_days
- EDGAR length-change variant scorer
- EDGAR rolling smoothing (multi-filing avg)
- Russell 2000 universe (small-cap, learning agent suggests stronger
  EDGAR signal)
- Form 4 insider clusters (academic agent #4) — new fetcher
- 8-K item-trigger event drift (academic agent #5) — reuses EDGAR
  pipeline
- Intangible Value (academic agent #3) — XBRL plumbing required
- Frontier LLM for FundamentalLLMScorer / EdgarLLMScorer

Russell 2000 ticker list cached at `/tmp/pr19_runs/russell2000_2026.csv`
(1918 tickers from iShares IWM holdings). Ready for next PR.

## Run metadata

- Worktree: `/Users/blasin/Works/bloasis/wt/pr19-research-axes`
- Branch: `pr19/research-axes`
- Configs: `configs/edgar-clean-monthly.yaml` (production), 4 grid
  variants in `/tmp/pr19_runs/cfg-*.yaml`
- 586 tests pass; mypy/ruff clean
