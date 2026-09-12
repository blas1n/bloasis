# Daniel-Moskowitz Dynamic Momentum 정밀 분석 (PR12 구현용)

작성일: 2026-05-07
대상: Bloasis PR12 — `bloasis/scoring/regime_overlay.py`
1차 출처: Daniel & Moskowitz, "Momentum Crashes" NBER WP #20439 (2014, JFE 2016 출간) — 본 문서 모든 인용은 이 NBER 풀텍스트 기준 ([NBER PDF 직접 추출 OK](https://www.nber.org/papers/w20439)). Barroso–Santa-Clara 원문은 인증서 만료로 직접 fetch 실패, 보조 문헌 ([Fan-Li-Liu 2017, MPRA #83510](https://mpra.ub.uni-muenchen.de/83510/))의 식 (1)–(2)에 재현된 정의를 사용.

---

## 1. DM 핵심 수식 — 그대로 쓸 수 있는 형태

DM 의 동적 모멘텀(이하 **dyn**) 비중은 Appendix C, Eq. (5):

```
w*_{t-1} = (1 / (2λ)) * μ_{t-1} / σ²_{t-1}
```

- `μ_{t-1}` = 다음 한 달 WML 수익률의 조건부 기대값
- `σ²_{t-1}` = 다음 한 달 WML 수익률의 조건부 분산
- `λ` = 시간불변 스칼라 — 사후적으로 무조건부 변동성을 19% (CRSP VW index 의 풀샘플 값) 에 맞추도록 캘리브레이션 (DM §4.1, Fig. 5 캡션).

### 1.1 기대수익 forecast (μ)

Table 5 column (5) 의 회귀를 그대로 사용. NBER §3.5 Eq. (4):

```
R_WML,t = γ0 + γB·I_{B,t-1} + γ_σ²·σ̂²_{m,t-1} + γ_int·I_{B,t-1}·σ̂²_{m,t-1} + ε_t
```

추정치 (Table 5 col 5, sample 1927:07–2013:03, %/월 환산):

| coef | value | t-stat |
|---|---|---|
| γ0 | +2.129 | 5.8 |
| γB | +0.023 | 0.0 |
| γ_σ² | -0.088 | -0.8 |
| γ_int | -0.323 | -2.2 |

→ 실무적 단순화: `μ_{t-1} ≈ γ0 + γ_int · I_B · σ̂²_m` (`γB`, `γ_σ²` 모두 비유의). DM 본문도 Section 4 시작 부분에서 동일한 단순화를 사용 ("the regression estimated in the last column of Table 5").

### 1.2 분산 forecast (σ²)

DM §4 Eq. (6)-(7), GJR-GARCH(1,1):

```
R_WML,t = μ + ε_t,    ε_t ~ N(0, σ²_t)
σ²_t = ω + β·σ²_{t-1} + (α + γ·I(ε_{t-1}<0))·ε²_{t-1}
```

US 일별 WML 추정치 (NBER Appendix D, MLE):

| param | μ | ω | α | γ | β |
|---|---|---|---|---|---|
| ML est | 0.86×10⁻³ | 1.17×10⁻⁶ | 0.111 | -0.016 | 0.896 |
| t-stat | 14.7 | 4.2 | 14.4 | -1.6 | 85.1 |

특이점: **`γ < 0`** — WML 에서는 음수 충격이 분산을 *낮춘다* (시장 인덱스의 leverage effect 와 부호 반대). 따라서 시장에 쓰는 GARCH 코드 그대로 갖다 쓰면 안 됨.

이후 GARCH 추정치 σ̂_GARCH,t 와 직전 126영업일 실현변동성 σ̂_126,t 를 OLS 로 합성:

```
σ̂_{22,t+1} = 0.0010 + 0.6114·σ̂_GARCH,t + 0.2640·σ̂_126,t,  R²adj = 0.617
```

### 1.3 Bear market indicator I_B

NBER §3.1 Eq. (3) 정의:

> I_{B,t-1} = 1 if cumulative CRSP VW index return over **past 24 months** is negative, else 0.

24개월 — 일반적인 200-DMA 보다 훨씬 긴 윈도우. Sample 의 1,035개월 중 183개월 (17.7%) 이 bear (NBER footnote 4).

### 1.4 σ̂²_m (시장 분산) 정의

NBER Eq. (4) 직후: "ex-ante estimate of the market volatility over the next month, ... variance of the daily returns of the market over the **126-days prior** to time t". 즉 **CRSP/SPY 일일초과수익 126영업일 단순 분산**(연환산 X — DM 회귀에서는 **월별 raw variance** 사용, 회귀계수의 단위가 그것을 흡수).

---

## 2. Barroso–Santa-Clara 비교 (constant-vol 베이스라인)

Fan-Li-Liu 2017 §3.2 Eq. (1)-(2) 의 BSC 재현을 그대로 인용 ([MPRA #83510](https://mpra.ub.uni-muenchen.de/83510/)):

```
σ²_t = (21 · Σ_{j=0..125} r²_{WML,d_{t-1-j}}) / 126        # Eq. (1)
r^CVS_{WML,t} = (σ_target / σ_t) · r_{WML,t}              # Eq. (2)
σ_target = 12% (annualized, monthly target)
```

- 윈도우 126 영업일 ≈ 6개월. 일일 제곱수익의 단순평균 (가중 X). 21배 곱은 일→월 환산.
- σ_target = 12% — Moskowitz–Ooi–Pedersen (2012) 의 futures 표준치.
- BSC 자체 발표 결과 (2차자료): SR 0.53 → 0.97, max DD -96.69% → -45.20%, skew -2.47 → -0.42 ([alphaarchitect 요약](https://alphaarchitect.com/risk-of-momentum-crashes/)).

DM Eq. (5) 와 BSC 의 관계 — DM 본문 §4 직접 인용:

> "the weight on WML would be inversely proportional to the forecast WML volatility — that is the optimal dynamic strategy would be a constant volatility strategy like the one proposed by Barroso and Santa-Clara (2012). However, this is not the case for momentum. In fact, the return of WML is actually negatively related to the forecast WML return volatility."

즉 BSC = "Sharpe 가 시간불변" 이라는 가정 하에 DM 의 special case. 실제 데이터에서 SR 이 시간가변(특히 panic 에서 음수)이므로 DM 이 BSC 를 spans (Table 7 Panel B col 4-6, BSC on dyn 의 alpha 모두 ~0).

---

## 3. 보고된 성능 숫자 (1927:07–2013:03, US WML)

NBER Fig. 5 (전 기간, 모두 19% annualized vol 로 재스케일):

| 전략 | Sharpe | Skew |
|---|---|---|
| 정적 WML | 0.59 | -4.70 (월), -1.18 (일) |
| BSC constant-vol | 1.02 | (positive ~ flat) |
| DM dynamic | **1.19** | (positive) |

분기세기별 (Table에서 추출):

| 구간 | wml | cvol | dyn |
|---|---|---|---|
| 1927–1949 | 0.25 | 0.61 | 0.67 |
| 1950–1974 | 1.13 | 1.33 | 1.48 |
| 1975–1999 | 1.18 | 1.36 | 1.48 |
| **2000–2013** | **0.22** | **0.50** | **0.76** |

→ Bloasis 의 2020-2025 sample 과 가장 가까운 2000-2013 구간에서도 DM 이 정적 대비 SR 을 **3.5x** 끌어올림.

Spanning test (NBER Table 7 Panel A, daily, both portfolios scaled to 23% vol):
- dyn on (Mkt+WML+conditional): α = 23.74%/yr, t = 11.99
- dyn on (FF+WML+conditional): α = 22.04%/yr, t = 11.60
- dyn on (Mkt+cvol): α = 7.27%/yr, t = 6.86 — BSC 를 넘는 7%p 의 정보비율.

---

## 4. 구현 시 주의사항 (gotchas)

1. **Cold start**: 24개월 시장수익이 필요 (`I_B`). +126영업일 σ̂²_m. → 실 거래 시작까지 최소 **506영업일 ≈ 24개월** warmup. Bloasis 가 5년치 데이터를 쓰므로 문제 없음.
2. **데이터 요구**: SPY (또는 CRSP VW) 일별 종가만 있으면 됨. **VIX, 옵션, 분산스왑 불필요** (DM Section 3.6 의 분산스왑 분석은 진단용이지 dyn 비중 계산에는 안 들어감).
3. **시점**: σ̂²_m 와 I_B 모두 t-1 까지의 정보 (look-ahead 없음). 비중 w*_{t-1} 는 월말에 산출, 다음 한 달 동안 고정 (DM 은 monthly rebalance, 월중 daily PnL 은 이 비중으로 그대로 계산).
4. **In-sample/out-of-sample**: DM 본문은 **in-sample** 회귀계수와 in-sample λ 를 사용 (Sample 1927-2013 통째로 fit). Robustness 는 quarter-century subsample 에서 *동일한 캘리브레이션* 으로 작동함을 보임으로써 확보 (NBER §4.2). 실무에선 expanding window 회귀가 더 정직 — DM 자신도 5절에서 다른 자산군에 옮길 때 각 자산군별로 fit.
5. **WML 의 음수 leverage effect**: GJR γ < 0 — 시장 GARCH 와 다름. naive 패키지로 GARCH 추정 시 부호 가정에 주의.
6. **Clip 범위 명시 부재**: DM 원문에는 w* 의 cap/floor 가 명시 안 됨. λ 캘리브레이션이 사실상 스케일을 잡아주지만, μ < 0 이면 음수 비중(short-momentum) 이 나옴 — 이건 의도된 것 (panic 에서 모멘텀을 *반대로* 가는게 최적). 단, leverage 제한이 있는 환경에서는 [0, w_max] 로 clip 하는 게 일반적. BSC 는 명시적 clip 없음 (sigma_target/sigma_t 가 자연 양수).

---

## 5. 후속 문헌 (replication / extension)

- **Fan-Li-Liu (2017, MPRA #83510)**: 55개 글로벌 futures 에서 **CVS(BSC) 가 DVS(DM) 보다 alpha 더 큼** (1.93% vs 1.43%, p=0.002). 단, **2007-2010 위기 기간에는 차이 사라짐** (p=0.96). 즉 DM 의 위기-대응 우위가 단일자산 분석에선 약함을 시사. CVS 가 더 변동성/DD 큰 대신 cumulative return 도 큼 (Sharpe 는 거의 동일 0.39).
- **Barroso-Santa-Clara**: Fama-French momentum factor 1927-2011, 12% target → SR 0.53→0.97, max DD -96.69%→-45.20%.
- **Asness-Pedersen "Volatility-Managed Portfolios"** (Moreira-Muir 2017 JFE) — 시장팩터에 같은 trick 적용, 모멘텀 한정 X. 본 PR 범위 밖.
- **Critique** — DM 우위는 cross-sectional WML (long-short) 한정. 단일자산 trend (TSMOM) 에 비중스케일은 효과 작음 (Fan et al. Table 3, scaled TSMOM Sharpe 0.55, scaled buy-and-hold 0.61, CVS XSMOM 0.39 — Sharpe 면에서 BSC 가 오히려 패).

→ Bloasis 시사점: 우리는 **cross-sectional long-only** (S&P 500 top decile, no shorting) 이므로 DM 의 "loser 옵션성" 메커니즘이 그대로 작동하지 *않음*. crash 가 발생하는 메커니즘은 다름 (단순 베타 노출). 따라서 **DM 의 dyn formula 를 그대로 쓰는 건 과적합 위험** — 우리에게 필요한 건 "panic state 에서 모멘텀 비중을 *낮추는*" 단순 overlay.

---

## 6. Bloasis 구현 결정 (PR12)

목표: 2020 -39% DD, 전체 max DD 비율 1.15 → 0.85 이하로. SR 1.21 유지 또는 향상.

### 결정사항

1. **DM 의 BSC variant 를 채택 (constant-vol scaling)**, DM 의 full dynamic 은 채택 안 함.
   - 이유: (a) Bloasis 는 long-only 라 DM 의 "loser-side option" 메커니즘 부재. (b) Fan-Li-Liu 결과상 위기 기간 DM 우위 사라짐. (c) BSC 는 lookback + target 두 hyperparameter 만으로 단순.
2. **σ_target = 12% annualized** (BSC/MOP 표준).
3. **Lookback = 126 영업일** (BSC 정의 그대로). Bloasis 의 기존 `volatility_20d` 와는 별개로 cross-section 합성 변동성을 따로 계산.
4. **Cross-section vol 정의**: 우리는 WML 포트폴리오가 없으므로 **SPY 일별 수익률의 126일 실현변동성** 을 proxy 로 사용. (SPY 가 panic state 진단에 가장 직접적.)
5. **Bear-market gate**: DM 의 24개월 누적 음수 indicator 를 추가 overlay 로 사용. `I_B = 1` 이면 추가로 0.5 곱 (즉 panic 에서는 BSC 비중에 추가 50% derisk).
6. **Clip range**: scaling factor 를 `[0.0, 1.5]` 로 clip — leverage 1.5x 까지만 허용, 음수 금지 (long-only 제약).
7. **위치**: 월말에 한 번 산출, 다음 한 달간 고정 (DM 과 동일한 monthly rebalance).

### 시그니처 (의사코드)

```python
# bloasis/scoring/regime_overlay.py

from __future__ import annotations
import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

VOL_TARGET_ANNUAL = 0.12          # BSC/MOP standard
VOL_LOOKBACK_DAYS = 126           # ~6 months
BEAR_LOOKBACK_DAYS = 504          # 24 months ≈ 504 trading days
BEAR_DERISK_FACTOR = 0.5          # additional shrink in bear state
SCALE_FLOOR = 0.0
SCALE_CEIL = 1.5


def compute_realized_vol(spy_daily_returns: pd.Series, lookback: int = VOL_LOOKBACK_DAYS) -> float:
    """126일 일별 SPY 수익률 → 연환산 실현변동성. BSC Eq.(1) 의 단순 평균.

    σ²_t = (21·Σ r²) / 126   (월환산)  →  연환산은 √12 곱
    """
    if len(spy_daily_returns) < lookback:
        raise ValueError(f"need >= {lookback} daily returns, got {len(spy_daily_returns)}")
    recent = spy_daily_returns.iloc[-lookback:]
    daily_var = (recent ** 2).mean()           # 평균 r² (BSC: σ² = mean(r²) ≈ var when mean≈0)
    annual_vol = float(np.sqrt(daily_var * 252))
    return annual_vol


def compute_bear_indicator(spy_daily_returns: pd.Series, lookback: int = BEAR_LOOKBACK_DAYS) -> bool:
    """DM §3.1 Eq.(3): 과거 24개월 누적 시장수익 < 0 ? → True"""
    if len(spy_daily_returns) < lookback:
        return False  # cold start: assume neutral
    cum = (1 + spy_daily_returns.iloc[-lookback:]).prod() - 1
    return bool(cum < 0)


def compute_regime_scale(
    spy_daily_returns: pd.Series,
    *,
    vol_target: float = VOL_TARGET_ANNUAL,
    bear_factor: float = BEAR_DERISK_FACTOR,
    floor: float = SCALE_FLOOR,
    ceil: float = SCALE_CEIL,
) -> float:
    """포트폴리오 비중에 곱할 단일 스칼라.

    1. BSC: w_BSC = σ_target / σ_realized
    2. Bear gate: bear 면 추가 *bear_factor*
    3. Clip [floor, ceil]
    """
    sigma_real = compute_realized_vol(spy_daily_returns)
    if sigma_real <= 0:
        return ceil  # degenerate → cap
    w_bsc = vol_target / sigma_real
    is_bear = compute_bear_indicator(spy_daily_returns)
    w = w_bsc * (bear_factor if is_bear else 1.0)
    w_clipped = float(np.clip(w, floor, ceil))
    logger.info(
        "regime_scale_computed",
        sigma_realized=sigma_real,
        w_bsc=w_bsc,
        is_bear=is_bear,
        w_final=w_clipped,
    )
    return w_clipped


def apply_regime_overlay(per_symbol_score: pd.Series, scale: float) -> pd.Series:
    """기존 [0,1] 합성 스코어에 스칼라 곱. 결과는 [0, scale*1] 범위."""
    return per_symbol_score * scale
```

위치: 기존 scoring 파이프라인에서 **합성 스코어 → top-K 선정 → position sizing** 사이에 끼워 넣음. top-K 는 그대로 두되 각 종목 비중에 `scale` 곱.

### 7. Acceptance test

세 가지 OOS 가능한 체크포인트:

1. **2020-03 March 2020 panic**: 2020-03-01 기준 SPY 126일 vol ≈ 35-40% (annualized) → `w_bsc ≈ 12/40 = 0.30`. 24개월 누적은 양수(2018-03~2020-02)였으므로 bear=False, gate 미작동. 최종 scale ≈ 0.30. **테스트: assert 0.20 ≤ scale ≤ 0.40 on 2020-03-23**.
2. **2009-03 Lehman aftermath**: 24개월 누적 음수 (`I_B=1`), vol ≈ 50% → `w_bsc ≈ 0.24`, gate ×0.5 = 0.12. **테스트: assert scale ≤ 0.20 on 2009-03-09**.
3. **Calm market (2017-06)**: vol ≈ 7%, bear=False → `w_bsc ≈ 12/7 = 1.71` → ceil=1.5 로 clip. **테스트: assert scale == 1.5 on 2017-06-30**.

추가 회귀 테스트: PR9 의 Phase1 backtest 를 `regime_overlay` 적용/미적용으로 두 번 돌려, 적용본의 (a) 2020 DD 이 -39% → -25% 이하로, (b) max DD 비율 < 0.85, (c) Sharpe 가 1.10 이상 유지 — 셋 다 통과해야 PR12 머지.

---

## 8. Confidence & 한계

- DM 원문 NBER PDF 는 직접 추출 성공, 모든 수식·숫자는 1차 출처 검증됨.
- BSC 원문은 인증서 만료로 직접 fetch 실패. BSC 의 식 (1)-(2)·target 12%·결과 숫자는 두 개 이상 secondary source ([Fan-Li-Liu MPRA](https://mpra.ub.uni-muenchen.de/83510/), [alphaarchitect](https://alphaarchitect.com/risk-of-momentum-crashes/)) 가 일관되게 보고하므로 신뢰함.
- DM 의 dyn formula 는 long-short WML 가정. Bloasis 의 long-only S&P 500 top-decile 과 메커니즘이 다르다는 점은 본 분석의 가장 중요한 깨달음 — 따라서 BSC variant + bear gate 라는 *축소된 채택* 이 정직한 설계.
