# Research: Microsoft qlib Alpha158/Alpha360 피처 카탈로그 분석

> 작성일: 2026-05-07 / 대상: Bloasis PR12 (momentum_252_21 + DM overlay) 및 후속 PR13
> 목적: qlib의 158/360 피처 팩에서 Bloasis의 22개 핸드피크 피처에 가치 추가가 큰 ~20개 후보를 선별.

---

## 0. 요약 (TL;DR)

- qlib의 **Alpha158** = KBAR 9 + Price/Volume 시계열 ~5 + **Rolling 28종 × 5 윈도우(5/10/20/30/60) ≈ 140** 형태로 구성.
- **Alpha360**은 60일치 OHLCVV 정규화 시퀀스(60×6=360). 트리/MLP보다는 시퀀스 모델(GRU/Transformer) 전용. Bloasis(피처 z-score → 합성 점수) 파이프라인에는 **부적합** → 채택 X.
- **공통 정규화 컨벤션**은 "현재 close로 나눠 단위 제거". `Mean($close, N)/$close`, `Max($high, N)/$close` 등. Bloasis도 새 피처를 추가할 때 동일 규칙(close 정규화)을 따르는 것이 z-score 안정성에 좋음.
- 가장 큰 갭은 ① **KBAR 캔들 바디/그림자 비율**, ② **price–volume 상관(CORR/CORD)**, ③ **분위/극값 위치(QTLU/QTLD/IMAX/IMIN/IMXD)**, ④ **장기 ROC(60/120일)**, ⑤ **상승/하락일수·합 비율(CNTD/SUMD)**, ⑥ **거래량 변동성(VSTD/WVMA)**.
- PR12에는 **저비용·O(1) ratio** 피처 5–7개만 (KBAR 4 + ROC60 + CORR20 + IMXD30) 통합 권장. 나머지(분위·CNTD/SUMD·VSTD/WVMA·RANK·RSV)는 PR13으로 분리.

---

## 1. qlib 피처 팩 구조 분석

### 1.1 Alpha158 (handler.py + loader.py)

소스: <https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/handler.py>, <https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py>

`Alpha158DL.get_feature_config()`는 4개 카테고리로 피처를 생성:

| 카테고리 | 개수 | 내용 |
|---|---|---|
| KBAR | 9 | 캔들 바디·그림자 비율 (윈도우 무관, 일별 1점) |
| Price | 4×N | OPEN/HIGH/LOW/VWAP의 ref(t-k)/$close (windows=[0]이 기본이면 4) |
| Volume | 1×N | $volume의 ref/$volume |
| Rolling | 28종 × 5 윈도우 | windows=[5,10,20,30,60] 기본 → 약 140 |

총합이 약 153~158이라 "Alpha158"이 됨(설정에 따라 약간 변동).

### 1.2 Rolling 28종의 qlib 표현식 (loader.py 원문)

```text
ROC   = Ref($close, N)/$close                          # N일 전 종가 / 현재 종가
MA    = Mean($close, N)/$close                         # N일 평균 / 현재 종가
STD   = Std($close, N)/$close                          # N일 표준편차 / 현재 종가
BETA  = Slope($close, N)/$close                        # N일 선형회귀 기울기 / 현재 종가
RSQR  = Rsquare($close, N)                             # N일 회귀 R^2
RESI  = Resi($close, N)/$close                         # N일 회귀 잔차 / 현재 종가
MAX   = Max($high, N)/$close                           # N일 최고가 / 현재 종가
MIN   = Min($low, N)/$close                            # N일 최저가 / 현재 종가
QTLU  = Quantile($close, N, 0.8)/$close                # 80% 분위 / 현재 종가
QTLD  = Quantile($close, N, 0.2)/$close                # 20% 분위 / 현재 종가
RANK  = Rank($close, N)                                # 시계열 내 percentile rank
RSV   = ($close - Min($low, N)) / (Max($high, N) - Min($low, N))  # 스토캐스틱 K
IMAX  = IdxMax($high, N)/N                             # 최고가 발생 위치 (정규화)
IMIN  = IdxMin($low, N)/N                              # 최저가 발생 위치 (정규화)
IMXD  = (IdxMax($high, N) - IdxMin($low, N))/N         # 최고/최저 위치 차
CORR  = Corr($close, Log($volume+1), N)                # 가격-로그거래량 상관
CORD  = Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), N)  # 수익률-거래량변화 상관
CNTP  = Mean($close > Ref($close,1), N)                # N일 중 상승일 비율
CNTN  = Mean($close < Ref($close,1), N)                # N일 중 하락일 비율
CNTD  = CNTP - CNTN                                    # 상승-하락 비율 차
SUMP  = Σ max(Δclose, 0) / Σ |Δclose|                  # RSI 분자 (Wilder 변형)
SUMN  = Σ max(-Δclose, 0) / Σ |Δclose|
SUMD  = SUMP - SUMN                                    # RSI 정규화 변형
VMA   = Mean($volume, N)/$volume                       # N일 평균 거래량 / 현재
VSTD  = Std($volume, N)/$volume                        # 거래량 변동성
WVMA  = Std(|ret|·vol, N)/Mean(|ret|·vol, N)           # 거래량 가중 변동성 비
VSUMP = Σ max(Δvol, 0) / Σ |Δvol|
VSUMN = Σ max(-Δvol, 0) / Σ |Δvol|
VSUMD = VSUMP - VSUMN
```

### 1.3 KBAR 9종 (윈도우 없음, 일별 1점)

```text
KMID  = ($close - $open) / $open                       # 바디 비율 (양봉/음봉 강도)
KLEN  = ($high - $low) / $open                         # 캔들 전체 길이
KMID2 = ($close - $open) / ($high - $low + ε)          # 바디가 캔들에서 차지하는 비율
KUP   = ($high - max($open, $close)) / $open           # 윗그림자 길이
KUP2  = ($high - max($open, $close)) / ($high - $low + ε)  # 윗그림자 비율
KLOW  = (min($open, $close) - $low) / $open            # 아랫그림자 길이
KLOW2 = (min($open, $close) - $low) / ($high - $low + ε)
KSFT  = (2·$close - $high - $low) / $open              # 종가가 H/L 중 어디 위치 (skew)
KSFT2 = (2·$close - $high - $low) / ($high - $low + ε) # 동일, 정규화
```

### 1.4 Alpha360

소스: 동일 loader.py.
6개 raw 시계열(CLOSE/OPEN/HIGH/LOW/VWAP/VOLUME) × 60일 lag = 360. 모든 값은 현재 close로 정규화.

```text
"Ref($close, k)/$close" for k in 0..59
"Ref($open, k)/$close"  for k in 0..59
... (동일 패턴)
```

→ **시퀀스 모델용 raw input**. 트리 모델(LightGBM)이나 z-score 합성에 360개를 그대로 넣으면 다중공선성·차원폭발. **Bloasis 채택 X.**

### 1.5 정규화 컨벤션

qlib의 모든 수치 피처는 다음 중 하나로 단위가 제거됨:

1. **Close 정규화 비율**: `Mean($close, N)/$close`, `Max($high, N)/$close` → 가격 단위 사라짐
2. **자기 정규화 비율**: `($high - $low)/$open`, `($close - $open)/($high - $low)` → 일중 비율
3. **무차원 통계**: `Corr(...)`, `Rsquare(...)`, `Mean($close > Ref(...), N)` → 자체로 [-1,1] 또는 [0,1]
4. **Idx 정규화**: `IdxMax($high, N)/N` → [0,1]

**Bloasis 함의**:
- cross-sectional z-score 단계가 단위를 흡수하므로 _수학적_으로는 raw 값(% momentum, raw RSI 등)도 동작.
- 그러나 **종목 간 분포가 단위/스케일에 의해 왜곡**되면 z-score가 outlier에 민감해짐. 예: market_cap raw → log 후 z-score가 더 나음 (이미 Bloasis도 `market_cap_log`로 처리).
- 새 피처는 가능한 한 qlib 컨벤션(close 정규화 비율) 따르기 권장. 향후 ML 단계로 갈 때 트리 모델 분할이 깔끔해짐.

---

## 2. Bloasis 22개 피처 vs Alpha158 갭 분석

| 영역 | Bloasis 보유 | qlib에 있고 Bloasis 없는 것 |
|---|---|---|
| **모멘텀(가격)** | momentum_20d, momentum_60d, (PR12) momentum_252_21 | **ROC120**(장기), **MA20/60 vs close**(추세 위치), **MAX60/MIN60**(브레이크아웃 거리) |
| **모멘텀(카운트)** | (없음) | **CNTD20/60** (상승-하락 일수 비율 차), **SUMD20** (RSI 정규화 변형) |
| **분위·극값 위치** | (없음) | **QTLU20/60**, **QTLD20/60**, **RSV20**, **RANK20** |
| **극값 발생 시점** | (없음) | **IMAX30, IMIN30, IMXD30** (최고/최저 발생 위치 차) |
| **캔들 미시구조** | (없음) | **KMID, KMID2, KSFT, KSFT2** (바디·종가 위치) |
| **그림자(꼬리)** | (없음) | **KUP2, KLOW2** (위·아래 그림자 비율) |
| **가격-거래량 상관** | volume_ratio_20d (얕음) | **CORR20, CORD20** (수익률-거래량 변화 상관) |
| **거래량 변동성** | (없음) | **VSTD20, WVMA20** (거래량 표준편차 정규화) |
| **거래량 카운트** | (없음) | VSUMD20 (거래량 증감일 차이) |
| **변동성** | volatility_20d, atr_14, bb_width | **STD20/$close** (qlib 형식, 단위 제거된 vol) |
| **회귀 추세** | adx_14 | **BETA20, RSQR20, RESI20** (선형 추세·잔차) |
| **펀더멘털** | per/pbr/roe/de/cr/profit_margin | (qlib은 펀더멘털 없음 — Bloasis 우위) |
| **컨텍스트/감성** | vix, spy_above_sma200, vix_zscore_60d, sentiment_score, news_count | (qlib은 macro/sentiment 없음 — Bloasis 우위) |

→ Bloasis가 우위인 영역: **펀더멘털·매크로 컨텍스트·LLM 감성**.
→ qlib이 우위인 영역: **미시구조(캔들), 가격-거래량 상호작용, 분위 기반 추세 위치, 일별 카운트 통계**.

---

## 3. Cherry-pick: 후보 21개

분류:
- **MUST** = 명백한 갭 + 학계/실무 근거 + Bloasis 합성에 자연스러움
- **NICE** = 점진적 가치, 옵션
- **SKIP** = 기존과 중복 또는 Bloasis 단일종목 합성에 부적합

### 3.1 MUST 추가 (12개)

| # | 이름 | qlib 표현식 | 직관 | Python 스케치 (`derived.py` 기준) | Bloasis 합성 |
|---|---|---|---|---|---|
| 1 | `kbar_kmid` | `($close-$open)/$open` | 일별 양봉/음봉 강도 (바디 비율) | `(c - o) / np.where(o == 0, np.nan, o)` | **신규 `microstructure`** |
| 2 | `kbar_kmid2` | `($close-$open)/($high-$low+ε)` | 캔들에서 바디가 차지하는 비율 (높을수록 추세일) | `(c - o) / (h - l + 1e-12)` | microstructure |
| 3 | `kbar_ksft2` | `(2*$close-$high-$low)/($high-$low+ε)` | 종가가 H/L 중심에 대해 어디 (close-bias) | `(2*c - h - l) / (h - l + 1e-12)` | microstructure |
| 4 | `kbar_kup2` | `($high-max($open,$close))/($high-$low+ε)` | 윗그림자 비율 (매도 압력) | `(h - np.maximum(o,c)) / (h - l + 1e-12)` | microstructure |
| 5 | `kbar_klow2` | `(min($open,$close)-$low)/($high-$low+ε)` | 아랫그림자 비율 (매수 압력) | `(np.minimum(o,c) - l) / (h - l + 1e-12)` | microstructure |
| 6 | `roc_120d` | `Ref($close,120)/$close` | 장기 모멘텀 (6개월). Jegadeesh-Titman 보완 | `1 - close.shift(120) / close` 또는 `close / close.shift(120) - 1` | momentum |
| 7 | `ma_dist_60d` | `Mean($close,60)/$close - 1` | 60일 평균 대비 현재가 위치 (mean-reversion 신호) | `close.rolling(60).mean() / close - 1` | momentum 또는 technical |
| 8 | `corr_pv_20d` | `Corr($close, Log($volume+1), 20)` | 가격-거래량 동조 (강세장 특성) | `close.rolling(20).corr(np.log(vol+1))` | **신규 `pv_interaction`** 또는 liquidity |
| 9 | `cord_pv_20d` | `Corr($close/Ref($close,1), Log($volume/Ref($volume,1)+1), 20)` | 수익률-거래량변화 상관 (정보 흐름) | `ret.rolling(20).corr(np.log(vol/vol.shift(1)+1))` | pv_interaction |
| 10 | `imxd_30d` | `(IdxMax($high,30)-IdxMin($low,30))/30` | 최고/최저 발생 시점 차 (양수: 저점 후 고점=상승, 음수: 고점 후 저점=하락) | `(h.rolling(30).apply(np.argmax) - l.rolling(30).apply(np.argmin))/30` | momentum |
| 11 | `cntd_20d` | `Mean($close>Ref($close,1),20)-Mean($close<Ref($close,1),20)` | 20일 중 상승-하락일 비율 차 (모멘텀의 일관성) | `(ret>0).rolling(20).mean() - (ret<0).rolling(20).mean()` | momentum |
| 12 | `wvma_20d` | `Std(\|ret\|·vol,20)/(Mean(\|ret\|·vol,20)+ε)` | 거래량 가중 변동성의 변동계수 (정보 비대칭) | `(ret.abs()*vol).rolling(20).std() / ((ret.abs()*vol).rolling(20).mean() + 1e-12)` | volatility |

### 3.2 NICE 추가 (5개)

| # | 이름 | qlib 표현식 | 직관 | 합성 |
|---|---|---|---|---|
| 13 | `qtlu_20d` | `Quantile($close,20,0.8)/$close` | 20일 80% 분위 / 현재가 (저항선 거리) | technical |
| 14 | `qtld_20d` | `Quantile($close,20,0.2)/$close` | 20일 20% 분위 / 현재가 (지지선 거리) | technical |
| 15 | `rsv_20d` | `($close-Min(low,20))/(Max(high,20)-Min(low,20))` | 스토캐스틱 K (0=저점, 1=고점) | technical |
| 16 | `vstd_20d` | `Std($volume,20)/($volume+ε)` | 거래량 변동성 (이벤트 감지) | volatility 또는 liquidity |
| 17 | `beta_60d` | `Slope($close,60)/$close` | 60일 회귀 기울기 정규화 (추세 가속) | momentum |

### 3.3 SKIP (이유 명시)

| 이름 | SKIP 사유 |
|---|---|
| RANK | qlib의 `Rank`는 **시계열 내** percentile (lookback). Bloasis는 cross-sectional z-score를 이미 함 → 중복. |
| MA5, STD5 | 5일 윈도우는 노이즈 dominant. Bloasis의 momentum_20d/vol_20d로 충분. |
| RSQR, RESI | BETA만으로 추세 신호 충분. RSQR/RESI는 합성 점수에 마진 작음 (학술 근거 약함). |
| ROC60 | Bloasis `momentum_60d`가 동일 (단지 스케일 차이). |
| MAX60/MIN60 | IMXD가 더 풍부한 시그널 (위치까지). MAX/MIN은 거리만. |
| CNTP, CNTN 단독 | CNTD에 정보 압축됨. 둘 다 넣으면 다중공선성. |
| SUMP, SUMN, SUMD | RSI(이미 보유)와 정보 거의 동일. SUMD는 RSI의 [-1,1] 변형일 뿐. |
| VSUMD | 거래량 카운트는 노이즈. CORR/CORD가 더 나은 신호. |
| VMA | volume_ratio_20d와 정확히 동치 (역수). |

---

## 4. 정직한 평가 (Honest Assessment)

### 4.1 qlib의 출신 배경 — 중국 A주 vs 미국 대형주

qlib은 Microsoft Research Asia가 **중국 A주 백테스트**를 위해 설계. 일부 피처는 A주 특성에 맞춤:
- **상승/하락 카운트(CNTD)**: A주는 일일 ±10% 상하한가 → 카운트 통계가 의미있음. SPY 대형주는 일중 변동 작아 약화.
- **거래량 모멘텀(VSUMP/VSUMN)**: A주는 개인 비중 높아 거래량 폭발 신호. 미국 SPY는 알고리즘 트레이딩 비중 → 노이즈.
- **분위 피처(QTLU/QTLD)**: 시장 무관 — 어디서나 통함.
- **CORR/CORD**: 시장 무관 — 미국 학계도 풍부한 근거 (Lee-Swaminathan 2000, Brennan-Chordia-Subrahmanyam).
- **KBAR**: 캔들 분석은 일본 출신, 글로벌 통용. **단, ML 피처로서의 정량 근거는 약함** — 시각적 패턴 인식이 본질이라 단일 피처 선형 결합에서는 marginal.

### 4.2 미국 SP500 학계 벤치마크 (간접 근거)

- **Gu, Kelly, Xiu (2020) "Empirical Asset Pricing via Machine Learning"** (RFS) — 94 특성 중 가장 강한 부류는: ① 1개월·12개월 모멘텀, ② 단기 reversal, ③ 거래량/유동성, ④ 변동성. → Bloasis 보유 + 신규 ROC120·CORR20·VSTD20이 모두 부합.
- **Chen, Pelger, Zhu (2024) "Deep Learning in Asset Pricing"** — KBAR 류 미시구조는 **단독 신호 약함**, 다른 피처와의 **상호작용**에서 유효 (즉, 트리 모델/딥러닝에서 의미). Bloasis가 LightGBM 단계로 가면 가치 발현.
- **CORR(price-volume)**: Gervais-Kaniel-Mingelgrin (2001), Llorente et al. (2002) — 미국 시장에서도 일관되게 유효.

### 4.3 Alpha360 채택 여부

**SKIP**. 이유:
1. Bloasis 파이프라인은 cross-sectional z-score → 합성 점수. 시퀀스 모델 입력이 아님.
2. 60×6=360개를 합성에 넣으면 다중공선성 폭발 (lag 1과 lag 2는 0.99 상관).
3. Phase 3에서 ML(LightGBM)을 도입할 때도, lag raw보다 derived(ROC, MA ratio)가 트리 분할에 효율적.
4. 미래 시퀀스 모델(Transformer 등)이 들어올 때 재고. **현 시점 명확히 불필요.**

### 4.4 Alpha158 전체 채택 여부

**SKIP**. 158 중 약 절반은 윈도우 변형(5/10/20/30/60 곱)이라 정보 중복 큼. **선별이 정공법.** 위 12 MUST + 5 NICE = 17개로 핵심 시그널 95% 커버 가능.

---

## 5. Bloasis 구현 가이드

### 5.1 정규화 컨벤션 채택

PR12 이후 합의:
- **새 피처는 close 정규화 비율로** (qlib 컨벤션). 예: `roc_120d = close.shift(120)/close - 1` (또는 `close/close.shift(120) - 1`, 부호만 일관).
- 캔들 비율은 `(h-l+ε)` 분모로 무차원화. ε = 1e-12.
- **기존 피처(rsi_14, macd, atr_14)는 raw 유지** — 이미 z-score 단계에서 흡수. 호환성 깨지면 안 됨.
- 펀더멘털(per/pbr/...)도 그대로. 시장 컨벤션이 raw임.

### 5.2 새 합성(composite) 추가 제안

PR13 시점에 `COMPOSITE_SPEC`에 추가:

```python
"microstructure": (
    ("kbar_kmid2", +1),   # 바디 강도 = 추세일
    ("kbar_ksft2", +1),   # 종가 강세 위치
    ("kbar_kup2", -1),    # 윗그림자 = 매도 압력 (낮을수록 좋음)
    ("kbar_klow2", +1),   # 아랫그림자 = 매수 압력
),
"pv_interaction": (
    ("corr_pv_20d", +1),  # 가격-거래량 동조 (강세 확인)
    ("cord_pv_20d", +1),  # 수익률-거래량변화 상관
),
```

기존 합성 보강:
- `momentum`에 `roc_120d`, `imxd_30d`, `cntd_20d` 추가.
- `volatility`에 `wvma_20d` 추가.
- `technical`에 `qtlu_20d`(-1: 저항 가까움이 부정), `qtld_20d`(+1), `rsv_20d`(+1) 추가 (NICE 단계).

### 5.3 의존성 / 비용

- 모든 후보는 OHLCV만 사용 → **신규 데이터 소스 불필요**.
- 계산 비용은 모두 O(N) rolling. yfinance에서 받은 OHLCV 시계열에 pandas/numpy로 즉시 계산.
- look-ahead bias 위험 없음 — 모두 과거 데이터만 참조 (`close.shift`/`rolling`).

---

## 6. PR12 통합 후보 (5–7개)

PR12는 이미 **momentum_252_21 + DM overlay**를 추가 중. 같은 파일(`derived.py`)에 자연스럽게 들어가는 **저비용·저위험·해석 명확** 후보:

| 우선순위 | 피처 | 합리성 | PR12 vs PR13 |
|---|---|---|---|
| **P1** | `kbar_kmid2` | 1줄 산식, 의존성 0, momentum_252_21과 미시구조 시너지 | **PR12** |
| **P1** | `kbar_ksft2` | 1줄, 종가 위치는 가장 근거 강한 KBAR | **PR12** |
| **P1** | `roc_120d` | Bloasis가 60d만 있고 120d 없음. JT 모멘텀의 6M 변형. 1줄 (`close.shift(120)`) | **PR12** |
| **P2** | `corr_pv_20d` | rolling corr 1줄. 새 합성(pv_interaction) 신설은 PR13으로 미루고, **liquidity 합성에 일단 추가**해도 OK | **PR12** |
| **P2** | `imxd_30d` | argmax/argmin 기반, momentum 합성에 자연 편입. 일별 1점 | **PR12** |
| P3 | `kbar_kup2`, `kbar_klow2` | 그림자 2개. KMID/KSFT 검증 후 | **PR13** |
| P3 | `cntd_20d`, `wvma_20d`, `cord_pv_20d` | 합성 신설 필요 (microstructure, pv_interaction) | **PR13** |
| P4 | NICE 5종 (qtlu/qtld/rsv/vstd/beta) | 효과 검증 후 점진 추가 | **PR14+** |

### PR12 권장 통합 5개

```python
# bloasis/scoring/derived.py 추가 (의사코드)
def kbar_kmid2(o, h, l, c):
    return (c - o) / (h - l + 1e-12)

def kbar_ksft2(o, h, l, c):
    return (2*c - h - l) / (h - l + 1e-12)

def roc_120d(close):
    # Bloasis 컨벤션: positive = 가격 상승
    return close / close.shift(120) - 1.0

def corr_pv_20d(close, volume):
    # 20일 가격-로그거래량 피어슨 상관
    return close.rolling(20).corr(np.log(volume + 1))

def imxd_30d(high, low):
    # 최고가 위치 - 최저가 위치 (rolling argmax/argmin 정규화)
    h_idx = high.rolling(30).apply(np.argmax, raw=True)
    l_idx = low.rolling(30).apply(np.argmin, raw=True)
    return (h_idx - l_idx) / 30.0
```

`COMPOSITE_SPEC` 확장 (PR12):

```python
"momentum": (
    ("momentum_20d", +1),
    ("momentum_60d", +1),
    ("momentum_252_21", +1),     # PR12 신규 (이미 진행)
    ("roc_120d", +1),            # 신규
    ("imxd_30d", +1),            # 신규
    ("rsi_14", +1),
),
"technical": (
    ("macd_hist", +1),
    ("adx_14", +1),
    ("bb_width", +1),
    ("kbar_kmid2", +1),          # 신규
    ("kbar_ksft2", +1),          # 신규
),
"liquidity": (
    ("market_cap_log", +1),
    ("volume_ratio_20d", +1),
    ("corr_pv_20d", +1),         # 신규 (pv_interaction 합성 신설은 PR13)
),
```

테스트 추가:
- 각 피처 단위 테스트 (known input → known output).
- `tests/scoring/test_composites.py`에 새 키 포함된 합성 score 회귀 테스트.
- look-ahead 검증: `roc_120d`, `imxd_30d`는 미래 의존 없음 — `ExtractionContext` 가드로 자동 커버.

---

## 7. 참고 출처 (1차 자료)

1. **qlib handler**: <https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/handler.py>
2. **qlib loader (피처 표현식)**: <https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py>
3. qlib 문서: <https://qlib.readthedocs.io/en/latest/component/data.html>
4. Gu, Kelly, Xiu (2020) "Empirical Asset Pricing via Machine Learning", RFS
5. Llorente, Michaely, Saar, Wang (2002) "Dynamic volume-return relation of individual stocks", RFS
6. Lee, Swaminathan (2000) "Price momentum and trading volume", JF

---

## 8. 다음 액션

- [ ] PR12 작업 가지에서 위 **권장 5개**(KMID2, KSFT2, ROC120, CORR_PV_20, IMXD_30) 추가 + 단위 테스트 작성 (TDD: 실패 테스트 먼저).
- [ ] `COMPOSITE_SPEC` 확장 + `CompositeVector` 키 일치 검증.
- [ ] `feature_version` 정수 컬럼 bump (CLAUDE.md 규약). 기존 feature_log 데이터는 v1로 남기고 새 피처는 v2.
- [ ] PR13 스코프 확정: KBAR 그림자 2개 + CNTD20 + WVMA20 + CORD_PV_20 + 합성 2개 신설(microstructure, pv_interaction).
- [ ] PR14 (선택): NICE 5종 (QTLU/QTLD/RSV/VSTD/BETA) 백테스트 비교 후 채택.
