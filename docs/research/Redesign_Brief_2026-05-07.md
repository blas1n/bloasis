# Bloasis Redesign Brief (2026-05-07)

> Phase 1/2 halt 후 redesign 계획. Postmortem + 2024-2026 modern AI
> 투자 research 종합. **사용자 confirm 후 implementation 시작**.

## 종합 진단 (Postmortem + Research)

### 우리가 입증한 것
- **JT 12-1 momentum 이 우리 universe 에 sharpe 1.21 alpha** (CPCV 87%
  pass, bootstrap 91% positive). 신호는 분명.
- **Production-grade 인프라 완성**: 503 tests, walk-forward engine,
  feature_log writer, ML training pipeline, regime overlay, SHAP
  rationale.
- **TDD discipline + acceptance gate** 가 작동 → 5개월 *돈* 안 잃음.

### 우리가 falsified 한 것
- **Cross-section z-score → entry threshold + equal-weight** 가 cap-
  weighted SPY 못 이긴다 (구조적 한계).
- **7-composite blend 의 equal-mean** 이 핵심 신호 dilute.
- **ML scorer 가 rule scorer ceiling 돌파** — 이 framework 안에선 X
  (ML mean IC -0.035).

### 2024-2026 시장 컨센서스 (research agent 발견)
- **JT 12-1 momentum 이 2024 96th percentile 50년래 excess return**
  (SSGA). 우리 1.21 sharpe 가 macro-regime 효과의 일부. 단 SSGA: best
  factor 11번 중 7번 다음 해 -5% → **vol-scale + market-state filter
  필수**.
- **AQR Cliff Asness 2025-04 ML 신봉자 전향**, but **economic intuition
  + hard data 50/50 지속, 순수 black-box 거부**.
- **Lopez-Lira ChatGPT alpha 1년에 절반씩 감쇠**: sharpe 6.54 (2021)
  → 1.22 (2024). LLM-direct path 의 시간 창이 매우 짧다.
- **Numerai-style ensemble** (LightGBM + Ridge + 단순 momentum 등가중)
  이 single 모델 대비 robust → **JPMorgan 2025-08 $500M 투입**.
- **End-to-end RL / 트랜스포머 / LLM 멀티에이전트 = 2024 컨센서스 hype**.
  Single-stock 데모는 인상적, S&P 500 cross-section reproducibility 거의 X.
- **2026 컨센서스 alpha 분배**: universe selection (40%) + factor design
  (40%) + 거래비용 처리 (10%) + ML model 선택 (10%). 우리 PR12-17 작업의
  비중은 거꾸로였음.

## 핵심 인식 — 정서적 sunk cost 함정

> **"5개월 LightGBM 자산이 sharpe -0.04 인데 1주 baseline 이 1.21 이면
> 모델이 아닌 framework 를 버리는 게 정답"** (research agent Path E).

PR12-17 의 ML 자산 (LightGBMScorer / SHAP / training pipeline) 을 살리려
강제하면 **acceptance gate 통과 못 함**. JT 12-1 baseline 은 이미 통과.

→ Phase 1/2 의 7-composite + threshold framework 는 **sunk cost. 폐기**.

ML 인프라 자산 (feature_log writer / labeling / training CLI) 은 보존
하되 **Phase 3 의 add-on alpha 1개 (텍스트 직교 신호 등) 학습용으로만
재사용**, 메인 scorer path 에서는 제외.

## Redesign Plan (Phase 0 → Phase 3)

### Phase 0 (1주) — JT 12-1 v1 ship

**Goal**: acceptance gate 통과하는 첫 strategy ship. 정서적 청산.

**Scope**:
- 신규 `bloasis/strategies/jt_momentum.py` (or `bloasis/scoring/jt_momentum_scorer.py`)
- Top-decile rank-based selection (cross-section threshold 폐기)
- Equal-weight long, monthly rebalance (현재 daily entry/exit 제거)
- 12-1 J-T momentum 단독 (`momentum_252_21` feature 만)
- regime_overlay 그대로 (BSC + DM bear gate, DD 통제 검증됨)
- 새 config `configs/baseline-v3-jt.yaml` — scorer.type 새로 `jt_momentum`

**Engine 변경**:
- `bloasis/scoring/scorer.py` `Scorer` Protocol 에 새 `JTMomentumScorer`
  추가 (rank-based)
- `bloasis/signal.py` 의 entry threshold 로직 우회 — top-N rank 직접
  매수
- 또는 `Backtester` 에 `RankBasedSelector` 인터페이스 추가
- (Backwards-compat 가능하면 RuleBasedScorer/LightGBMScorer 도 그대로 둠)

**측정**:
- 풀 walk-forward 503 syms × 6y (PR12 동일 setup)
- 기대치: sharpe 1.0+ 처음 통과, alpha +5-7% (cost 5bps 적용)
- DD ratio: regime overlay 활성 시 ≤ 0.85 가능
- multi-window: pre-COVID + 2019-2024 + post-COVID

**Acceptance gate 재정의 (mission.md 수정 후보)**:
- 현 1.0 sharpe 임계는 production 펀드 수준 (AQR 1.25 의 80%). honest
  retail 목표 0.7-0.9.
- mission 수정안: `median_sharpe_vs_spy >= 0.7` (0.7 이상 = paper trading
  진입, 1.0 이상 = real money)

**예상 리스크**:
- Cost 적용 후 sharpe 1.0 미달 (경험상 0.6-0.9). DD ratio 통과 borderline.
- regime_overlay parameter (σ=12% target) 가 너무 보수적 → 추가 튜닝
  1-2회.

### Phase 1 (2-3주) — Vol-scaled + market-state filter

**Goal**: SSGA "11번 중 7번 다음 해 -5%" 위험 mitigation. Path A research
agent recommendation.

**Scope**:
- `regime_overlay.py` 확장: 단순 BSC + bear gate 외 **vol-scaled position
  sizing** (현재 sigma_target=0.12 fixed → realized vol 으로 동적 매핑).
- **Market-state filter**: 10-month SMA above/below 같은 단순 지표로
  trend regime 식별. 하락 regime 시 노출 절반.
- 멀티 윈도우 측정 + tuning.

**기대치**: sharpe 1.2-1.4, MDD 25% → 15%. Path A research 결과 인용:
"momentum crash 위험 절반".

### Phase 2 (3-5주, 선택) — Quality + Momentum 2-factor blend

**Goal**: AQR 2024 quality + momentum 결합 패턴. Path B research recommendation.

**Scope**:
- Quality factor 정의: ROIC, asset turnover, accruals 음수 (Phase 1 의
  fundamentals features 일부 재사용 가능 — `roe`, `debt_to_equity`,
  `current_ratio`, `profit_margin`).
- Cross-section z-score 평균 (Phase 2 가 했던 equal-mean 방식 재시도, 단
  **2-factor 만**, 7-composite blend X)
- 합성 후 다시 top-decile rank
- 측정: vs Phase 0/1 baseline

**기대치**: sharpe 1.0-1.4 (AQR 2024 backtest 13.66% annualized excess
return). turnover 감소 (single momentum 보다).

**비즈니스 결정 포인트**: Phase 0 통과시 mission M3 paper trading 진입
가능. Phase 2 는 그 다음 enhancement.

### Phase 3 (1-2개월, 선택, 별 트랙) — 텍스트 직교 alpha

**Goal**: "JT 자체는 commodity, 직교 텍스트 alpha 1개 add-on" (Path E).

**Scope** — 셋 중 1개만 prototype:
1. **10-K risk-factor uncertainty embedding** (J. Finance 2025 "War
   Discourse" 패턴): 10-K Item 1A → embedding → cosine similarity to
   "uncertainty cluster" → 1m forward return 신호
2. **Earnings call transcript sentiment** (FactSet/MarketPsych 패턴):
   negative-tone bottom 5% → underperform
3. **News headline event drift** (Lopez-Lira 패턴, but **alpha decay
   인식하고 짧은 윈도우 ship**)

**구현**:
- 새 모듈 `bloasis/scoring/text_alpha.py`
- LLM call (Claude Haiku or local Qwen 3) for embedding/sentiment
- Cross-section z-score → momentum factor 와 *blend* (0.7 momentum + 0.3
  text)
- PR12-17 의 LightGBM 자산 *재활용*: text features 도 feature_log 에
  저장 → `bloasis ml train` 으로 ensemble 학습 가능

**기대치**: sharpe 1.3+ (Numerai-style ensemble + 직교 신호 패턴).

## Path 우선순위 (research agent + postmortem 합의)

| Path | Effort | P(통과) | 권장 시점 | Bloasis 자산 재활용 |
|---|---:|---:|---|---|
| **Phase 0: JT 단독 ship** | 1주 | **매우 높음** | 즉시 | 50% (engine + universe + cache) |
| **Phase 1: vol-scaled + market state** | 2주 | 높음 | Phase 0 직후 | 60% |
| Phase 2: Quality + Momentum blend | 3주 | 중-높음 | M3 paper trading 진입 후 enhancement | 70% |
| Phase 3: 텍스트 직교 alpha | 1-2개월 | 중 (cherry-pick risk) | 별 트랙 | ML 인프라 살림 |
| (Path D: qlib 통째 이주) | 4-6주 | 중 | 위 path 모두 fail 시 trigger | 30% (대량 폐기) |

**즉시 시작 권고**: Phase 0 (1주). Phase 1 다음 sprint.

## What to Keep / What to Discard

### Keep (다음 cycle 자산)
- ✅ `bloasis/scoring/derived.py` (momentum/volatility/volume_ratio + PR12 KBAR/CORR_PV)
- ✅ `bloasis/scoring/regime_overlay.py` (BSC + DM bear gate — Phase 1 적용)
- ✅ `bloasis/scoring/extractor.py` + `features.py` (23 features, feature_log writer)
- ✅ `bloasis/storage/` 전체 (schema, writers, readers)
- ✅ `bloasis/backtest/engine.py` (walk-forward, fold logic, regime overlay wiring)
- ✅ `bloasis/data/universe/sp500_historical.py` (loader)
- ✅ `bloasis/ml/` 모듈 (Phase 3 텍스트 alpha 학습용)
- ✅ Cached parquets + DB (재페치 안 필요)
- ✅ TDD 패턴 + 503 tests

### Discard / Mothball
- ❌ `RuleBasedScorer` 의 7-composite weighted average (메인 path 에서 제외, but 비교용 baseline 로 잠시 보존)
- ❌ `entry_threshold`/`exit_threshold` based selection — top-N rank 가 메인
- ❌ `regime_multipliers` (config dict) — 비활성, 대신 regime_overlay 재사용
- ❌ baseline.yaml + baseline-v2.yaml (deprecated, baseline-v3-jt.yaml 신규)
- ❌ PR12 의 KBAR/CORR_PV 같은 features 의 **composite blending** — features 자체는 keep, blend 방식 폐기
- ❌ `LightGBMScorer.score_cross_section` 의 cross-section z-score → CDF mapping 으로 entry threshold 통과 시키는 path (메인 X, Phase 3 ensemble 학습 보조 only)

## Mission gate 재정의 제안

기존 `mission.md` acceptance gate (1.0 sharpe) 가 production 펀드 수준
(AQR 1.25 의 80%) 으로 너무 높음. honest retail 단계 분리 권고:

```
Phase 0 ship gate (paper trading 진입):
  median_sharpe_vs_spy >= 0.7
  median_alpha_annualized >= -0.005
  median_max_dd_ratio_to_spy <= 0.85

Phase ∞ live trading gate (real money):
  median_sharpe_vs_spy >= 1.0
  median_alpha_annualized >= 0.0
  median_max_dd_ratio_to_spy <= 0.85
  + 6 month paper trading track record
```

이 변경은 mission.md 수정 — 사용자 결정 필요.

## 실행 순서 (사용자 confirm 후)

1. **mission.md acceptance gate 분리** (paper vs live) — 단일 commit
2. **Phase 0 (PR18)** — JTMomentumScorer + RankBasedSelector + baseline-v3-jt.yaml + 측정 + handoff doc
3. **Phase 1 (PR19)** — vol-scaled overlay 확장 + market-state filter + 재측정
4. (Phase 2/3 는 결과 보고 결정)

총 예상: Phase 0+1 합쳐 3-4주. Phase 0 단독 1주.

## Key References

- `docs/research/Phase2_Postmortem_2026-05-07.md` — 본 redesign 의
  evidence base
- `docs/research/Modern_AI_Investing_References_2026-05-07.md` — 2024-
  2026 실무 컨센서스
- `docs/research/Phase2_Final_Measurement_2026-05-07.md` — 정량 지표
- `docs/research/Quant_Robustness_2026-05-07.md` — JT 12-1 standalone
  sharpe 1.21 evidence
- `docs/research/Quant_References.md` — 학계 클래식
- `docs/research/Research_DM_Dynamic_Momentum.md` — regime overlay
  spec (Phase 1 재사용)

## 사용자 결정 사항

1. **Mission gate 재정의 OK?** (1.0 sharpe → 0.7 paper / 1.0 live 분리)
2. **Phase 0 (JT 단독 ship) 즉시 시작 OK?** PR18 begin
3. **Phase 1/2/3 의 우선순위 확정**: Phase 0 → 1 → (2 or 3)?
4. **PR12-17 의 ML 자산 처리**: keep but mothball (Phase 3 학습용으로만
   재호출) OK?
5. **추가 가설 / path 추가**? (위 5 path 외 검토할 것)

답변 후 PR18 implementation 시작.
