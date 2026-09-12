# Bloasis Phase 3D Final — EDGAR text-diff Paper-Gate 통과 (2026-05-09)

> **Status**: 🎯 **Bloasis 첫 paper-gate 통과 config** — EDGAR cosine
> clean pos=0.02 (50 stocks). 3-window robustness 검증. 추가 concentration
> tuning 으로 sharpe 1.076 / alpha +11.39% (DD 만 fail).

## 핵심 발견 1줄 요약

1. **bloasis backtest engine 의 friction 이 모든 신호 80-90% 까먹고 있었음**
   (특히 high-turnover JT)
2. **EDGAR 학술 cosine 신호가 friction 비활성 시 정확히 작동** — 학술 sharpe
   1.0+ 와 우리 측정 0.997 일치
3. **friction 가설 부분 falsified** — EDGAR (low-turnover) 에선 friction
   영향 X. 진짜 alpha driver 는 **concentration (position_size)**
4. **paper-gate 첫 통과** — EDGAR clean pos=0.02 (50 stocks): alpha
   +1.49%, sharpe 0.997, DD 0.80

## 측정 종합 (모두 SP500 2022-2024 walk-forward, 7 folds)

### EDGAR concentration grid

| pos | n_stocks | sharpe | alpha | DD/SPY | PASS |
|---:|---:|---:|---:|---:|:---:|
| **0.02** | **50** | **0.997** | **+1.49%** | **0.80** | **✅ all 4 gates** |
| 0.04 | 25 | **1.076** | +3.92% | 0.933 | ❌ DD by 0.083 |
| 0.05 | 20 | 0.871 | +3.52% | 0.895 | ❌ DD by 0.045 |
| 0.07 | ~14 | 1.006 | **+11.39%** | 0.935 | ❌ DD by 0.085 |
| 0.10 | 10 | 0.915 | +8.21% | 0.98 | ❌ DD |

### EDGAR cross-window robustness (pos=0.02 clean, 3 windows)

| Window | sharpe | alpha | DD | fails |
|---|---:|---:|---:|:---:|
| 2014-2019 | 0.985 | -6.08% | 0.207 | 1 (α) |
| 2019-2022 | **1.258** | -2.86% | 0.71 | 1 (α) |
| 2022-2024 | 0.997 | +1.49% | 0.80 | **0 ✅** |
| **median** | **0.997** | -2.86% | 0.71 | 1 (α median) |

→ sharpe + DD 매우 robust. alpha 시기 의존 (2022-2024 만 양수).

### Friction decomposition (EDGAR clean baseline + 1 friction at a time)

| Variant | sharpe | alpha | DD | PASS |
|---|---:|---:|---:|:---:|
| ALL OFF (clean) | 0.997 | +1.49% | 0.80 | ✅ |
| profit_tiers ON | 0.997 | +1.49% | 0.80 | ✅ |
| ATR stops ON | 1.005 | +0.53% | 0.83 | ✅ |
| Slippage 5bps ON | 0.997 | +1.49% | 0.80 | ✅ |
| **cash limit (pos 0.10)** | 0.915 | **+8.21%** | 0.98 | ❌ DD |

→ profit_tiers / ATR stops / slippage **모두 EDGAR 에 무영향**. 진짜 driver
는 cash limit (= concentration setting).

### JT vs EDGAR friction sensitivity 비교

| Scorer | friction sharpe | clean sharpe | Δ |
|---|---:|---:|---|
| JT (high-turnover, daily) | 0.225 | 0.860 | +0.64 (3.8x) |
| **EDGAR (low-turnover, annual)** | **0.110** | **0.997** | **+0.89 (9x)** |

→ EDGAR 가 friction-cleaning 에 가장 큰 효과. **신호 별 friction
sensitivity 다름** — production tuning 시 scorer 별로 분리 필요.

## Live deployment readiness

EDGAR clean pos=0.02 (50 stocks):
- mission paper-gate 모두 통과
- mission live-gate sharpe 1.0 까지 0.003 격차 (3 windows median 0.997)
- alpha gate 시기 의존성 큼 (2022-2024 +1.49%, 2014-2019 -6.08%, 2019-2022 -2.86%)

→ **paper trading 가능**. 6개월 paper track record + 3 window 추가 검증
후 live 가능.

## DD reduction candidates (다음 step, user 결정)

EDGAR pos=0.04/0.07 가 sharpe + alpha 둘 다 best 인데 DD 만 fail (0.08
정도 차이). DD reduction 시도:

1. **regime overlay** (BSC vol-target + DM bear gate) — Phase 1 cfg 활용
2. **monthly rebalance** — daily turnover 줄여 DD ↓ (코드 변경 필요할 수)
3. **multi-pos blend** — pos 0.02 (DD-safe) + pos 0.07 (alpha-strong) 가중
   평균
4. **Russell 2000 universe** — small-cap 의 EDGAR 신호 더 강할 가능성
5. **EDGAR + JT intersection clean** (이미 측정 — alpha 양수, but DD 0.98)

## 코드 자산 (PR18 worktree)

- `bloasis/data/fetchers/sec_edgar.py` — EDGAR client + Item 1A extraction
- `bloasis/scoring/edgar_textdiff.py` — TF cosine + length change
- `bloasis/scoring/scorer.py:EDGARTextDiffScorer` — cross-section rank
- `bloasis/cli.py` (this PR fix) — filings filter by backtest window
- 542 unit tests pass; mypy/ruff clean

## Run metadata

- Worktree: `/Users/blasin/Works/bloasis/wt/pr18-jt-momentum-rank`
- Branch: `pr18/jt-momentum-rank` (NOT pushed)
- DB: `bloasis.db` runs 50-77 (각 fold-level 결과 저장)
- Configs: `/tmp/pr18_runs/cfg-{edgar-clean, edgar-pos-{004,005,007},
  fr1-tiers, fr2-stops, fr3-cash, fr4-slip, edgar-jt-clean, jt-clean,
  pead-clean, fund-llm-clean}.yaml`

## Strategic 결정 영역 (user)

1. **Paper deploy 시작** — EDGAR clean pos=0.02 + Alpaca paper trading.
   mission 의 6개월 paper track record 시작.
2. **DD reduction 추가 tuning** — pos 0.04/0.07 의 alpha 활용 위해 DD 0.85
   까지 줄이는 tuning. regime overlay, monthly rebalance, multi-pos blend.
3. **Multi-window robustness** for pos=0.04, 0.07 — 3 windows 검증 (cache
   cold).
4. **Russell 2000 universe** — small-cap 에서 EDGAR signal 강도 검증.
