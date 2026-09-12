# AQR 멀티팩터 블렌딩 — 1차 자료 정리 + Bloasis 적용

**작성일**: 2026-05-07
**컨텍스트**: PR12 baseline-v2.yaml 결정용. Quant_References.md §2의 "AQR 블렌드는 long/short 한정 음의 상관" 명제를 고정시키고, long-only 단일자산(S&P 500) 셋업에서 어떤 가중치/구성이 합리적인지 1차 자료로 결정한다.

---

## 1. Quality 정의 — Asness/Frazzini/Pedersen, "Quality Minus Junk" (RAS 2019)

[SSRN 2312432](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2312432) · [AQR working-paper PDF](https://images.aqr.com/-/media/AQR/Documents/Insights/Working-Papers/Quality-Minus-Junk.pdf) · [Yale Shiller mirror](http://www.econ.yale.edu/~shiller/behfin/2013_04-10/asness-frazzini-pedersen.pdf)

QMJ는 Quality를 **4개 sub-pillar 등가중 평균**으로 정의한다. 각 sub-pillar 내부도 **개별 메트릭의 cross-sectional z-score 평균을 다시 z-score**한 합성치다. 즉 z(z(...) + z(...) + ...) 이중 정규화.

**Profitability** = `z( z_GPOA + z_ROE + z_ROA + z_CFOA + z_GMAR + z_ACC )`

- GPOA = (Revenue − COGS) / Total Assets — gross profits over assets (Novy-Marx)
- ROE = NI / Book Equity, ROA = NI / Total Assets, CFOA = (NI + DA − ΔWC − CapEx) / Total Assets
- GMAR = (Revenue − COGS) / Revenue — gross margin
- ACC = −accruals / total assets (낮은 accrual = 높은 quality, 그래서 부호 −)

**Growth** = `z( zΔGPOA + zΔROE + zΔROA + zΔCFOA + zΔGMAR + zΔACC )`

- 5년 변화: 분자 변화량 / **5년 전 분모** (예: ΔGPOA = (GP_t − GP_{t−5}) / Assets_{t−5})

**Safety** = `z( z_BAB + z_LEV + z_O + z_Z + z_EVOL )`

- BAB = −market beta (낮은 베타가 안전)
- LEV = −total debt / total assets, 또는 −leverage 종합
- O = −Ohlson O-score (부도확률), Z = +Altman Z-score (정상기업 확률)
- EVOL = −5년 ROE 표준편차 (수익성 안정성)

**Payout** = `z( z_EISS + z_DISS + z_NPOP )`

- EISS = −net equity issuance (자사주 매입 = +)
- DISS = −net debt issuance
- NPOP = +net total payout / profits

**최종 Quality score** = average(Profitability, Growth, Safety, Payout). 4개 pillar 내부에서 모두 z-score 정규화하므로, 한 메트릭 결측이어도 다른 메트릭들 평균으로 보간된다 (구현 시 결측 처리 주의).

---

## 2. Value+Momentum 블렌드 — Asness/Moskowitz/Pedersen, "Value and Momentum Everywhere" (JOF 2013)

[SSRN 1363476](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1363476) · [AQR dataset](https://www.aqr.com/Insights/Datasets/Value-and-Momentum-Everywhere-Factors-Monthly)

**Value 시그널 (개별주)**: book-to-price (BE/ME), Fama-French 표준 정의. AMP는 단일 메트릭(BP)을 사용했으나 후속 운용 펀드는 BP, EP, CFP, SP 등의 z-score 평균 (composite value).

**Momentum 시그널**: 12-1 (직전 12개월 누적수익에서 가장 최근 1개월 제외). 단기 reversal을 피하는 표준 처방.

**블렌드 비율**: 개별주 long/short에서 50% Value + 50% Momentum 등가중. 보고된 단일 팩터 sharpe ~0.5, 결합 sharpe ~0.9–1.0 (논문 표 4 기준 1972–2011 미국 표본). 핵심 메커니즘은 **L/S 기준 −0.5 ~ −0.65 음의 상관**.

**Vol-normalize step**: 각 long/short sleeve를 60일 realized vol로 나눠 ex-ante 동일 변동성으로 맞춘 뒤 결합. 그렇지 않으면 변동성 큰 momentum이 결합을 지배한다.

---

## 3. Long-only 통합 vs 분리 — Fitzgibbons/Friedman/Pomorski/Serban, "Long-Only Style Investing: Don't Just Mix, Integrate" (FAJ 2017)

[AQR landing page](https://www.aqr.com/Insights/Research/White-Papers/Long-Only-Style-Investing) · [PDF (CDN)](https://images.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Long-Only-Style-Investing-Dont-Just-Mix-Integrate.pdf) · [Swedroe summary](https://larryswedroe.substack.com/p/the-integration-of-factors-advantage)

**이 논문이 Bloasis가 가장 직접 따라야 할 1차 자료다.** Long-only 멀티팩터에서 두 가지 구성 방식을 비교한다.

- **Mixed (a la carte)**: 각 팩터별로 top-decile 포트폴리오를 만들고, 4개 팩터 포트폴리오를 동일 자본으로 합성. 직관적이지만 **상쇄 종목** 문제 발생 — 한 팩터에서는 top decile, 다른 팩터에서는 bottom decile인 종목이 그대로 들어감.
- **Integrated (score blend)**: 종목별로 4개 팩터 z-score를 합산해 단일 합성 스코어를 만들고, 합성 스코어 top-decile만 매수. 모든 팩터에서 동시에 attractive한 종목만 선택.

**실증 결과 (1993–2015 large-cap developed markets)**: 통합 방식이 mixed 대비 (a) **연 ~1.0% 초과수익 추가**, (b) **information ratio +40%**, (c) **회전율 −5~10%**. 팩터 수가 늘수록 효과 증가 (특히 음/저 상관 팩터 결합 시).

**메커니즘**: long-only는 short side가 없어서 "negative-correlation rebalance bonus"를 누리지 못한다. 대신 통합 스코어가 **상쇄 종목을 자동 배제**하여 effective factor exposure를 높인다. 이게 long-only 멀티팩터 alpha의 핵심 원천.

**Bloasis 직접 결론**: 현재 baseline.yaml의 7-bucket 가중평균은 본질적으로 integrated/score-blend 방식이다 — 옳은 출발점. 다만 가중치가 7개로 분산되어 있어 effective factor exposure가 희석. PR12에서 핵심 4팩터(value/quality/momentum/low-vol)에 가중치를 집중시켜야 한다.

---

## 4. AQR Live 펀드 — 시뮬레이션과 라이브의 간극

### QCELX (Large Cap Multi-Style, long-only US large)

[funds.aqr.com/funds/aqr-large-cap-multi-style-fund](https://funds.aqr.com/funds/aqr-large-cap-multi-style-fund) · [Morningstar QCELX](https://www.morningstar.com/funds/xnas/qcelx/quote)

- 벤치마크: Russell 1000 TR
- 라이브 성과 (2026-04-30 기준): 1y +40.83%, 3y +25.93%, 5y +14.66%, **10y +14.69%**
- 동기간 Russell 1000 ~10.03% → 10년 알파 ≈ +4.7%/yr (gross-of-fee, 0.41% expense ratio 차감 전)
- Morningstar Sharpe 1.25 (10y) — long-only 대형주 멀티팩터의 현실적 상단
- 팩터: value + momentum + quality 통합. Sector-neutral은 아니나 sector bet 회피 (net sector exposure −2.21% ~ +4.28%)

**핵심 시사점**: long-only 멀티팩터가 **10년 단위에서 4.7%/yr alpha 달성 가능**. Bloasis의 PR9 결과(연 alpha −18.3%)는 모델 자체의 문제이지 long-only 멀티팩터 패러다임의 문제가 아니다.

### QSPRX/QSPIX (Style Premia Alternative, long/short multi-asset)

[funds.aqr.com/funds/aqr-style-premia-alternative-fund](https://funds.aqr.com/funds/aqr-style-premia-alternative-fund) · [Advisor Perspectives 2023 review](https://www.advisorperspectives.com/articles/2023/12/04/examining-performance-aqrs-premia-alternative-fund)

- **타겟 sharpe 0.70**, 실제 since-inception (2013~) **0.46**. 시뮬레이션 대비 약 35% 미달.
- 2018: −12.3%, 2019: −8.1%, 2020: −21.9~25%, 누적 DD −41.4%. 3년 연속 손실 + 펀드 이탈 발생.
- 2024–2026 회복 (1y +19.6%, 3y +18.9% ann., 5y +18.9% ann.), 그러나 since-inception은 여전히 0.46.
- 의의: **백테스트 sharpe와 라이브 sharpe의 간극은 멀티팩터 펀드에서도 흔하다**. 단순 시뮬 0.9–1.0이 라이브에서 0.5 수준으로 deflate되는 것이 base case.

---

## 5. Defensive (Low-Vol/Quality 보강) — Frazzini/Pedersen, "Betting Against Beta" (JFE 2014)

[BaB paper PDF (Pedersen mirror)](https://docs.lhpedersen.com/BettingAgainstBeta.pdf) · [AQR landing](https://www.aqr.com/Insights/Research/Journal-Article/Betting-Against-Beta) · [Low-Risk Without Industry Bets (FAJ)](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/FAJ-LowRisk-Investing-Without-Industry-Bets.pdf)

BaB factor: 저베타 자산을 베타=1로 leverage하고 고베타 자산을 베타=1로 de-leverage. 시그널은 **rolling 1-year market beta** (또는 Frazzini-Pedersen 식 corr×vol 분해). Long-only 적용 시 단순히 **저베타 종목 overweight + 고베타 underweight** 또는 z-score 기반 통합 점수에 −β 항 추가.

**Bloasis 매핑**: 현재 `volatility` composite (volatility_20d, atr_14, bb_width)이 사실상 low-vol 시그널. BaB의 명시 베타(1y rolling β vs SPY)와는 다르지만, cross-section에서 변동성이 낮은 종목을 선호한다는 점에서 효과는 유사. 추가 베타 시그널을 도입할지는 ablation 측정 후 결정.

---

## 6. Long-only 단일자산 셋업의 정직한 평가

Quant_References.md §2에 정리한 명제를 1차 자료로 재확인:

1. **음의 상관 −0.5는 L/S 한정**. Long-only US large-cap에서 value-momentum 상관은 +0.4–0.6 (시장 베타 공유). Rebalance bonus는 거의 0.
2. **Long-only alpha 원천은 "통합 스코어 → 상쇄 종목 배제"**. AQR 1% per annum 초과수익(IR +40%)이 그 효과 (Fitzgibbons et al. 2017).
3. **QCELX 10년 alpha 4.7%/yr, Sharpe 1.25**가 long-only US large-cap 멀티팩터의 현실적 상단. Bloasis가 PR12에서 노릴 수 있는 것은 이 절반(2–3%/yr alpha, sharpe 0.7–0.9) 수준이 합리적 — 50종목 집중 + 0 비용 가정 deflate 후.
4. **DD 감소는 약함**. QSPRX는 라이브 −41% DD를 겪었고, QCELX도 2022년 SPY와 유사한 DD 노출. 멀티팩터 블렌드는 **alpha 안정화** 도구이지 DD 통제 도구가 아니다. DD는 별도 vol-target + regime overlay로 잡아야 한다 (Daniel-Moskowitz 처방).

---

## 7. Bloasis 구현 결정 (baseline-v2.yaml)

### 핵심 원칙

- **Score blend (integrated)** 방식 유지 — 7-bucket 가중평균은 옳다. 가중치만 재조정.
- **AQR 4-팩터 코어에 80% 가중치**를 몰아주고, 나머지 3 sleeve(technical/liquidity/sentiment)는 보조로 20%. 현재 49% (value 18 + quality 15 + momentum 18 = 51%, 정확히 그 인접) → 80%로 상향.
- **Sleeve별 ex-ante vol 정규화**는 별도 PR에서 (현재 z-score는 cross-sectional이지 vol normalize는 아님). PR12에서는 가중치 재배분만 우선 적용.
- **Sector neutralization은 PR12에서는 skip**. QCELX도 strict neutral은 아님. 50종목 long-only에서는 sector concentration cap(0.30)으로 충분.

### 구체 가중치

```yaml
scorer:
  type: rule
  weights:
    # AQR 4-factor core (80%) — Fitzgibbons et al. 2017 integrated approach
    value: 0.22       # AMP 2013 value sleeve. 18→22 (+4): primary alpha source
    quality: 0.22     # QMJ 2019. 15→22 (+7): long-only에서 가장 robust
    momentum: 0.22    # AMP 2013 12-1 momentum. 18→22 (+4)
    volatility: 0.14  # BaB 2014 proxy (low-vol). 12→14 (+2)
    # Auxiliary sleeves (20%) — 보조 시그널, 명시 cap
    technical: 0.08   # 12→8 (−4): RSI/MACD는 short-horizon noise 큼
    liquidity: 0.04   # 10→4 (−6): S&P 500 universe에서는 차별화 약함
    sentiment: 0.08   # 15→8 (−7): Lopez-Lira 2024 결과상 5–10% cap (Quant_Refs §5)
```

가중 합 = 1.00. 자동 normalize에 의존하지 않고 명시적으로 합 1.0으로 맞춤.

### 가중치 근거 (숫자별)

- **value 0.22 / quality 0.22 / momentum 0.22**: AQR Long-Only Integrated 논문에서 4-factor 등가중이 표준 권장. Bloasis는 4번째(low-vol)를 별도 sleeve로 분리했으므로 핵심 3개에 동일 0.22 부여. 합 0.66은 4-factor 등가중(0.25×3=0.75)에서 low-vol 분만큼 빼고 남은 비율과 정합.
- **volatility 0.14**: BaB factor 비중. AQR style premia에서 defensive는 25% 비중이지만, Bloasis는 단일자산 long-only라 효과 약함을 감안해 14%로 축소. 0.66 + 0.14 = 0.80 (코어 80%).
- **technical 0.08**: 단기 reversal 시그널은 월간 리밸런스 셋업에서 alpha 기여가 작다. PR9 ablation에서 net contribution 미미하면 다음 PR에서 0으로 drop 후보.
- **liquidity 0.04**: S&P 500은 모두 liquid라 cross-sectional 차별화 약함. 그러나 0으로 두면 코드 분기 깨짐 우려, minimum 4%로 유지.
- **sentiment 0.08**: Lopez-Lira & Tang 2024 결과상 LLM sentiment alpha는 2024 이후 sharpe 1.22로 감쇠 + 25bps 비용 가정 시 누적수익 1/7. 5–10% cap 권고에 따라 0.08.

### 추가 변경 (PR12 후속)

1. **Regime multiplier 재조정**: 현재 crisis에서 momentum 0.3×는 너무 약함. Daniel-Moskowitz 식 동적 vol-target이 momentum sleeve에 들어가면 regime multiplier는 0.5× 정도가 적정.
2. **Vol-normalization layer 추가**: 각 sleeve의 cross-sectional z-score를 산출 후, sleeve-level realized return의 60일 std로 다시 나눠 결합 (`combined = Σ w_i × z_i / σ_i`). 이는 baseline.yaml 스키마 변경 동반 (별도 PR).
3. **Acceptance gate를 CPCV 분포 기반으로**: median sharpe ≥ 0.6 AND 5%-quantile ≥ 0.3 (Quant_Refs §4). 점추정 sharpe 0.30이 0과 통계적으로 구분되는지 먼저 측정.

### 솔직한 기대치

- **목표 alpha**: +2.0–3.0%/yr (QCELX 10년 4.7%의 절반 ~ 2/3 수준).
- **목표 sharpe**: 0.70–0.90 (QCELX 1.25는 25년 운용 + risk model 보정 결과; Bloasis 6년 walk-forward + 단순 z-score blend로는 그 절반이 합리적).
- **DD 감소 기대치**: 단일 momentum 대비 −10~15% DD 개선이 상한. AQR live data상 멀티팩터 블렌드는 SPY 대비 max DD ratio 0.85를 단독으로 달성하기 어렵고, vol-target overlay가 추가로 필요.
- **PR12 acceptance 통과 확률**: 현재 sharpe 0.30 → 목표 1.0은 큰 도약. 가중치 재조정만으로는 +0.2–0.3 부스트가 한계. 통과를 위해서는 **(가중치 재조정) + (sleeve-level vol normalize) + (panic-state risk-off) 3종 동시 적용** 필요. PR12를 단일 PR로 보지 말고 PR12a/12b/12c로 분리 고려.

---

## 1차 자료 인용 정리

- Asness, Frazzini, Pedersen, "Quality Minus Junk", Review of Accounting Studies 2019. [SSRN 2312432](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2312432)
- Asness, Moskowitz, Pedersen, "Value and Momentum Everywhere", JOF 2013. [SSRN 1363476](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1363476)
- Asness, Frazzini, Israel, Moskowitz, "Fact, Fiction, and Momentum Investing", JPM 2014. [AQR PDF](https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/JPM-Fact-Fiction-and-Momentum-Investing.pdf)
- Fitzgibbons, Friedman, Pomorski, Serban, "Long-Only Style Investing: Don't Just Mix, Integrate", FAJ 2017. [AQR landing](https://www.aqr.com/Insights/Research/White-Papers/Long-Only-Style-Investing) · [PDF](https://images.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Long-Only-Style-Investing-Dont-Just-Mix-Integrate.pdf)
- Frazzini, Pedersen, "Betting Against Beta", JFE 2014. [Pedersen PDF mirror](https://docs.lhpedersen.com/BettingAgainstBeta.pdf)
- Asness, Ilmanen, Israel, Moskowitz, "Investing with Style", JOIM 2015. [AQR PDF](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/JOIM-Investing-With-Style.pdf)
- AQR Funds, "AQR Large Cap Multi-Style Fund (QCELX)". [Fund page](https://funds.aqr.com/funds/aqr-large-cap-multi-style-fund)
- AQR Funds, "AQR Style Premia Alternative Fund (QSPRX)". [Fund page](https://funds.aqr.com/funds/aqr-style-premia-alternative-fund)
- Advisor Perspectives, "Examining the Performance of AQR's Style Premia Alternative Fund", 2023-12. [Article](https://www.advisorperspectives.com/articles/2023/12/04/examining-performance-aqrs-premia-alternative-fund)
