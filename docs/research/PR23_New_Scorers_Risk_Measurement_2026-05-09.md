# PR23 — New Scorers + Risk Axis Grid Measurement (2026-05-09)

PR22 의 negative findings (knob sweep / EDGAR∩JT intersect 둘 다 dead) 이후
4개 미답 방향 자율 측정. 모두 PR20 protocol (start=2022-01-01, end=2024-10-17,
train=180, test=120, step=120 → 7 folds, SP500 at 2024-12-31).

## TL;DR

- **PR23-A PEAD: 0/6 PASS.** Bernard-Thomas PEAD 가 SP500 mega-cap 환경에서 dead.
- **PR23-B regime_overlay: 3/6 PASS** (= overlay disabled baseline 3개). Vol-targeting
  enabled 모두 alpha -1.5 ~ -3.4% 회귀.
- **PR23-C position_size_max_pct: 3/5 PASS, 2 cells α +4.2% (baseline +0.1pp).**
  pos=0.03/0.05 가 baseline 위로. 작지만 첫 실측 lift.
- **PR23-D fundamental_llm: 0/2 PASS.** llama3.2:3b 로는 SP500 mega-cap 알파 없음 (α -6.0 ~ -7.5%).

## PR23-A — PEAD scorer

| top_pct | drift_days | sharpe vs SPY | α       |
|---------|-----------:|--------------:|--------:|
| 0.10    | 30         | 0.38          | **-16.7%** |
| 0.10    | 60         | 0.76          | -6.5%   |
| 0.10    | 120        | 0.89          | -9.8%   |
| 0.20    | 30         | 0.38          | **-26.2%** |
| 0.20    | 60         | 0.43          | -6.1%   |
| 0.20    | 120        | 0.87          | -8.7%   |

**해석:**
- drift_days=30 처참 (-16~-26%). 너무 짧아서 surprise 신호 인식 전에 closed.
- drift=60-120 으로 sharpe 회복 (0.38 → 0.89) but 알파 음수 유지.
- best 알파: top=0.20/drift=60 = -6.1% (FAIL).

**Bernard-Thomas (1989)** 의 원 발견은 소형주 + 정보 비대칭 환경. 2022-2024
SP500 mega-cap 시장은 earnings surprise 가 즉시 반영, drift 기간 동안 추가
알파 없음. ChatGPT 등장 후 PEAD 가속 decay 도 이미 academic 관찰.
**PEAD 단독 dead.**

## PR23-B — regime_overlay sigma_target sweep

Hypothesis: PR22 intersect 가 universe 좁혀 알파 무너뜨린 반면, vol-targeting 은
universe 안 건드리고 DD 만 닫음. JT residual + monthly 의 DD 1.20 fail 을 살릴 수 있을지.

| enabled | sigma_target | sharpe | α       | gate |
|---------|--------------|--------|---------|------|
| False   | 0.10         | 1.33   | +4.1%   | PASS (= baseline) |
| False   | 0.12         | 1.33   | +4.1%   | PASS (baseline 중복) |
| False   | 0.15         | 1.33   | +4.1%   | PASS (baseline 중복) |
| True    | 0.10         | 1.35   | -3.4%   | FAIL |
| True    | 0.12         | 1.34   | -2.4%   | FAIL |
| True    | 0.15         | 1.33   | -1.5%   | FAIL |

**해석:**
- EDGAR 의 자연 vol 이 이미 낮음 (top-decile = stable disclosure stocks = low vol).
  vol-targeting 이 추가로 줄여서 알파 손실.
- DM bear gate (`bear_scale=0.5`) 가 2022 H1 bear 에서 position 절반 → 2022 후반 회복기 missed.
- sigma=0.15 가 enabled 셀 중 best 지만 여전히 baseline 보다 -5.6pp.

**EDGAR baseline 에는 vol overlay 부적합.** JT residual 단독에 적용하는 것이 가설의 본 의도였으니
다음 PR 후보: JT residual + overlay 조합.

## PR23-C — position_size_max_pct sweep

EDGAR baseline 위에서 concentration 직접 통제.

| pos     | 슬롯 수 | sharpe | α          | gate |
|---------|---------|--------|------------|------|
| 0.005   | 200     | 1.37   | **-11.2%** | FAIL (cash drag, 25% deployed) |
| 0.01    | 100     | 1.36   | -2.0%      | FAIL (cash drag, 50%) |
| 0.02    | 50      | 1.33   | +4.1%      | **PASS (baseline)** |
| 0.03    | ~33     | 1.33   | **+4.2%**  | **PASS** ← +0.1pp lift |
| 0.05    | 20      | 1.33   | **+4.2%**  | **PASS** ← +0.1pp lift |

**해석:**
- pos < 0.02: 후보가 50주 (top decile) 인데 capital limit 가 더 작아서 cash idle. 알파 처참.
- pos = 0.02: 50주 × 0.02 = 100% deployed. baseline.
- pos = 0.03/0.05: 후보보다 적은 슬롯 → 시그널 강한 top 33/20주만 채택. 약간 더 집중.

**positive finding!** PR22+23 의 첫 실측 lift. 다만 +0.1pp 알파 = noise 영역에 가까워
robustness 확인 필요. Bootstrap CI 또는 다른 walk-forward 윈도우에서 재확인 권장.

## PR23-D — fundamental_llm

| top_pct | sharpe vs SPY | α       | gate |
|---------|--------------:|--------:|------|
| 0.10    | 0.93          | **-7.5%** | FAIL |
| 0.20    | 0.88          | **-6.0%** | FAIL |

**해석:**
- 두 콤보 모두 negative α. wider top_pct (0.20) 가 약간 덜 나쁨.
- LLM 캐시는 이전 세션에서 이미 덥혀 있어서 (4.2MB, 1085 entries) cold 콤보 wall-clock
  ~10 min 으로 빨리 끝남. 결과 자체는 캐시된 LLM 점수에 대한 정상 측정.

**가능한 이유:**
1. **llama3.2:3b (3B params) 가 SP500 fundamental 분석에 부족.** 일반 LLM 의 quantitative
   accounting 추론 한계.
2. **Quarterly update freq 가 너무 느려서 surprise 신호 없음.** Cohen-Malloy 의 10-K text-diff
   는 yearly + 변화 자체가 신호이지만, fundamental_llm 은 절대값 health score 라 mean-reverting.
3. **Mega-cap 펀더멘털은 이미 가격에 반영.** EDGAR 처럼 disclosure dialect drift 같은 미세 신호는
   살아있지만, 단순 ratio-based health score 는 dead.

**다음 LLM 시도 후보 (별도 PR):**
- 더 큰 Ollama 모델 (qwen3:14b, ministral-3:14b 사용 가능)
- frontier model (claude haiku 또는 gpt-4o-mini) 작은 universe 에 한정 측정

## 결정

- **edgar-rolling2 (PR20 winner) 가 여전히 ship config.** PR23-C pos=0.03/0.05 가 +0.1pp 미세 lift
  지만 ship 변경 권할 정도는 아님 (noise 영역).
- 다음 grid 후보:
  - **JT residual + regime_overlay** — PR23-B 가설을 본래 의도대로 (EDGAR 베이스가 아닌 JT residual 베이스에) 적용
  - **PR23-C 결과 robustness** — pos=0.03 에 다른 walk-forward 또는 universe 적용
  - **fundamental_llm** 결과 본 후 결정

## Negative findings 의 가치 정리

| 가설 | 결과 | gain |
|------|------|------|
| PEAD 단독 ship | 0/6 | "PEAD 는 SP500 환경에선 dead" — PR12 ChatGPT decay finding 재확인 |
| Vol-overlay on EDGAR | 0/3 enabled | EDGAR 가 이미 low-vol 신호 — overlay 부적합. JT residual 베이스로 옮겨야 |
| Position-size sweep | 2 lifts | pos=0.03/0.05 가 작지만 baseline 보다 위 |

총 **19 콤보** 측정, 1 새 shippable 상한 (PR23-C pos=0.03/0.05 = α +4.2%).

## 최종 누적 측정 (PR21-23, 41 combos)

| Phase | n | 새 lift | finding |
|-------|---|---------|---------|
| PR21 v3 | 16 | 0 (PR20 reproduction) | rolling=2/rebal=21 sweet spot 확인 |
| PR22 A | 8 | 0 | top_pct=0.10/cont=False 가 진짜 local optimum |
| PR22 B | 4 | 0 | EDGAR ∩ JT intersect destroys alpha |
| PR23 A PEAD | 6 | 0 | dead on SP500 mega-cap |
| PR23 B regime | 6 | 0 | vol-target hurts EDGAR baseline |
| PR23 C pos | 5 | **2** (+0.1pp) | pos=0.03/0.05 marginal lift |
| PR23 D fund_llm | 2 | 0 | llama3.2:3b 약함 |

**41 combos / 1 미세 lift.** edgar-rolling2 가 robust local optimum.

**다음 권장:**
- pos=0.03 robustness 확인 (다른 walk-forward windows / universes)
- JT residual + regime_overlay (PR23-B 가설 본래 의도)
- 더 큰 Ollama 모델 또는 frontier LLM 작은 universe
