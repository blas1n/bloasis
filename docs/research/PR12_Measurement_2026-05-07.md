# Bloasis PR12 — Measurement & Decision (2026-05-07)

## TL;DR

PR12 (`pr12/momentum-blend-overlay`) 구현 완료 — 5 features + composites
업데이트 + DM/BSC regime overlay + AQR-style baseline-v2.yaml weights.

**5개 백테스트 측정 모두 acceptance gate FAIL**. 시간 감쇠 트렌드 확인 —
2014-2019 sharpe 0.46 → 2019-2024 0.35 → 2021-2024 sharpe **-0.24**.

**결정**: PR12 의 multi-factor blend 가설은 falsified. **Phase 2 ML 본격
진행** (옵션 A). PR12 의 코드 자산 (features, overlay, schema, tests) 은
ML 인프라의 input feature 로 그대로 활용.

## 측정 요약 (5 runs × 3 시간 윈도우)

### 동일 윈도우 (2019-01-01 .. 2024-12-31), 4 configs

| Run | Config | Sharpe | Alpha | DD/SPY | n_trades |
|---:|---|---:|---:|---:|---:|
| 1 | baseline.yaml (PR9 weights, no PR12 features) | 0.30 | -0.183 | 0.46 | 4273 |
| 2 | mom-only-PR11 (PR10 worktree) | **0.50** | -0.127 | 0.32 | 5052 |
| 3 | baseline-v2.yaml (AQR weights + overlay ON) | 0.23 | -0.168 | 0.35 | 3133 |
| 4 | pilot-mom-only-v2 (mom=1.0 + PR12 features + overlay ON) | 0.35 | -0.157 | 0.33 | 10239 |
| 5 | pilot-mom-only-v2 (overlay OFF) | 0.35 | -0.154 | **0.56** | 4760 |

**관찰**:
- Run 4 vs Run 2: PR12 features **diluted** momentum signal (sharpe 0.50 →
  0.35). `momentum_252_21` + `roc_120` 가 기존 `momentum_20d/60d/rsi_14` 와
  equal-mean 으로 묶이며 long-term signal 1/5 로 묻힘.
- Run 4 vs Run 5: overlay 는 **alpha 중립, DD 효과 명확** (DD 0.56 → 0.33).
  설계 의도대로 작동.
- Run 3: AQR weights 가 momentum 0.22 만 주니 PR12 features 의 dilution 위에
  추가 dilution. 가장 나쁨.

### 다중 시간 윈도우 (mom-only-v2 + overlay ON)

| 윈도우 | Sharpe | Alpha | DD | n_folds | 종목 (skipped) |
|---|---:|---:|---:|---:|---|
| Pre-COVID 2014-2019 | **0.46** | -0.107 | 0.45 | 15 | 370 (127/497 skipped, 25%) |
| Current 2019-2024 | 0.35 | -0.157 | 0.33 | 15 | 490 (13/503, 3%) |
| Post-COVID 2021-2024 | **-0.24** | -0.207 | 0.37 | 9 | 453 (52/505, 10%) |

**시간 감쇠 명확**: 0.46 → 0.35 → -0.24. 2020 COVID 가 single anomaly 가
아닌 *일관된 strategy 약화*. Pre-COVID 의 sharpe 0.46 도 acceptance 1.0 에
한참 미달, 그리고 25% survivorship bias 감안하면 실제는 더 낮음.

**Post-COVID 9 folds 중 8개에서 alpha 음수** (-0.142 ~ -0.469). AI rally
시기 일관 underperform.

## Root cause — Bloasis composite framework 의 구조적 한계

JT 12-1 standalone script (`/tmp/jt_momentum_pilot.py`): same universe 같은
2019-2024 기간에 sharpe **1.21**, alpha **+7.6%**.

Bloasis mom-only (PR11): 동일 데이터 → sharpe **0.50**.

**3-4배 갭의 원인**:

1. **Equal-mean dilution**: bloasis composite system 은 cross-section z-score
   → unit score → 5 momentum constituents equal-mean. 핵심 `momentum_252_21`
   이 1/5 가중치. JT standalone 은 pure 12-1 만 사용.

2. **Threshold-based entry vs rank-based**: bloasis 는 `entry_threshold=0.65`
   넘는 모든 종목 매수. JT standalone 은 top 10% rank 만. Threshold 방식은
   cross-section 변동성에 따라 보유 종목 수가 변함 (5-100+).

3. **Cap-weighted SPY vs equal-weight strategy**: 2021-2024 AI rally 는 NVDA/
   MSFT/GOOGL 등 mega-cap 에 집중. SPY (cap-weighted) 는 자동 큰 비중. Bloasis
   는 모든 종목 equal weight → mid/small cap 손실 흡수.

4. **7 buckets × 23 features 의 noise**: 다양한 factor 가 cross-section 에서
   서로 신호 캔슬. JT standalone 은 단일 factor.

이건 **Bloasis 의 의도된 디자인 (rule-based 다양한 factor blend)** 의
trade-off. ML scorer 가 동적 가중치 학습 → equal-mean dilution 해소가
설계 의도의 다음 단계.

## PR12 자산 — Phase 2 ML 의 input

PR12 코드는 **부정적 측정 결과**에도 불구 **인프라 가치** 있음:

1. **5 신규 features** (`momentum_252_21`, `roc_120`, `kbar_kmid2`, `kbar_ksft2`,
   `corr_pv_20`): ML training 의 추가 feature columns. `feature_log` 에 자동
   저장됨. ML 이 동적으로 가중치 학습.
2. **`feature_version` 1 → 2 bump**: ML training 이 신규 feature 가진 row 만
   필터링하는 메커니즘 활성화.
3. **`regime_overlay.py`**: BSC + DM bear gate 모듈. ML scorer 위에 그대로
   적용 가능 (size_pct multiplier). DD 0.85 통과 critical path.
4. **`baseline-v2.yaml`**: ML training 의 weight 초기값 후보 (AQR-prior). 나쁜
   결과지만 ML 이 starting point 로 학습할 수 있음.
5. **`bloasis/scoring/derived.py`** kbar_kmid2/ksft2/corr_price_volume 헬퍼:
   재사용.
6. **`feature_log` schema** 5 신규 컬럼: ML 이 query 할 데이터 구조.
7. **433 tests / 88% coverage / mypy strict / TDD discipline**: 안정 base.

## 의사결정 — 옵션 A 채택 (Phase 2 ML)

### 추진 이유

- **Mission roadmap 자연 진행**: Phase 1 → Phase 2 (ML scorer)
- **PR12 자산 재활용**: 모든 코드가 ML pipeline 의 building blocks
- **Equal-mean dilution 해결**: ML 이 학습된 가중치로 자동 해결
- **JT 1.21 → realistic 0.7-0.9 sharpe** (cost + risk gate 적용 후) 도달
  가능 — Kelly-Pruitt-Su 2020 ML factor 페이퍼 sharpe 30-40% improvement
  레퍼런스
- **Phase 2 끝나도 acceptance gate 못 통과 시** → strategy halt 정직한 결정
  (mission "halt" 옵션). 그땐 명확한 evidence 기반.

### 폐기되는 가설

- ❌ "AQR multi-factor blend (rule-based hard weights) 로 acceptance pass"
  — falsified across 3 시간 윈도우
- ❌ "Multi-factor 가 single momentum 대비 alpha 안정화" — equal-weight
  dilution 으로 오히려 alpha 감소

### 다음 작업 PR13-17 scope

PR12 머지 (인프라 가치) → Phase 2 ML 본격:

- **PR13**: 라벨링 job (`bloasis label-features`) — `feature_log.forward_return_*`
  컬럼을 5d/20d/60d 후행 수익률로 채움. 일별/주별 cron.
- **PR14**: LightGBM training pipeline (`bloasis ml train`) — purged
  walk-forward CV (Lopez de Prado), feature importance, model 저장.
- **PR15**: `MLScorerStub` → 실제 `LightGBMScorer`. `bloasis/scoring/scorer.py`
  업데이트, model file 로드 + predict 와이어링.
- **PR16**: SHAP rationale + backtest 통합. ML scorer 의 entry 이유를 SHAP
  contributions 로 설명.
- **PR17**: 풀 walk-forward 측정 + acceptance gate. PR12 의 5개 measurement
  와 직접 비교. 통과 시 mission M3 (paper trading) 진입.

각 PR ~3-5일 작업, 총 ~2-3주.

## PR12 머지 결정

**Recommended: PR12 머지**.

이유:
- 코드 품질 (433 tests, mypy strict, TDD)
- Phase 2 ML 의 입력 인프라
- 음의 결과는 **strategy 가설 falsification** 이지 **코드 버그** 아님
- baseline-v2.yaml 은 deprecated 표시 + ML 학습용 prior 로 documented

**대안 (논의 가능)**: PR12 close + features 만 별도 PR 로 cherry-pick. 그러나
이건 작업 손실 + 더 많은 review overhead.

## 산출물 위치

- 측정 raw: bloasis SQLite DB `bloasis.db` (worktree 의 `pr12-momentum-blend-overlay`).
  `bloasis runs show <id>` 로 조회 (run_id 1-5).
- 백테스트 logs: `/tmp/bt-v2.log`, `/tmp/bt-mom-only-v2.log`, `/tmp/bt-no-overlay.log`,
  `/tmp/bt-precovid.log`, `/tmp/bt-postcovid.log`
- Universe lists: `/tmp/sp500_2014.txt`, `/tmp/sp500_2019.txt`, `/tmp/sp500_2021.txt`
- 종합 측정 데이터: 본 문서

## 재현 명령

```bash
cd ~/Works/bloasis/wt/pr12-momentum-blend-overlay  # 또는 머지 후 main

# Run 3 (baseline-v2 + AQR + overlay) 재현
uv run bloasis backtest --config configs/baseline-v2.yaml \
    --start 2019-01-01 --end 2024-12-31 \
    $(cat /tmp/sp500_symbols.txt | tr ',' '\n' | sed 's/^/-s /' | xargs) \
    --train-days 365 --test-days 120 --step-days 120 \
    --name reproduce-pr12-v1

# Run 4/5: pilot-mom-only-v2 ± overlay (configs/pilot-mom-only-v2*.yaml)

# Pre-COVID
uv run bloasis backtest --config configs/pilot-mom-only-v2.yaml \
    --start 2014-01-01 --end 2019-12-31 \
    $(cat /tmp/sp500_2014.txt | tr ',' '\n' | sed 's/^/-s /' | xargs) \
    --train-days 365 --test-days 120 --step-days 120

# Post-COVID
uv run bloasis backtest --config configs/pilot-mom-only-v2.yaml \
    --start 2021-01-01 --end 2024-12-31 \
    $(cat /tmp/sp500_2021.txt | tr ',' '\n' | sed 's/^/-s /' | xargs) \
    --train-days 365 --test-days 120 --step-days 120
```
