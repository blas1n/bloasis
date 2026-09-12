# Bloasis Quant References (PR12 Pre-Read)

**작성일**: 2026-05-06
**컨텍스트**: 6년 walk-forward 결과 (sharpe 0.30, alpha -18.3%) 후 long-momentum 적용 + DD 통제 설계 단계. 본 문서는 PR12 의사결정에 직접 영향 줄 다섯 편의 1차 자료를 압축 정리한다.

---

## 1. Daniel & Moskowitz, "Momentum Crashes" (JFE 2016)

[SSRN 2371227](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2371227) · [NBER w20439](https://www.nber.org/papers/w20439) · [JFE 122(2): 221-247](https://www.sciencedirect.com/science/article/pii/S0304405X16301490)

논문의 핵심 주장은 단순한 WML(winners-minus-losers) 모멘텀이 정상 시기에는 견조하지만, 드물게 발생하는 **모멘텀 크래시(momentum crash)**가 누적 alpha의 상당 부분을 한 번에 지운다는 것이다. 1927–2013 미국 표본에서 가장 심각한 두 사례는 **1932년 7–8월** (loser decile +232%, winner decile +32% — WML이 약 -200%) 과 **2009년 3–5월** (loser decile +163%, winner decile +8% — WML 약 -155%)이다. 두 시기 모두 베어 마켓 직후의 강한 리바운드 국면이며, 이 패턴이 우연이 아니라 구조적이라는 것이 논문의 주장이다.

크래시가 발생하는 조건은 정량적으로 두 가지로 압축된다: (i) **bear market state** — 직전 24개월 시장 누적 수익률이 음(-)인 상태, (ii) **high realized volatility** — 시장 변동성이 상위 분위. 이 조건이 결합될 때 loser 포트폴리오의 옵션-유사 베타가 음(-)에서 큰 양(+)으로 점프하여 시장 리바운드 시 winner 대비 폭발적 수익을 낸다. 즉, 정태적 WML은 bear+rebound 국면에서 *short call* 같은 페이오프 구조를 가진다.

저자들의 처방은 **dynamic momentum** — 매월 momentum strategy의 조건부 평균(μ̂)과 분산(σ̂²)을 예측하여 가중치를 `w_t = (1/2λ) × μ̂_t / σ̂²_t` 로 스케일링한다 (λ는 위험회피). 실증 결과: 정태적 WML 대비 **alpha와 Sharpe ratio가 약 2배** (대략 0.5 → 1.0 수준)로 개선되며, 스타일 팩터(FF3, Carhart)로 설명되지 않는다.

**Bloasis 함의**: PR11 파일럿에서 sharpe 1.21, max DD 1.15× SPY로 fail한 원인 중 하나가 정확히 이 구조 — 12-1 momentum이 베어 마켓 리바운드에 노출된 결과로 보인다. PR12에서 **반드시 동적 vol-targeting을 추가**해야 한다. 구체적으로: (a) 60일 realized vol로 sleeve 변동성을 **연 12% 타겟**에 맞추기, (b) SPY 24개월 누적 수익률 < 0 이면서 VIX z-score(60d) > 1.5 인 "panic state"에서 momentum sleeve 가중치를 **50%로 자동 축소** — 이는 우리 vix_zscore_60d / spy_above_sma200 피처로 즉시 구현 가능하다. 정태적 momentum-only는 이 논문 결과상 즉시 폐기.

---

## 2. AQR (Asness, Frazzini, Israel, Moskowitz) — "Fact, Fiction, and Momentum Investing" (JPM 2014) + "Investing with Style" (JOIM 2015)

[SSRN 2435323 (Fact/Fiction/Momentum)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2435323) · [AQR PDF](https://images.aqr.com/-/media/AQR/Documents/Journal-Articles/JPM-Fact-Fiction-and-Momentum-Investing.pdf) · [Investing With Style PDF](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/JOIM-Investing-With-Style.pdf) · [Value & Momentum Everywhere (Asness/Moskowitz/Pedersen 2013)](https://www.aqr.com/Insights/Datasets/Value-and-Momentum-Everywhere-Factors-Monthly)

AQR의 핵심 주장은 모멘텀이 단독으로는 크래시 위험을 가지지만 **value와 음의 상관**(long/short 기준 약 -0.5 ~ -0.65)을 가지므로 두 팩터를 결합하면 sharpe가 크게 개선된다는 것이다. "Fact, Fiction" 논문은 모멘텀에 대한 10가지 통념을 1900년대 이후 212년 데이터로 반박하며, 그 중 핵심은 (i) 모멘텀은 거래비용 후에도 살아남는다, (ii) 단독 사용보다 value/quality와 결합 시 거래비용/회전율이 자연 감소한다는 점이다.

**구체 블렌드 비율**: AQR의 multi-asset Style Premia 펀드는 자산군 7개 (개별주 30%, 산업 10%, 주가지수 15%, 국채 10%, 금리선물 5%, 통화 15%, 원자재 15%)에 4개 스타일 (value, momentum, carry, defensive/quality) 을 등가중 배분한다. 주식 단일 자산군 내에서 권장되는 단순 블렌드는 **value 50% / momentum 50%** (AFM "Value and Momentum Everywhere" 2013) 이며 — 이 조합이 단일 팩터 대비 sharpe를 거의 두 배로 높인다 (각각 ~0.5 → 결합 ~0.9–1.0). Quality(profitability+earnings stability)를 추가한 3-팩터 등가중은 다시 sharpe 약 +0.1–0.2 부스트.

**Vol-targeting 메커니즘**: AQR은 각 sleeve를 동일한 ex-ante 변동성(보통 연 10–12%)으로 normalize한 뒤 결합한다. 이렇게 하면 가장 변동성 높은 sleeve(보통 momentum)가 결합 포트폴리오를 지배하지 않는다. 결합 후 다시 portfolio-level vol target(예: 10%)으로 lever up/down. **DD 감소 메커니즘**은 단순한 분산이 아니라 **negative correlation × rebalance bonus** — Asness 본인 표현으로 "약 0.66%/yr 의 추가 alpha"가 리밸런싱 자체에서 나온다 (단, 집중 포트폴리오 한정).

**중요한 caveat**: 이 음의 상관관계는 **long/short 기준**이다. Long-only 포트폴리오에서는 value와 momentum이 **둘 다 시장 베타 양 +1**을 공유하므로 상관관계가 +0.4–0.6 수준으로 올라가고, "rebalance bonus" 효과는 크게 감소한다.

**Bloasis 함의**: Bloasis는 long-only 단일 자산군(US large cap)이라 AQR의 long/short 결과를 직접 적용할 수 없다. 하지만 두 가지는 그대로 가져갈 수 있다 — (1) **각 composite sleeve를 ex-ante 60d vol로 normalize한 뒤 결합** (현재 blend는 raw z-score 합산이라 momentum sleeve가 지배적). (2) **value + long_momentum + quality 3-sleeve 등가중 + portfolio vol-target 12%** 를 PR12 기본 구성으로. PR11의 momentum-only sharpe 0.50은 정확히 vol-normalize 안 된 단일 sleeve의 한계를 보여준다. 추가로 sentiment sleeve는 weight를 5–10%로 명시 cap (3번 토픽에서 다시 다룸).

---

## 3. Microsoft qlib — Alpha158 / Alpha360

[microsoft/qlib repo](https://github.com/microsoft/qlib) · [handler.py](https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/handler.py) · [loader.py (실제 표현식 정의)](https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py) · [qlib docs](https://qlib.readthedocs.io/en/latest/component/data.html)

**Alpha360**은 단순하다 — 6개 OHLCV+VWAP 시계열 × 60일 lag = 360 features. 모두 `Ref($field, lag) / $close` 또는 `/ ($volume+1e-12)` 형태로 최신 값에 normalize. 인간이 만든 피처 엔지니어링이 아니라 ML 모델이 패턴을 학습하도록 하는 raw input이다.

**Alpha158**은 사람이 설계한 158개 기술적 지표로, 카테고리별로 다음과 같다.

- **KBAR (9개)**: 캔들 형상 — KMID `(close-open)/open`, KLEN `(high-low)/open`, KMID2 `(close-open)/(high-low)`, KUP/KUP2 (위 그림자), KLOW/KLOW2 (아래 그림자), KSFT/KSFT2 (close 위치).
- **Price (4×N)**: window별 `$open/$close`, `$high/$close`, `$low/$close`, `$vwap/$close`.
- **Volume (1×N)**: `$volume / (Ref($volume,1)+1e-12)`.
- **Rolling (multiple categories × multiple windows {5,10,20,30,60})**:
  - 추세/모멘텀: ROC `Ref($close,d)/$close`, MA `Mean($close,d)/$close`, BETA(Slope), RSQR(R²), RESI(잔차)
  - 변동성: STD `Std($close,d)/$close`, VSTD(volume std), WVMA(volume-weighted vol)
  - 극단값: MAX `Max($high,d)/$close`, MIN, QTLU(80th pct), QTLD(20th pct), IMAX/IMIN(극값까지 거리), IMXD
  - 상대 위치: RANK `Rank($close,d)`, RSV (recent strength)
  - 상관: CORR(가격-거래량), CORD(price change vs volume change)
  - 방향성 카운트: CNTP(positive day count), CNTN, CNTD; SUMP(positive return sum) / SUMN / SUMD
  - 거래량: VMA, VSUMP, VSUMN, VSUMD

**Bloasis 22 피처와 비교**:

| 카테고리 | Bloasis 보유 | qlib 추가 후보 | 평가 |
|---|---|---|---|
| Value/Quality 펀더멘털 | per, pbr, market_cap, profit_margin, roe, debt_to_equity, current_ratio | qlib에 없음 (qlib은 가격/거래량 only) | Bloasis 우위 |
| 모멘텀 | momentum_20d, 60d | ROC over {5,10,20,30,60} | 60d 위/아래 lookback 추가 가치 있음 |
| 변동성 | volatility_20d, atr_14, bb_width | STD/WVMA over multiple windows | 거래량 가중 변동성(WVMA) 신규 |
| 기술적 | rsi_14, macd*, adx_14 | qlib은 rolling primitive; RSI 등 명시 안 함 | Bloasis 우위 |
| 거래량 | volume_ratio_20d | VMA, VSUMP/N/D, CORR(price,volume) | **유의미 보강** (정보 거래량 vs noise 거래량 구분) |
| 캔들 형상 | 없음 | KBAR 9종 | **신규 카테고리** — 단기 reversal에 유효 |
| 극단값/순위 | 없음 | RANK, IMAX, QTLU/D | **유의미 보강** (Cross-sectional rank가 long-only blending에 핵심) |
| 시장 regime | vix, spy_above_sma200, vix_zscore_60d | qlib은 single-name only — regime 피처 없음 | Bloasis 우위 |

**중복**: Bloasis의 momentum_20d/60d, volatility_20d, atr_14는 qlib의 ROC/STD와 사실상 같다. 옮겨올 가치 있는 것은 **(a) KBAR 9종, (b) RANK / IMAX / IMIN / QTLU / QTLD, (c) volume-price 상관 CORR/CORD, (d) WVMA**. 도입 시 22 → ~40개 피처. 158개 전부 가져오는 건 long-only S&P 500 + 월간 리밸런스 셋업에서 노이즈 비율이 너무 높다.

**Bloasis 함의**: 피처 일괄 확장보다는 **선별 import** — KBAR/Rank/CORR 카테고리만 추가. 더 중요한 건 qlib 디자인 철학에서 가져올 점: **모든 피처를 `/ $close` 또는 `/ vol`로 normalize하여 cross-sectional 비교 가능하게 만드는 규약**. 현재 Bloasis 피처 일부는 절대값(ATR, market_cap)이라 cross-sectional ranking에 직접 못 쓰고 z-score 변환에 의존 — qlib 식 normalization 전처리 레이어를 추가하면 sleeve 결합이 깔끔해진다.

---

## 4. Lopez de Prado — Combinatorial Purged Cross-Validation (AFML 2018, Ch. 7)

[Wikipedia: Purged cross-validation](https://en.wikipedia.org/wiki/Purged_cross-validation) · [mlfinlab CPCV docs](https://www.mlfinlab.com/en/latest/cross_validation/cpcv.html) · [mlfinlab CPCV source](https://github.com/hudson-and-thames/mlfinlab/blob/master/mlfinlab/cross_validation/combinatorial.py) · [QuantInsti tutorial](https://blog.quantinsti.com/cross-validation-embargo-purging-combinatorial/)

표준 walk-forward k-fold가 시계열에서 편향되는 이유는 **label horizon overlap** — 예를 들어 학습 셋에 포함된 t-시점 관측치의 label이 [t, t+H] 구간 미래 수익률이라면, test 셋이 [t+1, t+H] 구간을 덮을 때 학습 셋이 이미 답을 본 셈이 된다. 추가로 자기상관/지연반응으로 test 직후 구간도 정보 누출원이 된다.

**Purging (제거)**: 학습 셋에서 label horizon이 test 구간과 시간상 겹치는 모든 관측치를 제거. 정의 그대로 — "Remove from the training set any observation whose timestamp falls within the time range of formation of a label in the test set."

**Embargo (격리)**: test 셋이 끝난 직후 일정 비율(보통 1–5%)의 관측치를 학습에서 추가 제외. 자기상관/뉴스 lag으로 인한 leakage 차단. 핵심 — **embargo는 test 이전이 아니라 이후에만 적용** (test 이전은 purge가 처리).

**CPCV 경로 산출**: 데이터를 N개 균등 그룹으로 나누고, **모든 C(N,k) 조합**을 test로 사용. 각 조합 내 k개 그룹은 각각 별개 test fold가 되고, 동일 test fold가 여러 train 조합에서 다시 등장한다. 결과적으로 각 시점은 k개의 다른 model fit으로 평가받는다. **고유 백테스트 경로 수**: φ(N,k) = (k/N) × C(N,k). 예: N=6, k=2 → C(6,2)=15 splits, paths = (2/6) × 15 = **5개 경로**. AFML 7장의 표준 권장은 N=6, k=2.

**Bloasis 현재 셋업과 비교**: Bloasis는 15-fold walk-forward (test=120d, step=120d), 즉 **단일 경로**만 보고 있다. 6년(약 1500거래일) / 120d = 12.5 fold. CPCV (N=6, k=2)로 바꾸면 — 같은 데이터에서 5개 백테스트 경로가 나오고, sharpe/alpha/DD를 단일 점추정이 아닌 **분포**로 측정 가능. 현재 sharpe 0.30 점추정이 표준오차 ±0.2 안인지 ±0.5 밖인지 알 수 없는 상태인데, CPCV는 이걸 정량화한다. PBO(Probability of Backtest Overfitting) 계산도 자연스레 가능.

**Bloasis 함의**: PR12 acceptance gate를 **점추정 임계값**에서 **분포 기반**으로 바꿔야 한다. 구체적으로 — (a) 현재의 walk-forward 외에 CPCV(N=6, k=2) 평가를 병행, (b) 5개 경로의 sharpe 중앙값과 5%-quantile을 함께 보고, (c) acceptance를 "median sharpe ≥ 0.6 **AND** 5%-quantile ≥ 0.3" 형태로. 라벨 horizon은 월간 리밸런스 + 21d holding이라 purge 윈도우는 ±21거래일, embargo는 1% (~15거래일)면 충분. 구현은 mlfinlab 또는 skfolio의 `CombinatorialPurgedCV` 클래스 그대로 import. 현재 sharpe 0.30이 5개 경로 중 4개에서 음수로 나온다면 PR12 진입 자체를 재고해야 한다 — 이걸 측정하지 않은 채 PR12 디자인하는 건 위험.

---

## 5. Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?" (SSRN 2023, 4412788)

[SSRN 4412788](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4412788) · [arXiv 2304.07619](https://arxiv.org/abs/2304.07619) · [arXiv HTML v6 (확장 버전, 2024)](https://arxiv.org/html/2304.07619v6) · [Wharton 2024-09 deck](https://jacobslevycenter.wharton.upenn.edu/wp-content/uploads/2024/09/Lopez-Lira.pdf)

**Setup**: Universe는 미국 보통주 4,123개, 기간은 **2021년 10월 ~ 2024년 5월** (확장 버전 기준; 초기 2023 버전은 2021-10 ~ 2022-12). 뉴스 소스는 주요 newswire의 헤드라인. 프롬프트는 단순 — "Forget all previous instructions. Pretend you are a financial expert... Is this headline good, bad, or neutral for the company's stock?" 형식의 zero-shot 분류. 각 헤드라인을 -1/0/+1로 라벨링하고, 다음 거래일 시초가 매수, 종가 매도하는 long-short 포트폴리오 구성.

**보고된 성과 (gross)**: GPT-4 long-short next-day strategy 연환산 **Sharpe 3.8**, GPT-3.5 sharpe 3.1, BERT/GPT-2/GPT-1은 유의미하게 낮음 — 모델 크기와 forecast 능력이 거의 monotone하게 비례. **거래비용 적용 시**: 10bps/trade 비용 가정 시 sample 기간 누적 350% 수익, **25bps/trade 가정 시 누적 50%로 추락** (전략의 회전율이 높아 비용 민감도 큼).

**시간에 따른 성과 감쇠**: 이 논문에서 가장 중요한 — annualized sharpe가 2021Q4 **6.54** → 2022 **3.68** → 2023 **2.33** → 2024 1–5월 **1.22**로 **단조 감소**. 저자들 본인 해석은 LLM 채택 확산 + 시장 효율성 증가 = arbitrage 소멸. 즉, 논문이 발표된 사실 자체가 alpha를 깎는 양의 피드백.

**비판/한계**: (1) **Look-ahead 가능성** — GPT-4의 학습 데이터 cutoff와 백테스트 기간 겹침 (2023 버전 cutoff 2021-09 vs 백테스트 시작 2021-10이라 거의 경계선). 저자들은 cutoff 이후 헤드라인만 사용한다고 명시하나, 모델이 비슷한 산업 패턴을 prior로 가졌을 가능성 배제 어려움. (2) **소형주 집중** — 드리프트 효과는 small-cap + negative news에서 특히 강하게 나오므로, S&P 500 같은 대형주만 거래 시 sharpe가 크게 줄어든다. (3) **거래비용 + 회전율** — daily rebalance라 25bps 가정도 아마 낙관적. 슬리피지 포함 실거래 환경에서 1.22 sharpe도 추가 deflate 가능. (4) **2026 시점 ceiling 추정**: 후속 연구(Modern Finance 2024 등) 결과로 최신 sharpe는 **0.5–1.0 수준**, 즉 단독 alpha source로 쓰기엔 부족하고 **보조 sleeve 5–10% 가중치**가 현실적 상한.

**Bloasis 함의**: 현재 Bloasis sentiment sleeve가 7-composite 안에 있는데, **단독 sleeve로 뜨겁게 안고 가면 안 된다**. 구체적으로 — (a) sentiment sleeve 가중치를 portfolio-level **5–10% cap**으로 명시, (b) 평가 윈도우는 2024 이후 데이터만 사용 (2023 이전은 LLM-pre-adoption alpha라 inflate), (c) **거래비용 모델링 필수** — 현재 백테스트가 zero-cost라면 sentiment sleeve의 net contribution은 거의 0일 가능성 큼. PR12 single-feature ablation에서 sentiment를 켜고/끈 net-of-cost sharpe 차이가 0.05 미만이면 sleeve 자체를 drop. LLM sentiment를 메인으로 안고 가는 설계는 2026년 시점에서 시간상 늦었다 — momentum + value + quality + vol-target 코어를 먼저 견고히 한 뒤 sentiment를 5% 미만 보조로.

---

## 종합 권고 (PR12 설계 결정)

1. **정태적 momentum-only 폐기, dynamic vol-targeted momentum 채택**: 60일 realized vol로 momentum sleeve를 연 12% vol target에 맞추고, panic state(SPY 24m return < 0 AND vix_zscore_60d > 1.5)에서 sleeve 가중치를 50%로 자동 축소. Daniel-Moskowitz 결과상 sharpe 약 2배, DD 절반 기대.

2. **3-sleeve 등가중 코어 (long_momentum + value + quality)**: 각 sleeve를 ex-ante 60d vol로 individually normalize한 뒤 33/33/33 결합, portfolio-level vol target 10–12%로 lever 조정. AQR 식 multi-factor construction. 단일 모멘텀 대비 sharpe +0.3–0.5, DD ratio 0.85 임계값 통과 가능성 ↑.

3. **Sentiment sleeve는 5–10% 가중치 cap, net-of-cost ablation 통과 시에만 유지**: Lopez-Lira 결과는 2024년 시점 sharpe 1.22로 감쇠했고 25bps 비용 가정 시 누적 수익 1/7로 줄어듦. 단독 alpha source로 가정 금지.

4. **피처 확장은 선별 import**: qlib에서 KBAR(9), RANK/IMAX/QTLU/QTLD(~8), CORR/CORD(2), WVMA(1) 약 20개만 추가. 158 일괄은 노이즈/회전율 폭증. 기존 22개와 합쳐 ~40개가 long-only S&P 500 셋업 적정선. 모든 신규 피처는 qlib 식 `/ $close` normalize 규약 적용.

5. **CPCV(N=6, k=2) 평가 도입, acceptance gate를 분포 기반으로 전환**: walk-forward 단일 경로 외에 5개 CPCV 경로의 sharpe/alpha/DD 분포 산출. 새 acceptance: "median sharpe ≥ 0.6 AND 5%-quantile ≥ 0.3 AND median DD ratio ≤ 0.85". 현재 sharpe 0.30 점추정이 통계적으로 0과 구분되는지 먼저 측정 — PR12 진입 전 1주 내 검증.

6. **거래비용을 backtest engine에 1급 시민으로**: 슬리피지(~5bps) + commission(~1bps) + half-spread(~3bps) ≈ 한쪽 9bps 보수 가정. 월간 리밸런스 가정 시 회전율 약 80%/yr → 연 비용 ~70bps. 이 수치를 모든 sleeve ablation 결과에 차감하지 않으면 sentiment 같은 high-turnover sleeve를 잘못 채택할 위험.

7. **Panic-state risk-off 룰 명시화**: spy_above_sma200=False AND vix_zscore_60d > 1.5 동시 충족 시 (i) momentum sleeve 0.5×, (ii) cash 비중 +20%p, (iii) 신규 진입 정지. Daniel-Moskowitz는 정확히 이 국면에서 momentum이 옵션-유사로 페이오프 구조가 변한다고 보였고, 우리 vix/spy regime 피처가 이미 있으므로 코드 수정량 적음.
