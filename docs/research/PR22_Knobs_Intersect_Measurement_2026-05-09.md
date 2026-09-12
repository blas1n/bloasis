# PR22 — continuous_score / top_pct / EDGAR∩JT Grid Measurement (2026-05-09)

PR21 grid 인프라 검증 완료 후 첫 본격 axis 탐색. 두 가설을 한 번에:

1. **Grid A** — `continuous_score` × `edgar_textdiff_top_pct` 가 PR20 winner 위로 올라가나?
2. **Grid B** — `edgar_textdiff_jt_intersect` (residual/vanilla × top_pct) 가 PR19 의 JT residual α +8.99% 를 EDGAR DD 로 살릴 수 있나?

## TL;DR

**둘 다 가설 falsified. PR20 baseline 위로 못 감.**

- Grid A: **8/8 완료, 1 PASS** (= PR20 baseline 재현). 모든 새 셀 baseline 보다 약함.
- Grid B: **4/4 완료, 0 PASS.** EDGAR∩JT intersect 가 alpha 를 -7~-16% 로 밀어버림.

EDGAR rolling=2 + top_pct=0.10 + cont=False + monthly 가 여전히 ship config.

## Grid A — Knob sweep on EDGAR baseline

Walk-forward: 2022-01-01..2024-10-17, train=180, 7 folds. SP500 at 2024-12-31.

| top_pct | continuous_score | sharpe vs SPY | α        | gate |
|---------|------------------|---------------|----------|------|
| 0.05    | False            | 1.07          | -4.5%    | FAIL |
| 0.05    | True             | 0.91          | +1.8%    | FAIL (DD) |
| **0.10**| **False**        | **1.33**      | **+4.1%**| **PASS** ← PR20 baseline |
| 0.10    | True             | 0.91          | +1.8%    | FAIL (DD) |
| 0.15    | False            | 1.19          | +1.9%    | FAIL (α weak) |
| 0.15    | True             | 0.91          | +1.8%    | FAIL |
| 0.20    | False            | 1.04          | +0.4%    | FAIL |
| 0.20    | True             | 0.91          | +1.8%    | FAIL |

### 인사이트

1. **top_pct 가 single-knob optimum at 0.10.** 0.05 (top 5%) 너무 좁아 강한 신호 놓침.
   0.15-0.20 은 약한 신호까지 끌어들여 dilution.
2. **continuous_score=True 가 cont=False 모두에서 회귀** (sharpe 0.91 / α +1.8% 일관). EDGAR
   cosine 신호는 "spiky" — binary 0.99/0.0 가 강한 시그널만 잡지만 percentile-rank 는 약한 시그널까지 부분 가중.
3. 결론: **PR20 default 가 local optimum.** 이 두 축으로는 더 못 올라감.

## Grid B — EDGAR ∩ JT(residual) ensemble

같은 walk-forward. scorer.type = `edgar_textdiff_jt_intersect`.

| jt_residual | jt_top_pct | sharpe vs SPY | α        | gate |
|-------------|------------|---------------|----------|------|
| False       | 0.10       | 0.77          | **-14.0%** | FAIL |
| False       | 0.20       | 0.94          | -7.5%    | FAIL |
| True        | 0.10       | 0.56          | **-16.0%** | FAIL |
| True        | 0.20       | 0.88          | -8.7%    | FAIL |

### 인사이트

1. **Intersect 필터가 alpha 를 망가뜨림.** EDGAR top decile (50주) ∩ JT top decile
   (50주) = 5–15주 정도의 매우 좁은 universe. 이 정도 concentration 은 단일 스토리에 노출되어
   breakdown 시 큰 손실.
2. **residual JT 가 intersect 에서는 상황 악화** (vanilla 보다 sharpe 더 낮고 α 더 음수).
   이유: residual 은 vol-control 로 알파를 깎는 trade-off. 알파가 이미 사라진 intersect 에서는
   순수 페널티만 남음.
3. **wider top_pct 가 약간 도움** (0.10 → 0.20: α -14% → -7.5%). intersect 너비를 넓힐수록
   덜 나쁘지만 절대값은 여전히 mass-fail.

### 가설 falsified 정리

PR19 finding: **JT residual + monthly = α +8.99% 인데 DD 1.20 (FAIL)**. 가설 가설은
"DD 문제는 concentration → EDGAR intersect 로 sector 분산 강제하면 알파 살리고 DD 닫음".

**측정 결과 false.** Intersect 가 universe 를 너무 좁혀서 알파 자체가 없어짐. JT residual 이
가졌던 +8.99% 알파는 intersect 후 -8 ~ -16% 로 무너짐.

대안 가설 (다음 PR 후보):
- **Vol-targeting overlay** (regime_overlay 활성화) — DD 를 universe 좁히지 않고 sigma-target 으로 닫는 시도
- **Sector cap** in risk_evaluator — 단일 sector 비중 제한
- **JT residual 단독에 더 보수적 position_size_max_pct** (0.02 → 0.01) — concentration 을 직접 줄임

## 결정

- **edgar-rolling2 (PR20 winner) 가 ship-eligible 로 유지**. PR22 어떤 셀도 위로 못 올림.
- 다음 grid 는 **EDGAR baseline 외 새 scorer 차원** 권장 — 다른 angle 필요. continuous/top_pct/intersect 는 한계점 도달.
- 가능한 후보:
  - **EDGAR + regime overlay (sigma_target sweep)** — DD 추가 보호
  - **EDGAR + position_size sweep** (0.005 ~ 0.03) — concentration 직접 통제
  - **EDGAR + sector_concentration cap** sweep — sector limit 효과
  - **PEAD scorer** 같은 protocol 로 첫 측정 — 미답 영역
  - **fundamental_llm scorer** 같은 protocol — 비싸지만 미답

## Negative findings 의 가치

- Grid A: top_pct=0.10 / cont=False 가 진짜 sweet spot 임을 다양한 인접 셀에서 확인.
  Single-point estimate 가 아닌 **basin** 확정.
- Grid B: 직관적이지만 큰 가설 (intersect 가 ensemble) 을 12 min wall-clock 으로 정리.
  남은 시간을 다른 방향에 쓸 수 있음.
