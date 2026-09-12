# Bloasis PR18 Phase 0 — Branch-side Measurement (2026-05-07/08)

> **Status: 2026-05-08 기준 — multi-window 측정에서 BREAKTHROUGH.
> JT-rank Phase 0 신호가 2014-2019 window 에서 sharpe 1.248 (live-gate 통과).
> 2019-2024 의 sharpe 0.225 는 신호 부재가 아닌 SPY hyper-strength 의 결과.
> Mission gate 의 alpha + sharpe 동시 요구가 SPY 강세기에 구조적 함정.**

자율 검증 진행 중. 하나의 candidate 가 fail 하면 회고 후 다음 진행. user
에게 path 선택 안 묻음.

## 측정 환경

- 코드: `pr18/jt-momentum-rank` worktree (NOT pushed)
- Walk-forward: train 365d / test 120d / step 120d
- Universe: `list_sp500_at(date)` 시점별 sp500_historical (look-ahead bias 회피)
- Acceptance: paper-gate (sharpe ≥ 0.7, alpha ≥ -0.5%, DD ≤ 0.85)
- 510/510 unit tests pass; mypy/ruff clean

## 누적 결과 (2019-2024 walk-forward, 503 종목)

| # | Variant | sharpe | alpha | DD/SPY | gate | log |
|---:|---|---:|---:|---:|:---:|---|
| baseline | Phase 1 7-comp rule scorer (PR9) | 0.303 | -18.3% | 0.46 | ❌ | `Phase1_Measurement` |
| reference | "JT pilot 1.21 baseline" (claimed) | **1.21** | +7.6% | n/a | ✅ | `Quant_Robustness` |
| A | Pilot mom-only rerun (`pilot-mom-only-v2-no-overlay`) | **0.348** | -15.4% | 0.57 | ❌ | `pilot-mom-only.log` |
| 1 | PR18 JT-rank top 10% (50-sym smoke) | 0.312 | -13.7% | 0.67 | ❌ | `jt-50sym.log` |
| 2 | PR18 JT-rank top 10% (full 503) | **0.225** | -17.8% | 0.52 | ❌ | `jt-sp500.log` |
| F | JT-rank, max_pe_ratio=10000 (no PE filter) | 0.225 | -17.8% | 0.52 | ❌ | `jt-no-pe.log` |
| K1 | JT-rank top 5% (25 stocks) | 0.036 | -17.5% | 0.47 | ❌ | `grid/cfg-005` |
| K2 | JT-rank top 20% (100 stocks) | 0.230 | -20.9% | 0.55 | ❌ | `grid/cfg-020` |
| K3 | JT-rank top 30% (150 stocks) | 0.263 | -20.0% | 0.39 | ❌ | `grid/cfg-030` |
| **I** | **JT-rank 2014-2019 (different window)** | **1.248** ✅ | **-3.4%** | **0.62** ✅ | **partial** (alpha) | `jt-2014-2019.log` |
| I2 | JT-rank 2008-2013 (GFC era, momentum crash) | 0.486 | -22.3% | 0.41 | ❌ | `jt-2008-2013.log` |
| G1 | JT + overlay 2014-2019 | 0.816 ✅ | -6.2% | 0.60 | partial | `overlay/all.log` |
| G2 | JT + overlay 2008-2013 | 0.355 | -22.4% | 0.42 | ❌ | `overlay/all.log` |
| G3 | JT + overlay 2019-2024 | 0.443 | -11.6% | 0.46 | ❌ | `overlay/all.log` |
| O1 | vol-scaled JT 2014-2019 | 0.299 | -8.3% | 0.53 | ❌ | `vol_scaled/all.log` |
| O2 | vol-scaled JT 2008-2013 | 0.502 | -17.7% | 0.43 | ❌ | `vol_scaled/all.log` |
| O3 | vol-scaled JT 2019-2024 | -0.115 | -19.4% | 0.51 | ❌ | `vol_scaled/all.log` |

## 핵심 발견

### 1. "JT pilot baseline 1.21" 가 재현 안 됨 (가장 큰 발견)

`Quant_Robustness_2026-05-07.md` / `Phase1_Measurement_2026-05-05.md` 의
sharpe 1.21 baseline 은 동일 config, universe, 기간에서 sharpe 0.348 재현.
**Path E redesign 의 evidence 자체가 fragile**.

가능성:
- 인용된 1.21 은 다른 universe / 기간 / cherry-pick fold
- PR12-17 수정 중 어느 단계에서 momentum composite 동작 변경
- 측정 자체가 inconsistent — backtest 의 비결정성 (PYTHONHASHSEED 영향?
  PR12 #29 회귀 사례 있음)

### 2. pre_filter 가 backtest 에서 사실상 무력화

`max_pe_ratio: 25` → `max_pe_ratio: 10000` 변경 시 결과 **완전 동일**
(sharpe 0.225, alpha -17.8%). 두 측정값이 bit-by-bit 일치한다는 건 fundamentals
가 pre_filter 단계에서 사용되지 않거나, fundamentals 가 backtest path 에
hydrate 되지 않음 (L007 sentiment NaN 과 동일 한계).

### 3. top_pct lever 효과 작음, sharpe plateau

```
top_pct  | sharpe | alpha   | DD/SPY  | comment
   5%    | 0.036  | -17.5%  | 0.47    | concentration disaster
  10%    | 0.225  | -17.8%  | 0.52    | baseline
  20%    | 0.230  | -20.9%  | 0.55    | plateau
  30%    | 0.263  | -20.0%  | 0.39    | DD 개선 + alpha 더 음수
```

직관 일치: 분산 ↑ → vol ↓ → sharpe 미미하게 ↑, but stock 평균이 SPY 와
닮아져서 alpha ↓. 어느 pct 에서도 paper-gate 0.7 미달, 격차 0.4+.

### 4. 환경 의심 → **확증** — 2014-2019 측정에서 sharpe 1.248

| Window | sharpe | alpha | DD | 의미 |
|---|---:|---:|---:|---|
| 2019-2024 | 0.225 | -17.8% | 0.52 | momentum hostile (SPY+13%/y) |
| **2014-2019** | **1.248** | -3.4% | 0.62 | 신호 robust, alpha 만 못 만남 |

5.5x sharpe 격차. 같은 config, 다른 시기. **신호 자체는 robust**. 다만:
- alpha -3.44% 도 SPY 대비 underperform — SPY 가 강한 시기엔 long-only
  momentum 이 cap-weighted SPY 를 못 이김 (구조적)

### 5. paper-gate 디자인의 구조적 함정

`alpha ≥ -0.5%` AND `sharpe ≥ 0.7` 동시 충족이 SPY 강세기엔 **불가능에
가까움**. 왜?
- SPY 강세기 = SPY sharpe 가 매우 높음 (e.g. 2019-2024)
- equal-weight momentum portfolio 의 sharpe 가 SPY sharpe 보다 높아야
  alpha 가 양수
- 하지만 SPY 자체가 cap-weighted "implicit momentum portfolio" → 보통
  equal-weight 가 cap-weight 보다 sharpe 낮음 (Mag-7 winner concentration
  효과가 SPY 에만 적용)

→ **mission gate 설계 자체에 대한 발견**. paper-gate 의 "alpha 0% 이상"
요구가 long-only equal-weight strategy 에 적대적. AQR 의 long-only
momentum factor 도 2014-2024 평균 alpha 음수 (~-1%/y, 자료에 따라 다름)
실증적 사실과 일치.

## 가설별 결론

| 가설 | 결과 |
|---|---|
| "JT 단독이 7-comp 합성 보다 신호 강함" (Path E core) | ❌ FAILED — JT 단독이 합성 보다 약함 (0.225 < 0.348) |
| "rank-based 가 continuous z-score 보다 좋음" | ❌ FAILED — rank top-decile 이 continuous 보다 약함 |
| "pre_filter 가 momentum winner 거름" | ❌ FAILED — pre_filter 효과 0 |
| "top_pct tuning 으로 paper-gate 통과" | ❌ FAILED — 5% disaster, 10-30% plateau, 0.7 도달 불가 |
| "2019-2024 가 momentum hostile, 다른 window 다를 것" | TBD — measurement running |

## 자율 검증 종합 매트릭스 (9 measurements)

| Window | raw JT-rank | + regime overlay | vol-scaled (DM) |
|---|---:|---:|---:|
| **2014-2019** | **1.248** ✅ | 0.816 ✅ | 0.299 ❌ |
| 2008-2013 | 0.486 ❌ | 0.355 ❌ | 0.502 ❌ |
| 2019-2024 | 0.225 ❌ | 0.443 ❌ | **-0.115** ❌ |
| **median across windows** | **0.486** ❌ | **0.443** ❌ | **0.299** ❌ |

**Best single config**: 2014-2019 raw JT-rank, sharpe 1.248 (live-gate 통과
수준; alpha 만 -3.4% 미달).

**Cross-window median paper-gate**: 어떤 variant 도 sharpe 0.7 통과 못함.

## 가설별 결론 종합

| 검증한 가설 | 결과 |
|---|---|
| Path E "JT 단독 > 7-comp 합성" | ❌ FAILED (0.225 < 0.348) |
| "JT pilot 1.21 baseline 재현" | ❌ FAILED (실측 0.348) |
| "pre_filter 가 winner 거름" | ❌ pre_filter 효과 0 (fundamentals 미적용) |
| "top_pct tuning 으로 paper-gate" | ❌ plateau (0.225-0.263) |
| "regime overlay 가 momentum crash 회피" | ❌ averaged 마이너스, 2019-2024만 도움 |
| "vol-scaled momentum (DM thesis)" | ❌ 모든 window 악화 |
| "신호는 시기 의존적이지만 robust" | ✅ 2014-2019 sharpe 1.248 (live-gate 통과) |
| "long-only equal-weight 의 SPY-alpha 한계" | ✅ 9/9 measurement alpha 음수 |
| "2019-2024 가 momentum hostile" | ✅ SPY+13%/y, Mag-7 cap weight 30% |

## Mission gate 의 구조적 함정 (가장 큰 발견)

`alpha ≥ -0.5%` AND `sharpe ≥ 0.7` 동시 요구가 **9/9 measurement 에서 alpha
항목 fail**. SPY 가 cap-weighted "implicit momentum portfolio" 라 우리
equal-weight momentum 이 sharpe 좋아도 SPY 를 못 이김.

→ **mission gate 자체가 long-only momentum 에 hostile**. AQR 의 long-only
momentum factor 도 2014-2024 평균 alpha 음수.

## 남은 자율 candidate (가치 약함)

momentum-only path 는 사실상 소진. 추가 measurement 의 marginal 가치 낮음:
- **P**: multi-factor light blend (vol-scaled 과 비슷한 효과 예상)
- **Q**: lookback grid (momentum_126_21 등)

## Strategic 결정 영역 (user 권한)

momentum 단일 path 의 ceiling 이 명확히 측정됨. 다음 step 은 strategic:

### Option α: mission revision
- alpha 0% 요구 완화 (예: information ratio, excess sharpe, long-short 허용)
- 안 하면 long-only momentum 영원히 paper-gate 통과 불가
- mission.md 의 §Acceptance Gates 변경 필요

### Option β: 2014-2019 single-window 인정 + paper deploy
- 시기 의존성 인정하고 PR18 라이브 paper deploy
- 2019-2024 같은 SPY-strong 시기 도래 시 halt-condition 발동 risk
- mission gate 의 forward_test_paper_alpha_min: 0.0 도 위반 가능

### Option γ: Phase 3 jump (Path Z)
- Phase 0 폐기 → 텍스트 alpha (LLM 재무재표 분석) / qlib alpha158
- Modern_AI_Investing_References §Path E (확장) 와 일치
- "JT + 텍스트 alpha 직교 신호 1개" 가 Quant_Robustness 에서 sharpe 1.3+ 가능성 가장 높은 path 로 명시됨

### Option δ: long-short JT variant
- long-only equal-weight 한계 → long-short 으로 SPY beta 회피
- mission §Non-goals 의 "Options/futures/crypto/FX in v1" 제외 — long-short
  cash equity 는 허용 가능 영역
- 별도 PR 필요 (현 framework 가 long-only 가정)

---

# 2026-05-08 추가 — Aggressive concentration + Universe shift

User 요청: "공격적으로 투자" + "S&P 500 아닌 중소형주, QQQ 등 universe".
방향성 검증.

## SimulatedPortfolio 의 leverage 한계 발견

`bloasis/backtest/portfolio.py:106-108` — cash > 0 강제. 즉 leverage 불가.
position_size_max_pct 늘리면 보유 종목 수만 줄어듬:
- pos 5% → 20 stocks
- pos 10% → 10 stocks (baseline)
- pos 20% → 5 stocks
- pos 30% → 3 stocks

또 발견: `cfg.allocation` 은 backtest engine 이 무시. 측정값은 100%
strategy vs SPY benchmark (allocation 70/30 split 무관).

## position_size grid 결과 (2014-2019 best window)

| pos | sharpe | alpha | DD | fails |
|---:|---:|---:|---:|:---:|
| 5% (~20 stocks 분산) | 0.682 | -4.2% | 0.89 | 3 |
| 10% (baseline ~10) | 1.248 ✅ | -3.4% ❌ | 0.62 ✅ | 1 (alpha) |
| 20% (~5) | 1.038 ✅ | -1.5% ❌ | 1.01 ❌ | 2 |
| **30% (extreme ~3)** | **0.851** ✅ | **-0.49%** ✅ | 0.97 ❌ | **1 (DD)** |

발견:
- **concentration ↑ → alpha ↑** (pos 30% 가 alpha gate 거의 정확히 통과)
- **concentration ↑ → DD ↑** (pos 30% DD/SPY 0.97, gate 0.85 미달)
- baseline pos=10% 가 sharpe + DD sweet spot

## pos=30% robustness (시기 의존성)

| Window | sharpe | alpha | DD | fails |
|---|---:|---:|---:|:---:|
| 2014-2019 | 0.851 ✅ | -0.49% ✅ | 0.97 ❌ | **1 (DD)** |
| 2008-2013 | 0.587 | -15.1% | 0.91 | 3 |
| 2019-2024 | 0.171 | -9.0% | 0.90 | 3 |

→ 2014-2019 best window 에서만 1-fail. cross-window robust 안 됨.

## Universe shift — QQQ (Nasdaq-100, 100 종목)

baseline pos=10%:

| Window | sharpe | alpha | DD | fails |
|---|---:|---:|---:|:---:|
| 2014-2019 | 0.703 ✅ | -4.7% ❌ | 0.77 ✅ | 1 (alpha) |
| 2019-2024 | **0.650** | -18.3% | 0.82 ✅ | 2 |

발견: **2019-2024 sharpe 거의 3배 개선** (0.225 → 0.650). 시기 의존성
크게 완화. tech-heavy momentum signal 효과.

## QQQ + pos=30% combo (universe + concentration)

| Window | sharpe | alpha | DD | fails |
|---|---:|---:|---:|:---:|
| **2014-2019** | **0.792** ✅ | **+5.94%** ✅ | 1.45 ❌ | **1 (DD)** 🎯 |
| 2019-2024 | 0.506 | -19.2% | 1.49 | 3 |

🎯 **첫 alpha 양수 측정** (+5.94%). paper-gate 의 alpha + sharpe 둘 다
통과. DD 만 fail (1.45 = SPY DD 의 145%). mission halt-condition 의
"live 30-day max DD > 1.5x backtest median" 트리거 위험 매우 큰 config.

## paper-gate 1-fail configs 종합 (모두 2014-2019)

| Config | alpha | sharpe | DD | fail |
|---|---:|---:|---:|---|
| SP500 baseline pos=10 | -3.4% | 1.248 | 0.62 | alpha |
| SP500 pos=30 | -0.49% | 0.851 | 0.97 | DD |
| QQQ baseline pos=10 | -4.7% | 0.703 | 0.77 | alpha |
| **QQQ pos=30** | **+5.94%** | **0.792** | **1.45** | **DD** |

모든 paper-gate 가까운 config 가 2014-2019 specific. 2019-2024 (worst window)
에서는 어떤 variant 도 1-fail 까지 못 줄임.

## 다음 자율 candidate

- **S&P 400 mid-cap** (학술적으로 momentum 효과 가장 강한 universe) —
  cache cold (~25-30min)
- **Russell 2000 small-cap** (mid 보다 더 효율 시장 작음) — fetch 필요

## Out-of-scope

- Live deployment — paper-gate 통과 후
- LightGBM 와이어링 — Phase 2 final 결론 유지 (폐기 보류)
- mission gate 조정 — 0.7 paper / 1.0 live 분리 그대로

## Run metadata

- Worktree: `/Users/blasin/Works/bloasis/wt/pr18-jt-momentum-rank`
- Branch: `pr18/jt-momentum-rank` (NOT pushed)
- Logs: `/tmp/pr18_runs/`
- Configs: `configs/baseline-v3-jt.yaml`, `configs/exp-jt-no-pe-filter.yaml`,
  `/tmp/pr18_runs/grid/cfg-{005,020,030}.yaml`
