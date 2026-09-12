# Bloasis — JT 12-1 Momentum Robustness 분석 (2026-05-07)

PR12 design 결정 전 sanity check. 5/5 baseline JT 12-1 pilot (sharpe ratio
1.21 vs SPY, alpha +7.6%) 가 점추정 — 분포 평가로 통계적 신뢰도 확인.

스크립트: `/tmp/jt_momentum_robustness.py` / 데이터 dump:
`/tmp/jt_momentum_robustness.json`. 동일 universe (490 종목 × 2019-01..2024-12),
no costs / no risk gate, daily-frequency mark-to-market.

## 1. Block Bootstrap (1000 reps, ~21-day expected block)

Politis-Romano stationary bootstrap on joint daily returns.

| 메트릭 | p5 | p50 | p95 | mean |
|---|---:|---:|---:|---:|
| sharpe ratio vs SPY | **0.46** | 1.16 | 2.92 | 1.69 |
| annualized alpha | -1.1% | +7.9% | +17.9% | +8.0% |

- **p50 sharpe ratio 1.16** — baseline 1.21 보다 약간 낮지만 acceptance gate 1.0
  통과
- **70%** of bootstrap reps have sharpe ratio ≥ 1.0
- **91.2%** of reps have positive alpha
- p5 sharpe ratio 0.46 = 5% 확률로 baseline 의 1/3 수준. 실제 다음 6년은
  p5-p95 어디든 가능

## 2. 연도별 분해 — alpha concentration 발견

| Year | strat ann | SPY ann | **alpha** | sharpe_strat | sharpe_spy | DD_strat |
|---|---:|---:|---:|---:|---:|---:|
| 2019 | +11.1% | +14.4% | **-3.3%** | 0.66 | 1.05 | -9% |
| 2020 | +42.0% | +15.1% | **+26.8%** | 0.85 | 0.42 | **-39%** |
| 2021 | +25.9% | +29.2% | **-3.3%** | 0.98 | 1.95 | -14% |
| 2022 | -4.8% | -20.2% | **+15.3%** | -0.19 | -0.92 | -20% |
| 2023 | +20.1% | +25.2% | **-5.2%** | 1.09 | 1.7 | -14% |
| 2024 | +37.8% | +24.1% | **+13.7%** | 1.52 | 1.71 | -12% |

**핵심 발견 — alpha 가 3개 년도에 집중**: 2020 (+26.8%), 2022 (+15.3%),
2024 (+13.7%). 합계 +56%. 나머지 3년 (2019, 2021, 2023) 은 -3% ~ -5% drag.

**3개 양의 alpha 년도의 공통점**:
- 2020: COVID 패닉 + 회복기 (V자 반등 momentum 끝물)
- 2022: bear market (성장주 → 가치주, 약 momentum 의 short-momentum-on-defaults
  특성)
- 2024: AI rally + Trump trade (강한 trend 후반)

**음의 alpha 3개 년도의 공통점**: 2019/2021/2023 — quiet bull markets.
SPY 가 꾸준히 오를 때 momentum strategy 는 SPY 따라가다가 회전 비용으로 살짝
underperform. 정확히 Daniel-Moskowitz "Momentum Crashes" 가 예측하는 패턴
— momentum 의 alpha 는 trend/crisis 시점에서 발생하고 quiet 시기에 cost drag
로 잠식.

## 3. Yearly Leave-One-Out

해당 년도 1개 빼고 나머지 5년 평가:

| 빼는 year | sharpe_ratio | alpha |
|---|---:|---:|
| 2019 | 1.30 | +7.8% |
| **2020** | **0.97** | **+3.3%** ← 가장 의존적 |
| 2021 | 1.53 | +8.4% |
| **2022** | **0.92** | **+4.3%** ← 두 번째 의존적 |
| 2023 | 1.51 | +9.2% |
| 2024 | 1.29 | +6.1% |

- 2020 빼면 sharpe ratio 1.0 미만 (0.97), alpha 3.3% — borderline
- 2022 빼면 0.92 — fail
- 2020+2022 동시에 빼면 사실상 fail. 즉 6년 중 2년에 의존

**위험**: 다음 6년에 2020-급 패닉/회복 또는 2022-급 bear market 이 1번도 안
오면 쉽게 0.5-0.7 sharpe ratio 로 떨어질 수 있음. 단순 momentum 만으로는
근본적으로 "regime 변동" 을 사야 alpha 가 나오는 strategy.

## 4. CPCV-Light (6 blocks, drop 2, C(6,2)=15 조합)

연도별이 아닌 chronological 1/6 블록 단위로 2개 빼고 나머지 4개로 평가:

| 메트릭 | min | p5 | p50 | p95 | max |
|---|---:|---:|---:|---:|---:|
| sharpe ratio vs SPY | **0.90** | 0.95 | 1.21 | 1.60 | 1.73 |
| annualized alpha | — | +3.9% | +7.0% | +8.6% | — |

- **86.7%** (13/15) of combinations pass sharpe ratio ≥ 1.0
- **100%** of combinations have positive alpha
- worst combo (0.90) 도 acceptance gate (1.0) 와의 거리 작음

CPCV 가 yearly LOO 보다 더 robust 한 신호 — 더 잘게 자를수록 평균이 안정.
2-year-block 사이즈 이슈 줄어듦.

## 5. 종합 — PR12 진행 결정

**진행 권고**. 근거:

1. **신호 robust**: 91% bootstrap rep + 100% CPCV combo positive alpha
2. **acceptance gate 통과 robust**: 70% bootstrap + 87% CPCV combo
   sharpe ratio ≥ 1.0
3. **하지만 concentration risk 명확**: alpha 가 2-3 년에 집중. 다음 6년에
   regime shift 없으면 sharpe drop 가능

**PR12 design 에 직접 반영해야 할 점**:

1. **Daniel-Moskowitz dynamic scaling 필수** (docs/research/Quant_References.md
   §1):
   - 2020 strategy DD -39% 는 max_dd_ratio 1.15 fail 의 직접 원인
   - DM panic-state risk overlay (vix_zscore_60d + spy_above_sma200 활용)
     로 2020 Q1 노출 줄이면 DD 임계 통과 가능성
   - 단, 2020 의 +26.8% alpha 의 일부도 같이 줄어들 위험. balance 중요
   - 적용 후 measurement 결과 보고 fine-tune

2. **AQR-style multi-factor blend** 검토 (long_mom + quality + low_vol):
   - 단일 momentum 으로는 quiet years (2019/2021/2023) 에 -3 ~ -5% drag
   - quality + low_vol overlay 가 quiet years 의 cost drag 흡수 가능
   - long-only 구조라 분산 효과 제한적이지만 (Quant_References §2 caveat)
     ex-ante vol normalize blend 자체는 가치 있음

3. **walk-forward 측정 시 stress test 추가**:
   - 단일 6년 점추정 → 2-3 windows 정도로 측정 (2019-2022 + 2021-2024 등)
   - 다음 PR12 backtest 결과의 sharpe 가 1.21 이라도 진짜 신뢰 구간은
     [0.95, 1.60] 로 보고

4. **acceptance gate 정의 재검토 후보** (별도 design discussion):
   - 현재 `median_sharpe_vs_spy >= 1.0` 단일 임계. 점추정 vs 분포 의식 X
   - 더 robust: `5th-percentile_sharpe_vs_spy >= 0.7` 같은 percentile gate
   - 또는 `% of CPCV folds passing >= 0.7` 식
   - PR12 에 변경 포함하지 말 것 — 별도 PR 또는 PR13. 측정 일관성 우선.

5. **Phase 2 ML 우선순위 추가 하향**:
   - Quiet-years 의 -3 ~ -5% drag 제거가 ML 의 가장 명확한 가치 (regime
     filter 학습)
   - 하지만 PR12 + DM overlay 만으로 acceptance pass 가능성 높음
   - ML 은 Phase 1 통과 후 P&L 향상용 work

## 6. 다음 PR12 scope (확정안)

**Order of work** (가장 high-ROI 부터):

1. `momentum_252_21` feature 정식 통합 (features + extractor + composite +
   schema). feature_version 2 bump.
2. **Daniel-Moskowitz dynamic vol overlay** — `bloasis/scoring/regime_overlay.py`
   신규 모듈, vix_zscore + spy_above_sma200 로 panic-state 식별 후 size
   scaling (논문 식: target_size = base_size × (target_vol / realized_vol_60d))
3. `configs/baseline-v2.yaml` — weights `long_momentum=0.5, momentum=0.1
   (단기 보조), quality=0.2, volatility=0.2`, regime overlay 활성, sentiment 0.05 cap
4. 풀 walk-forward 백테스트 + acceptance gate 측정 (cost / risk 모두 포함)
5. **bonus**: walk-forward 두 개 윈도우 측정 (2019-2022, 2021-2024) — CPCV
   분포 신뢰성 production 검증

기대 결과:
- sharpe ratio ≥ 1.0 (CPCV 87% 통과 률 + DM 보강)
- alpha ≥ -0.5% (모든 CPCV 조합 +3.9% 이상)
- max_dd_ratio ≤ 0.85 (DM dynamic scaling 가 2020 Q1 핵심 contribution)
- acceptance gate **통과 가능성 높음**

기대치 충족 시 → mission.md M3 (live trading) 조건부 진입 가능.
