# Bloasis Phase 2 — Final Measurement (2026-05-07)

PR17. Phase 2 ML pipeline 종착점. 측정 결과 + acceptance gate 평가 +
mission halt vs continue 결정.

## TL;DR

**ML scorer 가 rule scorer 보다 개선됨 — 하지만 acceptance gate 통과 X**.
Mission "halt" 옵션 권고.

| 지표 | Rule (2022-2024) | **ML (2022-2024)** | 차이 | Acceptance |
|---|---:|---:|---:|---:|
| median_alpha_annualized | -0.2742 | **-0.2287** | +4.5pp | ≥ -0.005 ❌ |
| median_sharpe_vs_spy | -0.239 | **+0.038** | +0.28 | ≥ 1.0 ❌ |
| median_max_dd_ratio_to_spy | 0.559 | 0.492 | -0.067 | ≤ 0.85 ✅ |

5개월 + 17 PRs 작업, 모든 시나리오 acceptance fail. 정공법 결론: **paper
trading 진입 불가, halt**.

## Setup

- **Universe**: S&P 500 as-of 2024-12-31 (503 종목, 13 skipped → 490
  effective. PR12 와 동일 cached 데이터)
- **Window**: 2022-01-01 .. 2024-12-31 (held-out 평가 윈도우)
- **ML training**: 2019-2021 (3년) → 243k labeled rows, model.pkl 저장
- **Walk-forward**: train 365d / test 120d / step 120d → 6 folds
- **scorer.type**: `rule` 와 `ml` 두 config 비교
- **regime_overlay**: disabled (단순 측정 위해)

Reproducible: `bloasis.db` run_ids 1 (rule 2019-2024 base), 2 (ml 2022-2024),
3 (rule 2022-2024).

## ML Training (2019-2021)

`bloasis ml train --train-end 2021-12-31` → LightGBM regressor, 5-fold
purged walk-forward CV (21d embargo):

| fold | IC |
|---:|---:|
| 0 | +0.0301 |
| 1 | -0.2009 |
| 2 | +0.0566 |
| 3 | +0.0757 |
| 4 | -0.1377 |
| **mean** | **-0.0353** |

**Mean IC slightly negative**. Within-CV variance huge (±20%). Folds 1
& 4 (covering COVID 2020 + recovery 2021) are deeply negative — model
trained on quiet period generalizes poorly to crisis. Folds 0, 2, 3 are
mildly positive.

이 자체로 PR15 design 의 가설 ("ML 이 dynamic weighting 으로 rule scorer
ceiling 돌파") 의 weak evidence. IC 0.05 가 "real signal" floor (Kelly-
Pruitt-Su 2020) 인데 mean -0.0353 은 floor 미달.

## Multi-Run Comparison

### Rule Scorer Baseline (2019-2024 full)

15 folds, 2914 trades:
- median_alpha: **-0.2035**
- median_sharpe: **-0.194** (음수)
- median_DD_ratio: 0.400

PR12 의 rule baseline sharpe 0.30 보다 *더 나쁨*. 차이는 PR12 features
(momentum_252_21, kbar_*, corr_pv_20) 가 baseline 의 momentum/technical/
liquidity composites 에 추가되어 기존 신호 dilute (PR12 measurement 에서
이미 발견된 패턴). Rule scorer 는 features 추가될수록 악화.

### Rule Scorer (2022-2024 held-out)

6 folds, 1200 trades:
- median_alpha: -0.2742
- median_sharpe: -0.239
- DD ratio: 0.559

Held-out window 에서 더 나쁨. 2022 bear market + 2023-2024 AI rally 모두
rule scorer 에 adversarial.

### ML Scorer (2022-2024 held-out, model trained 2019-2021)

6 folds, 2443 trades:
- median_alpha: **-0.2287**
- median_sharpe: **+0.038**
- DD ratio: 0.492
- alpha 모든 6 folds 음수 (-0.13 ~ -0.34)

**ML 가 rule 대비 개선** (sharpe -0.24 → +0.04) — 하지만 sharpe ≈ 0,
**SPY 와 거의 차이 없음** + 모든 folds 음의 alpha → 신호 부재.

## 진단

### ML 이 rule 보다 좋은 이유 (작은 개선)

1. **Cross-section z-score → CDF** mapping 이 동적. rule scorer 는 hardcoded
   weights 로 정적 매핑.
2. **Non-linear interactions**: LightGBM 이 features 간 상호작용 학습. 단,
   23 features 에 대한 학습량 (243k rows) 이 *부족함* 에 의한 underfitting
   가능성.
3. **Feature selection 자동**: trees 가 informative features 만 선택. rule
   scorer 의 7-composite blend dilution 회피.

### 왜 acceptance pass 못 했나

1. **ML mean IC -0.035** — Kelly-Pruitt-Su 2020 의 "real signal" 임계
   (IC ≥ 0.05) 미달. 모델 자체가 학습할 signal 거의 없음.
2. **시간 감쇠 + regime shift**: 2019-2021 (COVID 시기) 학습한 모델이
   2022-2024 (높은 금리, AI rally) regime 에 일반화 실패. PR12 의 시간
   감쇠 (sharpe 0.46 → 0.35 → -0.24) 와 일관.
3. **Cap-weighted SPY 구조 문제 그대로**: ML 도 equal-weight 로 entry
   threshold 통과하는 종목 매수 → mega-cap tech AI rally 의 cap-weighted
   SPY 못 따라감.
4. **Look-ahead 측면 honest**: 2019-2021 학습 + 2022-2024 평가 = true
   forward test. PR15/PR16 의 in-sample IC 가 양수 (~+0.05 짜리) 였을
   가능성, but 진짜 forward test 에서는 mean IC -0.035 + alpha -23%.

### 가능한 추가 작업 (모두 risk 큼)

A. **Hyperparameter tuning**: 보수적 default 에서 깊은 grid search.
   Lopez de Prado 경고: "ML factor research 80% time spent on hyperparams
   gives 5% IC improvement". 위험 대비 보상 작음.

B. **Per-fold retraining (일반 walk-forward CV)**: 현재 train-once.
   매 fold 학습 → ~5x compute, real walk-forward. 측정 신뢰도 향상이지만
   alpha 자체 개선은 의문.

C. **Feature engineering 확장**: qlib alpha158 의 cherry-pick 외 50+ 추가.
   Phase 2 design lockin §risk register 가 경고: "23 features 가 부족하면
   추가, but 풀 alpha158 은 over-engineering".

D. **Strategy 구조 변경 (Path B)**: rank-based selection (top decile equal
   weight, monthly rebalance) — standalone JT 12-1 momentum 이 1.21 sharpe
   를 보여준 패턴. bloasis 의 threshold-based + cross-section z-score
   architecture 자체를 갈아엎음. 큰 작업.

E. **Halt**: mission 의 정직한 옵션. 17 PRs / 5 개월 작업, 데이터 기반
   결정.

## Acceptance Gate 평가

| 임계 | Target | Rule (2022-2024) | ML (2022-2024) |
|---|---:|---:|---:|
| median_alpha_annualized ≥ -0.005 | 0% | -27.4% ❌ | **-22.9% ❌** |
| median_sharpe_vs_spy ≥ 1.0 | 1.0 | -0.24 ❌ | **+0.04 ❌** |
| median_max_dd_ratio_to_spy ≤ 0.85 | 0.85 | 0.56 ✅ | 0.49 ✅ |
| walk_forward_min_folds ≥ 5 | 5 | 6 ✅ | 6 ✅ |
| **passed_acceptance** | TRUE | **NO** | **NO** |

ML 가 sharpe / alpha 둘 다 acceptance 임계 한참 미달.

## Decision: Mission Halt

Phase 2 design lockin §"Worst case":

> sharpe < 0.6 → mission "halt" 정직 결정. 6개월 작업이지만 명확한
> evidence 기반.

ML sharpe **+0.04** << 0.6.

**권고**: paper trading 진입 보류 (mission M3 차단). Phase 2 ML pipeline
인프라는 보존 (PR13-16 코드 자산). 이후 작업은 strategy redesign or
**프로젝트 일시 중단** 둘 중 하나.

## What survives

PR13-17 의 코드 자산은 의미 있음:
- `feature_log` writer + ML training pipeline + ML scorer + SHAP rationale
  → **재현 가능한 ML factor research 인프라**
- 23 features × 60만 labeled rows DB → 미래 strategy redesign 시 재사용
- `bloasis label-features`, `bloasis ml train` CLI → ad-hoc experiment
  workflow

mission M3 못 진입했지만 인프라 자체가 학습 자산.

## 다음 액션 (사용자 결정 필요)

1. **Halt + retrospective**: 정직한 마무리. docs/research/Phase2_Postmortem.md
   작성. 무엇이 falsified 됐는지 정리. Phase 1 Exit Gate 통과 못 한 첫
   strategy 로 기록.
2. **Strategy redesign (Path B)**: rank-based top-decile + JT 12-1 standalone
   pattern bloasis 에 통합. 큰 architectural 작업이지만 standalone pilot
   sharpe 1.21 evidence 강함.
3. **Hyperparameter exploration (D 위험)**: hyperparams + feature 추가 +
   per-fold retraining. Phase 2.5 deferred work.
4. **프로젝트 일시 중단**: mission halt 옵션 발동. 다른 우선순위 (BSVibe
   등) 로 시간 재배분.

추천: **1 (halt + retrospective) → 2 (redesign) 검토**. 데이터로 입증된
신호 (JT 12-1 standalone) 있으니 "halt 영구" 가 아닌 "halt 까지 일시정지
+ 다음 사이클 redesign 고려" 가 자연스러움.

## 산출물 위치

- `docs/research/Phase2_Final_Measurement_2026-05-07.md` (this doc)
- DB: `bloasis.db` run_ids 1-3
- model: `/tmp/pr17_model.pkl` + `pr17_model.json` sidecar
- backtest logs: `/tmp/bt-pr17-rule.log`, `/tmp/bt-pr17-ml.log`,
  `/tmp/bt-pr17-rule-22-24.log`
- Phase 2 design: `docs/research/Phase2_ML_Design_Lockin_2026-05-07.md`
- 관련 PR12 측정: `docs/research/PR12_Measurement_2026-05-07.md`
