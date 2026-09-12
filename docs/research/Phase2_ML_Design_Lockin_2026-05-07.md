# Bloasis Phase 2 ML — Design Lock-in (2026-05-07)

## Context

Phase 1 measurement (run 1) → acceptance gate FAIL.
PR12 multi-factor blend hypothesis falsified across 3 windows
(sharpe 0.46 → 0.35 → -0.24). Bloasis composite framework 의 equal-mean
dilution 이 구조적 한계로 확인됨.

**Phase 2 ML 진행** (옵션 A). Hypothesis: ML scorer 가 cross-section 의
동적 가중치 학습 + non-linear feature interaction 으로 rule scorer 의
ceiling (0.50) 을 0.7-0.9 sharpe 로 상승.

Reference: Kelly-Pruitt-Su (RFS 2020) "Empirical Asset Pricing via ML" —
ML 이 linear factor 대비 30-40% sharpe improvement reported.

## 목표

- **acceptance gate 통과**: median_sharpe_vs_spy ≥ 1.0, alpha ≥ -0.5%,
  DD ratio ≤ 0.85
- **realistic floor**: AQR live fund 1.25 sharpe deflate 35% → bloasis
  실용 0.7-0.9 sharpe (Quant_References.md §5)
- **PR12 인프라 재활용**: 5 features (`momentum_252_21`, `roc_120`,
  `kbar_kmid2/ksft2`, `corr_pv_20`) + `regime_overlay` 모두 ML 입력/오버레이

## Scope (PR13-17, ~2-3주)

### PR13 — Forward-return labeling job

`feature_log` 테이블의 `forward_return_5d`, `forward_return_20d`,
`forward_return_60d` 컬럼을 채우는 CLI 명령 + storage migration.

**구현**:
- 신규 CLI: `bloasis label-features [--lookback-days N]`
- 매일 (또는 주별) 실행: `feature_log` 의 `label_filled_at IS NULL`
  partial index 사용해 unlabeled rows scan
- 각 (symbol, timestamp) 에 대해 OHLCV cache 에서 forward returns 계산:
  - `label_5d = close[t+5] / close[t] - 1`
  - `label_20d = close[t+20] / close[t] - 1`
  - `label_60d = close[t+60] / close[t] - 1`
- `label_filled_at = now()` 표시
- delisted/missing forward bars → NULL 그대로

**TDD scope**:
- `test_writers.py`: forward return 계산 단위 테스트
- `test_cli.py`: 새 명령 smoke
- 시나리오: NaN forward returns (symbol 끝), partial fills (5d 만 있고 60d 없음)

**예상 작업**: 1-2일.

### PR14 — LightGBM training pipeline

`bloasis ml train --feature-version 2 --label label_20d` CLI 명령.
LightGBM regressor with purged time-series CV (Lopez de Prado).

**구현**:
- 신규 모듈 `bloasis/ml/training.py`
- 의존성 추가: `lightgbm`, `shap` (이미 pyproject `--extra ml` 에 있음 확인 필요)
- Pipeline:
  1. `feature_log` 에서 `feature_version=2 AND label_filled_at IS NOT NULL`
     row load
  2. 23 features (X) + label_20d (y, default)
  3. Purged + embargoed walk-forward CV (Quant_References.md §4 CPCV
     변형 — k=5 folds 우선, full CPCV 는 PR17)
  4. LightGBM regressor (default hyperparams: max_depth=6, num_leaves=31,
     learning_rate=0.05, n_estimators=500, early_stopping_rounds=50)
  5. Per-fold IC (information coefficient = corr(predictions, labels)),
     average IC report
  6. Refit on all train data → save `model.pkl` + feature importance + metadata
- Output: `~/.cache/bloasis/models/<config_hash>_<feature_version>_<label>.pkl`

**Hyperparam philosophy**: minimal initial tuning. PR12 측정처럼 hard-coded
weights 의 over-fit 위험. 기본값에서 sharpe 도달 못하면 hyperparams 만 만지
지 말고 architecture 고민.

**TDD scope**:
- `test_ml_training.py`: synthetic data 로 train pipeline 단위 테스트
- IC 양수 가정 (synthetic data 가 학습 가능하게 구성)
- model serialization round-trip
- mypy strict (LightGBM types)

**예상 작업**: 3-4일.

### PR15 — MLScorerStub → real LightGBMScorer

`bloasis/scoring/scorer.py` 의 `MLScorerStub` 을 실제 model loading +
predict 으로 교체.

**구현**:
- `LightGBMScorer.__init__(model_path: Path)` — pickle load
- `LightGBMScorer.score(feature_vectors: list[FeatureVector]) -> list[float]`:
  cross-section batch predict, 결과를 [0, 1] unit-score 로 z-score → cdf 매핑
- 기존 rule scorer 와 같은 인터페이스 (signal/scorer.py의 Scorer protocol)
- Config: `scorer.type = "ml"`, `scorer.ml_model_path` 활성화

**Engine 와이어링**: 기존 `scorer_factory: type[Scorer] | None = None` 이
이미 있음 ([engine.py:96](~/Works/bloasis/bloasis/backtest/engine.py)).
`MLScorer` 통과 시 cross-section batch processing 활용.

**TDD scope**:
- `test_scorer.py`: ML scorer mock model 로 score → unit-score 매핑 검증
- `test_backtest_engine.py`: ML scorer 와 backtest 통합 — 동일 데이터로 rule
  vs ML 다른 결과 (회귀 테스트)
- Cross-section batch performance 측정 (모델당 1만 회 predict 미만)

**예상 작업**: 2-3일.

### PR16 — SHAP rationale + backtest 통합

각 entry 의 ML 점수를 SHAP value 로 분해하여 `Rationale` 객체 생성.
사용자가 "왜 이 종목 매수?" 질문에 ML attribution 제공.

**구현**:
- `bloasis/scoring/rationale.py` 의 `Rationale` 확장 또는 신규 `MLRationale`
- LightGBM SHAP explainer (`shap.TreeExplainer`)
- Top 5 SHAP contributors per entry
- `bloasis runs show <id>` UI 에 SHAP top-5 표시

**TDD scope**:
- SHAP value 계산 단위 테스트 (synthetic model)
- backtest 의 fold_fills 에 SHAP 첨부 검증

**예상 작업**: 2일.

### PR17 — 풀 walk-forward 측정 + acceptance gate

PR13-16 완료 후, ML scorer 로 풀 backtest 재측정.

**Pre-requisite**:
- PR13: `feature_log` 라벨링 완료 (수개월 ~ 6년 데이터)
- PR14: LightGBM model 학습 완료
- PR15: ML scorer wiring 완료

**측정**:
1. Single-window: 2019-2024 mom-only-v2 와 directly compare
2. Multi-window: 2014-2019, 2019-2024, 2021-2024 (PR12 동일 패턴)
3. CPCV (Quant_References.md §4) — 6 blocks, drop 2: 15 combinations
4. Cost sensitivity: 0/5/15/25 bps round-trip

**기대치**:
- Single-window 2019-2024: sharpe 0.7+ (PR12 mom-only 0.50 + ML lift)
- Multi-window: pre-COVID 0.6+, post-COVID 0.4+ (시간 감쇠 역전 가능성)
- CPCV: 60%+ combos pass sharpe ≥ 1.0
- Acceptance gate: 통과 가능성 60-80% (Kelly-Pruitt-Su 30-40% improvement
  레퍼런스 + bloasis 구조적 disadvantage 감안 다소 낮춤)

**Scenarios**:
- **Best**: acceptance pass → mission M3 (paper trading) 진입
- **Likely**: sharpe 0.7-0.9 borderline → tuning PR (ML hyperparams,
  feature engineering) 1-2회 후 재측정
- **Worst**: sharpe < 0.6 → strategy halt 정직 결정 (mission "halt" 옵션)

**예상 작업**: 3-4일 (측정 ~1일 + 결과 doc + decision).

## 주요 의사결정 정리

### Q1. ML 모델 선택

**LightGBM** 확정. 이유:
- mission Phase 3 stub 이 이미 LightGBM 가정 (CLAUDE.md §6)
- Native NaN handling (pandas float64 NaN 그대로 처리)
- Tabular data 의 SOTA (Kelly et al. 2020 + 산업 표준)
- SHAP TreeExplainer 무료 (interpretability)
- XGBoost vs LightGBM: LightGBM 이 약간 빠르고 leaf-wise growth → 정확도
  비슷
- Neural nets / transformers: tabular factor data 에 over-engineering
  (Phase 3+ 후보)

### Q2. Label 선택

**`label_20d`** (4-week forward return) primary. 이유:
- monthly rebalance 의도 (signal half-life)
- noise vs signal balance: 5d 너무 noisy, 60d 너무 lagged
- AQR / qlib 표준 lookahead

PR14 는 5d/20d/60d 다 label 하되 default training 은 20d. 향후 multi-target
ensemble 검토 가능.

### Q3. CV 전략

**Purged walk-forward CV** (PR14) → **CPCV** (PR17 측정 시).

- PR14 단순 walk-forward: 5 folds (train 80% / test 20% rolling)
- 각 fold 사이 21일 embargo (label_20d 가 future 20d 사용하므로)
- PR17 CPCV: full 평가용. PR14 는 development.

### Q4. Feature engineering 전략

**현재 23 features 만 사용** (PR12 features 포함). 이유:
- ML 이 비선형성 학습 → 기존 features 의 "더 좋은 weighting" 시도
- 추가 features (qlib 158 등) PR12 의 cherry-pick 후 다음 Phase
- Over-engineering 회피: 23 features 가 충분한지 ML 결과로 검증

**예외**: training data 부족 (3-4년) 시 `bloasis label-features` 의 lookback
연장 검토.

### Q5. Cross-section vs Time-series ML

**Pooled cross-section** 채택. 모든 (symbol, date) row 를 하나의 dataset
으로 학습. 이유:
- 23 features × 490 symbols × ~1500 days = ~1700만 rows. 충분한 학습량.
- Symbol-specific 모델은 small-cap 데이터 부족.
- Industry standard (Kelly et al., qlib 등 모두 pooled).

### Q6. Production model retraining 주기

**연 1회** (mission M3 paper trading 시), **PR17 측정 시 1회**. PR15 의
walk-forward backtest 는 CV 의 각 fold 마다 retrain. 빈번한 retrain 은
over-fit risk + compute cost.

### Q7. Regime overlay (PR12 의 자산) 활용

**유지**. ML scorer 위에 그대로 size_pct multiplier. ML 이 entry signal,
overlay 가 portfolio risk control. 분리된 concern.

DD ratio 0.85 통과는 overlay 가 critical path (PR12 measurement 0.56 → 0.33
검증).

## 위험 등록

| 위험 | 완화 |
|---|---|
| Training data 부족 (~6년 = 1500 days × 490 = 735k rows) → over-fit | Walk-forward CV + early stopping. CPCV 측정. |
| ML scorer 가 rule scorer 보다 못함 → option A 폐기 | PR15 단계에서 rule vs ML 직접 비교. fail 시 PR16-17 보류 + strategy halt 결정 |
| LightGBM hyperparam 과민 → 측정 결과 노이즈 | 기본 hyperparams 고정. tuning PR 별도 분리 (PR17 후) |
| Feature drift (PR12 features 가 train 후반에 noise) | feature_version 2 만 학습. v1 데이터 (~2024 이전) 는 모두 v2 로 재라벨. |
| Cap-weighted SPY 구조적 disadvantage 그대로 | ML 이 mega-cap tech 에 자동 가중치 학습 가능. equal-weight 와는 다름. |
| Look-ahead bias in ML pipeline | Purging + embargo. test_extractor.py 의 look-ahead test pattern 따라 ML training pipeline 도 회귀 테스트. |
| LightGBM model 직렬화 경로 (Phase 3 자동화 시) | model file 을 cache_dir 에 저장. config_hash + feature_version 키. |

## Acceptance criteria (Phase 2 종료 게이트)

PR17 측정 시:
- [ ] `median_sharpe_vs_spy ≥ 1.0` (current 0.30, target 1.0+)
- [ ] `median_alpha_annualized ≥ -0.005` (current -0.183, target +0.02-0.07)
- [ ] `median_max_dd_ratio_to_spy ≤ 0.85` (current 0.46, overlay 적용 시 ≤ 0.4)
- [ ] CPCV 60%+ combos pass sharpe ≥ 1.0
- [ ] Multi-window: pre-COVID + post-COVID 모두 sharpe > 0.5

통과 시 → mission M3 (paper trading 1-3개월) 진입.

## 산출물 위치

- 본 문서: `docs/research/Phase2_ML_Design_Lockin_2026-05-07.md`
- PR12 측정: `docs/research/PR12_Measurement_2026-05-07.md`
- 학술 reference: `docs/research/Quant_References.md`,
  `Research_DM_Dynamic_Momentum.md`, `Research_AQR_Factor_Blend.md`,
  `Research_Qlib_Features.md`

## 다음 액션

1. **이 doc 사용자 confirm** (모델 선택 / label / CV / 작업 순서)
2. PR12 (#29) 머지 wait — Phase 2 의 base
3. PR13 worktree 생성 (`pr13/forward-return-labeling`)
4. TDD 순서대로 구현 (각 PR 의 §TDD scope)
5. 측정 + 결과 doc 별도 (`docs/research/Phase2_<step>_Measurement_<date>.md`)
