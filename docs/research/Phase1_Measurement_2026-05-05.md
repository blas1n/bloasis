# Bloasis Phase 1 Exit Gate — Measurement (2026-05-05)

PR10 머지 전 worktree (`pr10/sp500-loader-fix`) 에서 첫 풀 S&P 500 walk-forward
백테스트 실행 완료. mission.md 의 "S&P 500 × 5+ years" 요건 충족하는 첫 측정값.

## 측정 조건

- 코드: `pr10/sp500-loader-fix` HEAD `99394a7`
  - PR10 universe loader fix (GitHub API auto-discovery)
  - + 백테스트 pre-fetch resilience (delisted/404 symbol skip)
- Universe: `bloasis universe show sp500_historical --as-of 2024-12-31` → **503 종목**
  (자동 발견된 최신 fja05680 snapshot `01-17-2026`)
- 실제 fetch 성공: **490/503 종목** (13 skipped, see below)
- 기간: `2019-01-01 .. 2024-12-31` (6 년)
- Walk-forward: train 365d / test 120d / step 120d → **15 folds**
- Config: `configs/baseline.yaml` (rule scorer, sentiment NaN by L007)
- Run id: `1` / `e458fbafd3c1` / name `phase1-exit-gate-sp500-v1`

## 결과 (acceptance gate)

| | 측정값 | 임계 | 결과 |
|---|---:|---:|:---:|
| `walk_forward_min_folds` | 15 | ≥ 5 | ✅ PASS |
| `median_alpha_annualized` | **-0.1826** | ≥ -0.005 | ❌ FAIL |
| `median_sharpe_vs_spy` | **0.303** | ≥ 1.000 | ❌ FAIL |
| `median_max_dd_ratio_to_spy` | 0.463 | ≤ 0.850 | ✅ PASS |
| **passed_acceptance** | | | **NO** |

다른 보조 지표:
- median_total_return: **-0.0068** (-0.68%)
- median_spy_total_return: +0.0564 (+5.64%)
- final equity: $10,213 (시작 $10,000)
- annualized: -0.35%
- sharpe (vs cash, not SPY): 0.0085
- max DD: -3.59%
- win rate: 33.74%
- total trades: 4,273

## Fold 별 (15 folds)

| fold | test period | alpha | sharpe | DD/SPY | trades |
|---:|---|---:|---:|---:|---:|
| 0 | 2020-01-02..2020-04-30 | +0.176 | -1.41 | 0.19 | 226 |
| 1 | 2020-05-01..2020-08-28 | -0.762 | 1.92 | 0.33 | 329 |
| 2 | 2020-08-29..2020-12-26 | -0.190 | -0.03 | 0.51 | 270 |
| 3 | 2020-12-27..2021-04-25 | -0.465 | -0.58 | 0.92 | 318 |
| 4 | 2021-04-26..2021-08-23 | -0.183 | 1.17 | 0.43 | 307 |
| 5 | 2021-08-24..2021-12-21 | -0.181 | -1.35 | 0.77 | 344 |
| 6 | 2021-12-22..2022-04-20 | +0.070 | -1.14 | 0.46 | 331 |
| 7 | 2022-04-21..2022-08-18 | +0.027 | -0.71 | 0.29 | 190 |
| 8 | 2022-08-19..2022-12-16 | +0.298 | 0.89 | 0.18 | 188 |
| 9 | 2022-12-17..2023-04-15 | -0.269 | 0.51 | 0.38 | 242 |
| 10 | 2023-04-16..2023-08-13 | -0.275 | -0.46 | 0.79 | 369 |
| 11 | 2023-08-14..2023-12-11 | -0.140 | -1.21 | 0.46 | 330 |
| 12 | 2023-12-12..2024-04-09 | -0.276 | 2.49 | 0.98 | 260 |
| 13 | 2024-04-10..2024-08-07 | -0.128 | -2.09 | 0.56 | 342 |
| 14 | 2024-08-08..2024-12-05 | -0.430 | 2.15 | 0.30 | 227 |

Alpha 양수는 4 folds (0, 6, 7, 8). 대부분 음의 alpha. Sharpe vs SPY 도 분산
크고 일관된 outperformance 없음.

## Skipped symbols (13)

| symbol | reason |
|---|---|
| ANSS | yfinance 404 (Synopsys 인수 2024) |
| BF.B | "no data" (yfinance 는 `BF-B` 사용) |
| BRK.B | "no data" (yfinance 는 `BRK-B` 사용) |
| DAY | rename (Ceridian → Dayforce) |
| DFS | acquired (Discover → Capital One pending) |
| FI | rename (Fiserv FISV → FI) |
| HES | acquired (Chevron pending) |
| IPG | acquired (Omnicom pending) |
| JNPR | acquired (HPE 2025) |
| K | rename (Kellogg → Kellanova) |
| MMC | "no data" (실패 원인 불명, Marsh McLennan 은 살아있음) |
| PARA | rename (VIAC → PARA) |
| WBA | going private 진행중 |

대부분 yfinance 의 ticker symbol mapping issue. Phase 2 에서 alias resolver
도입 시 회복 가능 (예: `BF.B → BF-B`, `BRK.B → BRK-B`). MMC 같은 케이스는
별도 조사 필요.

## 비교: 5심볼 baseline (PR9 시점)

| | 5심볼 | 풀 S&P 500 | 변화 |
|---|---:|---:|---|
| folds | 12 | 15 | + |
| median alpha | -0.185 | **-0.183** | ≈ 동일 |
| median sharpe | 0.50 | **0.30** | ↓ 더 나빠짐 |
| median DD/SPY | 0.10 | 0.46 | ↑ 더 위험 |
| total trades | 70 | 4,273 | ×60 |

**가설 기각**: "5심볼 결과가 sample bias로 luck이 나빴고 풀 universe 면 더 나아짐" — 틀림. 풀 universe 에서 sharpe 가 오히려 0.50 → 0.30 으로 악화. Rule scorer
는 large-universe 에서도 SPY 를 못 이김. 5심볼 결과가 bias가 *덜* 한 sample
이었던 것.

## 진단 신호

1. **trade churn 매우 높음**: 6년 4,273 trades = 평균 1.6 trades/day. 490 종목
   universe 에서 0.3% turnover/day. Walk-forward fold 마다 200-370 trades.
   포지션 holding period 가 너무 짧고 transaction cost 누적 가능. 개선 여지:
   re-entry threshold, min holding period, signal hysteresis.
2. **win rate 33.74%**: signal precision 낮음. 33% × asymmetric upside 면 양수
   expectancy 가능하지만 현재 total return -0.68% 로 그것도 안 됨.
3. **drawdown 양호 (0.46)**: risk gate 는 잘 작동 중. 이건 보존할 자산.
4. **fold 별 분산 큼**: alpha 가 +0.298 (fold 8) 부터 -0.762 (fold 1) 까지.
   regime detection 이 실제로 effective 하지 않거나, regime multiplier 가
   잘못 튜닝되어 잘못된 시점에 leverage up.
5. **2020 Q2 fold 1 -76% alpha**: COVID 회복기에 SPY 가 V자 반등할 때 우리
   scorer 가 underperform. 너무 많은 종목 보유 또는 너무 보수적 진입. regime
   = "recovery" 시 entry threshold 가 너무 높을 가능성.

## Path D 파일럿 1 — Momentum-only (rule scorer)

**Run 2** (`pilot-momentum-only-v1`, config `pilot-momentum-only.yaml`):
같은 백테스트 엔진, weights={momentum: 1.0, others: 0}, regime_multipliers
비활성. 즉 *기존 단기 momentum composite (momentum_20d + momentum_60d +
rsi_14)* 만 활성화.

| 메트릭 | run 1 baseline | **run 2 momentum-only** | 변화 |
|---|---:|---:|---|
| median_alpha_annualized | -0.183 | **-0.127** | +5.5pp |
| median_sharpe_vs_spy | 0.30 | **0.50** | +67% |
| median_max_dd_ratio_to_spy | 0.46 | **0.32** | 더 안전 |
| median_total_return | -0.0068 | **+0.0087** | 음→양 |
| n_trades | 4273 | 5052 | +18% |
| passed_acceptance | NO | NO | 둘 다 fail |

Sharpe 1.65x 개선. 양수 fold 4→5개. **방향성 맞음** — multi-composite blend
가 momentum 신호를 dilute. 하지만 단기 momentum 만 으로 0.50 sharpe 가
ceiling. 기존 rule scorer 시스템에서 이게 한계.

## Path D 파일럿 2 — 12-1 Jegadeesh-Titman momentum (script)

bloasis 백테스트 엔진 우회한 standalone pandas 스크립트 (`/tmp/jt_momentum_pilot.py`).
캔노니컬 academic momentum: 12개월 - 1개월 lookback (`lookback=252, skip=21`),
top-10% equal-weight, monthly rebalance, no costs/slippage/risk-gate.

**목적**: ceiling test — "이 universe 에서 정통 momentum signal 이 SPY 를
이길 잠재력이 있는가?" upper bound 측정.

| 메트릭 | run 1 | run 2 | **JT 12-1 (script)** |
|---|---:|---:|---:|
| annualized_alpha | -0.183 | -0.127 | **+0.076** |
| sharpe (vs SPY ratio) | 0.30 | 0.50 | **1.209** |
| max_dd_strategy | -0.036 | -0.045 | -0.391 |
| max_dd_spy | -0.358 | -0.358 | -0.341 |
| max_dd_ratio_to_spy | 0.46 | 0.32 | **1.145** |
| total_return_strategy | -0.0068 | +0.0087 | **+1.8884** |
| total_return_spy | +0.056 | +0.056 | +0.993 |

(주: run 1/2 의 max_dd_strategy 가 작은 건 70% SPY core 가 아닌 *strategy
slice 만* 측정하는 백테스트 구조 + entry threshold 0.65 로 상당 기간 cash
보유 때문. JT 스크립트는 strategy 100% 투자.)

**핵심 발견**:

1. **acceptance gate sharpe 임계 (1.0) 통과**: 1.209. **alpha 임계 (-0.005)
   통과**: +0.076. 두 핵심 임계 둘 다 첫 통과.
2. **DD 임계 (0.85) FAIL**: 1.145. 100% 투자 + COVID 2020-Q1 + 모멘텀 이름은
   대부분 growth → 큰 drawdown 노출.
3. **cost 미반영 caveat**: 70 rebalances × ~50 names × 2 (sell+buy) ≈ 7000
   trades. 5bps slippage 가정 시 ~3.5%/yr cost penalty. alpha +7.6% → 실제
   ~+4%. 여전히 양수.
4. **walk-forward 미반영 caveat**: 단일 2019-04 .. 2024-12 윈도우. fold-by-fold
   분산은 미측정. 일관성 검증은 다음 단계.
5. **선정 종목 sanity**: 첫 rebalance (2019-04) AMD, ENPH, LULU, PAYC 등
   당시 상위 momentum. 마지막 rebalance (2024-11) NVDA, PLTR, KKR, RCL 등
   AI/leverage 테마. 시기별 적절한 종목 회전 확인.

**결론**: 이 universe 에 정통 momentum factor signal 이 **명백히 존재**.
기존 rule scorer 가 이를 다른 factors (value/quality/sentiment) 로 dilute.

## 다음 결정 (Path B / C / D)

이 측정값 을 input 으로:

### Path B — Baseline tuning (research, ~1-2주)

- entry/exit threshold, regime multiplier 데이터 기반 튜닝
- walk-forward in-sample 튜닝 + out-of-sample 평가 구조 (full-history
  optimization 금지 [CLAUDE.md §4](https://github.com/blas1n/bloasis/blob/main/CLAUDE.md))
- min holding period, signal hysteresis 추가 (trade churn 감소)
- **위험**: rule scorer 의 fundamental capacity 가 SPY 를 1.0 sharpe 로
  이길 만큼 있는지 의심. Sharpe 0.30 → 1.0 은 3x 개선 — tuning 으로
  도달 가능한 범위가 아닐 수 있음.

### Path C — Phase 2 ML scorer (~4-6 PR, 2-4주)

- `feature_log` forward-return labeling job (`label_5d`, `label_20d`)
- LightGBM training pipeline (time-series CV)
- `MLScorerStub` → 실제 LightGBM predict 교체
- SHAP rationale
- 이게 mission.md 의 "Phase 2 ML" 본격 작업
- **장점**: rule scorer 한계를 학습 모델이 보완. feature engineering 자체는
  Phase 1 에서 이미 잘 됨 (22 features × 7 composites).
- **위험**: 라벨링 + 학습 인프라 자체가 큰 작업. 가치 검증 전에 매몰비용 큼.

### Path D — 전략 단순화 / 리셋

- 22 features 너무 넓음. 단일 신호 (12-month momentum 또는 mean reversion)
  로 reset 후 SPY beat 가능한지 먼저 확인
- mission.md "Reset, simplify, or halt" 옵션
- **장점**: 빠른 hypothesis test. 단순 momentum strategy 가 SPY 를 못 이기면
  복잡한 ensemble 도 못 이김 (ceiling test).
- **단점**: Phase 1 에 투입한 22 features 의 일부를 버림 (재활용 가능하지만)

## 추천 (업데이트됨 — 두 pilots 후)

~~Path D 먼저~~ → **두 파일럿 후 명확해짐**: Path D 의 ceiling test 통과.
정통 momentum factor 가 이 universe 에 alpha 가짐을 입증.

**다음 작업 (PR12 후보 — 정식 통합)**:

1. **`momentum_252_21` feature 정식 통합**:
   - `FeatureVector` 에 필드 추가, `FEATURE_COLUMNS` append, `feature_version`
     bump (1 → 2)
   - `FeatureExtractor.extract()` 에서 `momentum(close, 252, skip=21)` 호출
   - `feature_log` schema 컬럼 추가 (alembic 없으니 `MetaData.create_all()` —
     기존 DB 의 경우 column add migration 필요)
   - 단위 테스트
2. **`long_momentum` composite 추가**:
   - `COMPOSITE_SPEC` 에 `("momentum_252_21", +1)` 단일 constituent 등록
   - `CompositeVector` 에 필드 추가
   - `WeightsConfig` schema 에 `long_momentum: float = 0.0` 추가
   - `regime_multipliers` 도 `long_momentum` 키 허용 (Literal 또는 dict 자유)
3. **신규 `configs/baseline-v2.yaml`**:
   - weights: `long_momentum=0.6, momentum=0.1` (단기는 보조), 나머지 minor
   - regime_multipliers: crisis 시 long_momentum 0.5x, bull 시 1.3x 정도
   - 기타는 baseline.yaml 동일
4. **풀 walk-forward 백테스트** (with bloasis costs/slippage/risk gate):
   - run 3 = `phase1-exit-gate-sp500-v2`
   - 기대치 (script 결과 - cost penalty - 70/30 dilution 미적용 캐비어트):
     - sharpe 1.0+ 첫 통과 가능성 높음
     - DD 임계 0.85 통과는 risk gate (VIX > 40 → block buys) 가 COVID 2020
       기간 작동하면 가능
5. **acceptance gate 통과 시**: paper trading 그린라이트, mission.md M3 (live
   trading) 조건부 진입.

**Path B (tuning)**: PR12 위에 follow-up. entry/exit threshold + regime
multiplier 데이터 기반 미세조정. PR12 가 이미 acceptance pass 면 marginal
gain. PR12 가 borderline 이면 critical.

**Path C (Phase 2 ML)**: 우선순위 **하향**. 학습 모델 없이 acceptance gate
통과 가능 path 가 보임. ML 은 momentum + value + quality blend 의 *학습된*
weights 로 추가 alpha capture 시 가치 있음 — 하지만 그건 Phase 1 통과 후의
Phase 2 본 작업.

## 부록: 재현

```bash
cd /Users/blasin/Works/bloasis/wt/pr10-sp500-loader-fix
uv run bloasis runs show 1
```

또는 다른 worktree 에서:

```bash
git fetch && git checkout pr10/sp500-loader-fix
uv sync --extra dev --extra data --extra ta --extra llm --extra broker
uv run bloasis init-db
COLUMNS=100000 uv run bloasis universe show sp500_historical --as-of 2024-12-31 \
    | tail -1 | tr -d ' ' > /tmp/sp500.txt
bash -c '
SYMBOL_ARGS=""
while IFS= read -r sym; do
  [ -n "$sym" ] && SYMBOL_ARGS="$SYMBOL_ARGS -s $sym"
done < <(tr "," "\n" < /tmp/sp500.txt)
uv run bloasis backtest \
    --config configs/baseline.yaml \
    --start 2019-01-01 --end 2024-12-31 \
    $SYMBOL_ARGS \
    --train-days 365 --test-days 120 --step-days 120 \
    --name phase1-exit-gate-sp500-v1
'
```

소요: cache cold start ~25-35 분 (yfinance 503 fetch + walk-forward 15 folds).
캐시 hit 시 ~2-3 분.
