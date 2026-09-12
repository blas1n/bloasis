# Bloasis Phase 1/2 Postmortem (2026-05-07)

> Mission halt 정직 마무리. Phase 1 Exit Gate 통과 못 한 첫 strategy 로
> 기록. 17 PRs / 5 개월 작업의 학습 자산 정리 + 다음 사이클 redesign
> 검토 input.

## TL;DR

5 개월 / 17 PRs / 503 tests / 88% coverage 의 production-grade trading
research 인프라 완성. 그러나 **mission acceptance gate (median_sharpe_vs_spy
≥ 1.0) 통과하는 strategy 못 만듦**. ML scorer 까지 포함한 모든 변종
sharpe 1.0 미달.

핵심 발견: **bloasis 의 cross-section z-score → entry threshold 0.65
architecture 자체가 cap-weighted SPY 를 long-only equal-weight 로 이길
수 없는 구조적 한계**. JT 12-1 standalone (top decile rank, equal weight,
monthly rebalance) 이 동일 데이터에서 sharpe 1.21 → bloasis 의 신호 다이루션
경로를 우회하면 alpha 가 살아남는다는 명확한 evidence.

→ **Mission halt + 다음 사이클 redesign** (rank-based + 현대 AI factor
연구 통합).

## Phase 1/2 Timeline (2025-12 ~ 2026-05)

| Phase | Period | Key PRs | Outcome |
|---|---|---|---|
| Phase 1 (Foundation) | 2025-12 ~ 2026-04 | PR1-PR9 | 골격 완성: walk-forward + rule scorer + acceptance gate |
| PR10 (universe loader) | 2026-05-05 | #28 | sp500_historical 자동 발견 + backtest resilience |
| PR11 (PR12 pilot) | 2026-05-05 | (prep) | mom-only sharpe 0.50 ceiling |
| PR12 (multi-factor + overlay) | 2026-05-07 | #29 | 가설 falsified, sharpe 0.46→0.35→-0.24 시간 감쇠 |
| Phase 2 (ML Pipeline) | 2026-05-07 | PR13-17 | 인프라 완성, ML 도 acceptance fail |

## 검증된 가설 vs 폐기된 가설

### ✅ 검증

1. **JT 12-1 momentum 이 S&P 500 universe 에 alpha 보유** — standalone
   pilot sharpe 1.21, alpha +7.6%. CPCV 87% 통과. Bootstrap 91%
   양 alpha. (Quant_Robustness_2026-05-07.md)
2. **Walk-forward + acceptance gate discipline** — full-history
   optimization 회피, 정직한 측정. CLAUDE.md §4 가 작동.
3. **TDD + mypy strict** — 503 tests, 88% coverage, 17 PRs 모두 무사고.
   refactor 비용 낮게 유지.
4. **Universe loader auto-discovery** (PR10) — fja05680/sp500 dataset
   파일명 변동 자동 처리, env override fallback.
5. **regime_overlay (BSC + DM bear gate)** (PR12) — DD 통제 효과
   명확 (0.56 → 0.33), 다음 cycle 에서도 재사용 가능.
6. **ML 가 rule scorer 보다 marginal 개선** — sharpe -0.24 → +0.04
   (+0.28 shift), alpha +4.5pp. 인프라 자체는 작동.

### ❌ 폐기

1. **AQR multi-factor blend (rule weights) → acceptance pass**: PR12
   가설. falsified across 3 시간 윈도우 (sharpe 0.46→0.35→-0.24).
2. **ML cross-section weighting → acceptance pass**: PR15-17 가설.
   ML mean IC -0.035 (Kelly-Pruitt-Su 0.05 floor 미달), held-out
   sharpe +0.04 << 1.0.
3. **PR12 features (momentum_252_21 + qlib) → momentum composite 강화**:
   equal-mean dilution 으로 오히려 신호 약화. PR12 mom-only sharpe 0.35
   < PR11 mom-only 0.50.
4. **Rule scorer 의 7-composite framework + threshold entry → SPY beat**:
   long-only equal-weight 가 cap-weighted SPY 의 mega-cap tech AI
   rally 못 따라감. 구조적 한계.
5. **Sentiment composite (LLM 생성 sentiment_score 0.15 weight)**:
   backtest 에 wiring 안 되어 있었고 (L007), 와이어링 해도 Lopez-Lira
   2024 결과로 시간 감쇠 명확 → 의미 있는 contributor 안 됨.

## 구조적 한계 (핵심 학습)

### 1. Cross-section z-score → threshold 가 cap-weight 인덱스 적

bloasis 가 cross-section 에서 z-score → unit-score → entry_threshold
0.65 통과 종목 매수 (variable count, equal weight). SPY 는 cap-weighted
(NVDA 7%, AAPL 6%, MSFT 6% 등 mega-cap 비중 큼). 2023-2024 AI rally 같은
mega-cap-driven 시장에서 equal-weight 는 자동 underperform.

이건 *데이터의 문제* 가 아니라 *strategy 구조의 문제*. ML 도 이 구조 안에선
못 이김.

### 2. Equal-mean composite blend 의 신호 dilution

7 composites × 23 features 의 cross-section z-score 평균. 핵심 신호
(long-term momentum) 이 noise-correlated 다른 composites 에 묻힘.
PR11 → PR12 측정에서 명확: features 추가 → 신호 *감소*.

ML 가 자동 dynamic weighting 으로 이 dilution 을 우회할 수 있다는
가설 → falsified. Mean IC -0.035 = ML 가 학습할 신호 자체가 데이터에
없음 (이 framework 안에서).

### 3. 시간 감쇠 (regime shift)

Pre-COVID 2014-2019 (sharpe 0.46) → 2019-2024 (0.35) → Post-COVID
2021-2024 (-0.24). PR12 pilot/momentum/baseline 모두 동일 패턴. 2020
이 single anomaly 가 아니라 strategy 의 효력이 시간에 따라 감쇠.

이건 momentum strategy 의 알려진 패턴 (publication bias / crowding /
factor decay) 이지만, **acceptance gate 1.0 sharpe 임계가 너무 높았음**.
AQR live fund (QCELX) 1.25 sharpe 가 이론적 상한. 35% deflate 적용 시
0.81 정도가 현실. 우리 1.0 임계는 production 펀드 수준.

### 4. Long-only 의 한계

DM 2016 의 dynamic momentum 의 alpha 는 short side 에 의존 (loser-as-
written-call). long-only 인 우리는 절반만 받음. AQR 의 multi-factor
blend 도 long/short 에서 더 효과적. mission 의 long-only 제약은 honest
하지만 천장 낮춤.

## 작업한 것 — 인프라 자산 (보존)

리디자인 시 재사용 가능한 코드 자산:

| 자산 | 위치 | 재사용 가능성 |
|---|---|---|
| feature_log writer (chunked, idempotent) | `bloasis/storage/writers.py` | ✅ |
| 23 feature extractor + 5 composite | `bloasis/scoring/{features,composites,extractor,derived,indicators}.py` | ✅ (필요한 features 골라쓰기) |
| `bloasis label-features` CLI | `bloasis/cli.py` + `bloasis/ml/labeling.py` | ✅ |
| `bloasis ml train` CLI | `bloasis/cli.py` + `bloasis/ml/{cv,training}.py` | ✅ |
| LightGBMScorer + SHAP | `bloasis/scoring/scorer.py` | ✅ |
| regime_overlay (BSC + DM bear gate) | `bloasis/scoring/regime_overlay.py` | ✅ |
| sp500_historical loader (GitHub auto-discovery) | `bloasis/data/universe/sp500_historical.py` | ✅ |
| Backtest engine + walk-forward + AcceptanceEvaluator | `bloasis/backtest/*` | ✅ (signal/scorer 인터페이스 유지 시) |
| Trades / equity_curve / feature_log schema | `bloasis/storage/schema.py` | ✅ |
| 503 tests + TDD 패턴 | `tests/` | ✅ |
| Cached OHLCV parquet (490 syms × 6y) | `~/.cache/bloasis/parquet/ohlcv/` | ✅ (대용량 데이터 재페치 안 필요) |
| Labeled feature_log DB (60만 rows × 5 backtest runs) | `bloasis.db` | ✅ ML training prior |

## 작업한 것 — 폐기 (또는 mothball)

| 자산 | 사유 |
|---|---|
| `RuleBasedScorer` 의 7-composite weighted average | 신호 dilution. 다음 cycle 에선 single-factor 또는 학습된 가중치 |
| `entry_threshold` / `exit_threshold` based selection | cross-section threshold 대신 rank-based 추천 |
| `regime_multipliers` (config) | 비활성. JT crashes (DM 2016) 는 overlay 로 대체 |
| baseline.yaml + baseline-v2.yaml | deprecated. 다음 cycle 의 새 config 가 starting point |

## 비용 회계 (5 개월)

- **시간**: ~5 개월. mission roadmap 의 Phase 1 (4 weeks) + Phase 2
  (4 weeks) 예측 대비 약 2.5x 초과. 주 원인: PR12 multi-factor blend
  실패 + Phase 2 ML 결과 fail.
- **PRs**: 17 (PR1-PR17)
- **코드**: ~10k LOC (production) + ~5k LOC (tests)
- **측정 비용**: yfinance fetch 시간 ~수 시간 누적. 다행히 모든 measurement
  cached → 다음 cycle 재사용 가능.

**ROI 평가**: mission M3 (paper trading) 진입은 못했지만,
- 정직한 acceptance gate discipline 으로 false positive 거른 것이 가장 큰
  자산 (5개월 시간 투자 외에 *돈* 잃지 않음)
- ML factor research 인프라 완성 → 다음 cycle 의 시작점
- 학습된 falsifications → 다음 cycle 의 risk register

## Mission Halt 정직 표명

**Phase 1 Exit Gate 통과하지 못함**. mission.md 의 acceptance gate:
- median_sharpe_vs_spy ≥ 1.0 → 최고 0.50 (mom-only PR11), ML 0.04
- median_alpha_annualized ≥ -0.005 → 최고 +0.087 (script JT 12-1, no
  costs), production 모든 변종 음수

→ paper trading 진입 차단. mission "halt" 옵션 정직 발동. (mission.md
"Reset, simplify, or halt" 의 honest 발동.)

5 개월 작업이지만 명확한 evidence 기반 결정.

## 다음 사이클 — Redesign 검토

폐기 결정 아닌 **일시정지 + 다음 사이클 redesign** 가능성:

### 살아있는 신호

JT 12-1 standalone sharpe 1.21 (CPCV 87% pass, bootstrap 91% positive
alpha) → 신호 자체는 분명. bloasis 의 architecture 안에서만 못 살아남음.

### 검토 후보 (별도 design lockin doc)

1. **Path B (rank-based)**: top-decile rank → equal weight → monthly
   rebalance. JT standalone pattern bloasis 통합. Architecture 변경
   대규모 (Signal/Scorer 인터페이스 자체).
2. **Modern AI redesign**: 2024-2026 AI 투자 reference (docs/research/
   Modern_AI_Investing_References_2026-05-07.md) 기반 — Transformer
   time-series / LLM agents / RL portfolio construction / numerai-style
   ensemble.
3. **Long/short 또는 market-neutral**: long-only 한계 우회. mission 변경
   필요.
4. **Acceptance gate 재정의**: 1.0 sharpe 가 production 펀드 수준 (AQR
   live 1.25). 0.7-0.9 가 honest 목표. mission.md 수정.

위 옵션들의 비교는 별도 redesign brief 에서.

## 산출물 위치

- 본 doc: `docs/research/Phase2_Postmortem_2026-05-07.md`
- 측정 결과: `docs/research/Phase2_Final_Measurement_2026-05-07.md`
- Phase 2 design lockin (예측 vs 결과 비교): `docs/research/
  Phase2_ML_Design_Lockin_2026-05-07.md`
- 모든 backtest run: `bloasis.db` run_ids 1-3 (PR17 worktree 내)
- 모든 PR: GitHub blas1n/bloasis #28 - #34
- 모든 측정 학술 reference: `docs/research/{Quant_References,
  Quant_Robustness,Research_*}.md`

## 결론

mission 의 정공법 결과: halt. 전략 자체가 acceptance 통과 못 함을
**5개월 데이터 + 17 PRs 로 입증**. 그러나 인프라 + 학습 + JT 12-1 의
salvageable 신호 → 다음 사이클 redesign 의 starting point 충분.

다음 작업: redesign brief 작성 (docs/research/Modern_AI_Investing_
References_2026-05-07.md 의 modern AI 투자 research 결과 통합 후).
