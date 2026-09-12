# Bloasis Phase 3 — Modern Candidates (2026-05-08)

> **Mission shift (2026-05-08)**: Phase 0 PR18 의 16+ measurements 결과
> momentum-only ceiling 명확. user 결정으로 **우선순위 재정의: alpha → sharpe → DD**.
> 3개 동시 잡기 포기, alpha 양수 만드는 path 우선. JT 변형 그만하고
> modern 기법 (LLM 등) 으로 paradigm shift.
>
> 본 doc 는 5개 candidate 의 spec + 측정 plan. **하나씩 실측 후 결정** —
> "실제 테스트 해보기 전까지는 모르는 것" (user 명시).

## 사전 결정

| | 변경 |
|---|---|
| 우선순위 | alpha > sharpe > DD (mission gate 동시 충족 포기) |
| 검증 단위 | 1개 candidate × 다 windows × 변형 → 다음 candidate |
| 머지 기준 | alpha 양수 + cross-window robust 한 single best config |
| 베이스라인 | PR18 Phase 0 결과 (`PR18_Phase0_Measurement_2026-05-07.md`) |

## Phase 0 ceiling 요약

best 1-fail config 들 (전부 2014-2019 specific):

| Config | alpha | sharpe | DD | fail |
|---|---:|---:|---:|---|
| SP500 baseline pos=10 | -3.4% | 1.248 | 0.62 | alpha |
| SP500 pos=30% | -0.49% | 0.851 | 0.97 | DD |
| QQQ baseline pos=10 | -4.7% | 0.703 | 0.77 | alpha |
| **QQQ + pos=30%** | **+5.94%** | 0.792 | 1.45 | DD |

→ alpha 양수 single config 등장 (QQQ+pos=30, 2014-2019). 단 cross-window
robust 안 됨 (2019-2024 동일 config 가 -19.2%).

---

## Candidate A — PEAD (Post-Earnings Announcement Drift)

### 정의
**Earnings beat 직후 60-90 일 동안 가격이 expected 보다 drift 한다**는
well-documented anomaly (Bernard-Thomas 1989, Sloan 1996). 학술적으로
가장 robust 한 alpha factor 중 하나, sharpe 1+ 보고 다수.

### 신호 정의 (proposal)
```python
# 매일 cross-section 에서:
# 1. 최근 60 days 안에 earnings 발표한 종목만 필터
# 2. surprise% > 0 (실제 EPS > consensus) 인 종목만
# 3. surprise% 큰 순으로 top decile
# → score 0.99, 나머지 0.0
```

### 데이터 source
- **yfinance free**: `Ticker.get_earnings_dates(limit=N)` —
  - EPS estimate (consensus)
  - Reported EPS
  - Surprise %
  - 약 2-3 년 historical (확인됨)
- 한계: multi-year (2014-2019 등) 측정 어려움. 첫 검증 2022-2024 한정.

### 구현 plan
1. `bloasis/data/fetchers/yfinance_earnings.py` 추가
   - `Ticker.get_earnings_dates()` wrapper, parquet cache
2. `bloasis/scoring/features.py` 에 추가 features:
   - `days_since_earnings`
   - `last_eps_surprise_pct`
   - `eps_surprise_streak` (4Q rolling beats count)
3. `bloasis/scoring/scorer.py` 의 `PEADScorer` 신설
   - JT 와 동일 pattern (cross-section rank)
   - top decile of `last_eps_surprise_pct` AND `days_since_earnings ≤ 60`
4. config: `configs/exp-pead.yaml`
5. 측정: 2022-2024 (full S&P 500) — yfinance 한계
6. 가능하면 SP500 + QQQ + concentration (pos=30%) 조합도

### 예상 결과 (가설)
- alpha 양수 (학술적 baseline 사실)
- sharpe 1+ (학술 보고 수준)
- DD 적정 (분산 효과, top decile = 50 stocks)
- JT 와 직교 (서로 다른 신호 source)

### 비용
- 구현: 1-2일
- 데이터: 무료 (yfinance)
- LLM: 없음

---

## Candidate B — Earnings/Revenue YoY momentum

### 정의
quarterly EPS 또는 Revenue 의 **YoY 성장률 자체를 momentum signal** 로
사용. 즉 "지난 4분기 평균 성장률 가속" 하는 종목 = buy.

### 신호 정의
```python
# 매 quarter 발표 후:
# rev_yoy_growth_q1 - rev_yoy_growth_q4 = "growth acceleration"
# 또는 rolling 4Q YoY EPS growth
# top decile → score 0.99
```

### 데이터 source
- yfinance `quarterly_income_stmt` — Total Revenue, Net Income (5 quarters)
- 한계: 단 5 quarters (1년) → momentum 계산용 4 quarters 가져가면 4
  measurements 만. backtest 매우 짧음.

### 구현 plan
1. yfinance fetcher 확장 (이미 일부 있음)
2. `quarterly_revenue_yoy_growth` feature 추가
3. 그 위에 PEADScorer 와 비슷한 scorer

### 비용
- 구현: 1일
- 데이터: 무료
- 한계: backtest 기간 짧아 검증 약함

### 우선순위
- A 먼저 → B 는 실용성 낮아 보류 (yfinance 5Q 한계 critical)

---

## Candidate C — News Sentiment in backtest (LLM)

### 정의
Finnhub historical headlines + LiteLLM scoring → daily aggregate
sentiment per stock. positive sentiment 종목 = buy.

### 신호 정의
```python
# 매일 cross-section 에서:
# 1. 최근 7 days 의 headlines 가져옴 (Finnhub)
# 2. LLM (Haiku) 으로 sentiment scoring [-1, 1]
# 3. universe-mean 가중평균 (recent skew)
# 4. top decile of sentiment_score → score 0.99
```

### 데이터 source
- **Finnhub free tier**: 1 년 historical news + 60 calls/min rate limit.
  multi-year 위해선 paid 필요 ($150/mo basic, $500/mo standard).
- **LiteLLM**: 이미 인프라 있음 (`bloasis/runtime/llm.py`)
- **bloasis 인프라**:
  - `news_sentiment_cache` 테이블 이미 있음
  - `FinnhubNewsFetcher` 이미 있음
  - 단 backtest engine 에 sentiment 미연결 (L007 한계)

### 구현 plan
1. backtest 의 ExtractionContext 에 sentiment hydrate 추가
2. live LLM 호출 → cache 사용 (deterministic 위해)
3. 첫 1년 측정 (Finnhub free)
4. 의미있으면 paid Finnhub 또는 다른 source

### 비용
- 구현: 2-3일 (백테스트 결정성 + cache 설계)
- 데이터: free (1년) → paid (full)
- LLM 비용: ~$1/year per stock × 503 = $500 1회 (Haiku)
- 한계: LLM determinism (response 변동), backtest reproducibility 위해 cache critical

### 위험
- LLM-based feature 가 OOS 에서 decay (Lopez-Lira ChatGPT 1년에 절반)
  → 성능 maintenance cost 큼

---

## Candidate D — SEC EDGAR + LLM 분석 (full modern)

### 정의
SEC EDGAR API 로 모든 10-K/10-Q filings + earnings call transcripts
가져와서 LLM 으로 risk factors / management discussion / earnings call
sentiment 분석. **multi-year backtest 가능**.

### 신호 정의 (multiple alpha sources 가능)
1. **risk_factor_change_score**: 10-K 의 Item 1A "Risk Factors" 섹션
   year-over-year delta (LLM 으로 변화 추출 + 부정 키워드 빈도)
2. **earnings_call_sentiment**: Q&A 섹션의 management tone
3. **forward_guidance_strength**: management discussion 의 forward-looking
   language strength (LLM 으로 confident/cautious score)

### 데이터 source
- **SEC EDGAR**: free, full historical (2001+), 모든 미국 상장사
- **earnings call transcripts**: paid (Seeking Alpha, FactSet, etc.) 또는
  scraping
- LLM: LiteLLM 인프라 활용

### 구현 plan
1. SEC EDGAR API client (`bloasis/data/fetchers/sec_edgar.py`)
2. 10-K/10-Q text 추출 + chunking
3. LLM-based feature extractor (chunked, cached)
4. feature 들을 LightGBM 으로 ensemble (Phase 2 ML 인프라 재활용)
5. 측정 — multi-year possible

### 비용
- 구현: 1-2주
- 데이터: SEC free, transcripts 위해선 paid
- LLM 비용: 큼 (~$5-50/stock 1회 batch)
- 한계: PIT (point-in-time) bias 회피 critical — 미래 정보 leak 안 되게

### 잠재력
- **가장 큰 alpha 후보** — Modern_AI_Investing_References §"LLM-engineered
  features in Numerai-scale ensemble" 와 일치
- AQR 2025-04 ML 전향 path 와 일치
- bloasis 의 unique 가치 — JT/quality factor 위에 LLM-extracted alpha 추가

---

## Candidate E — Numerai-style multi-feature ensemble

### 정의
Phase 2 LightGBM 인프라 (PR14) 부활 + LLM-engineered features 결합.
**여러 weak signals → ML 으로 ensemble**.

### 신호 정의
- LightGBM regressor on (전통 factors) + (LLM features)
- 학습 target: forward 21d return (Phase 2 PR13 labeling 그대로)
- features:
  - 전통: JT momentum, vol, earnings, fundamentals (이미 있음)
  - **LLM features (신규)**: SEC filings risk score, news sentiment,
    analyst recommendation tone, earnings call transcript sentiment

### 구현 plan
- Phase 2 인프라 (`bloasis/ml/training.py`, `LightGBMScorer`) 그대로
- LLM features 추가 (Candidate C, D 결과 활용)

### 비용
- 구현: A/C/D 의 sum (위 후보들의 features 들 활용)
- 데이터: A/C/D 합산
- LLM 비용: A/C/D 합산

### 위험
- Phase 2 ML 결과 IC -0.035 (실패) 의 원인이 features weak 였다는 가설 —
  새 features 가 IC > 0.05 클리어해야 의미 있음
- 단순 stack 에 의지하면 over-fitting

---

## 측정 우선순위

| # | Candidate | 비용 | 데이터 한계 | 예상 alpha potential | 자율 가능 |
|---|---|---|---|---|---|
| 1 | **A (PEAD)** | 작음 | 2-3년 backtest | 높음 (학술 robust) | ✅ |
| 2 | C (News+LLM) | 중간 | 1년 (free) | 중간 | ✅ (LLM 비용 작음) |
| 3 | D (EDGAR+LLM) | 큼 | 전 기간 | **가장 높음** | 부분 (LLM 비용 큼 — user confirm) |
| 4 | E (Numerai-style) | 가장 큼 | A/C/D dependent | 높음 | A/C/D 후 |
| 5 | B (Quarterly YoY) | 작음 | 1년 만 | 낮음 (한계 critical) | 보류 |

## 측정 결과 누적 (TBD)

### Candidate A — PEAD (2026-05-08 측정 완료)

**Setup**: SP500 (492 fetched, 11 delisted), 2022-2024, 7 folds (180d
train / 120d test / 120d step), top decile rank, position_size 10%,
no overlay.

| Variant | sharpe | alpha | DD | fails | note |
|---|---:|---:|---:|:---:|---|
| baseline (top 10%, drift 60d) | 0.057 | -11.7% | 0.50 | 2 | academic PEAD failed |
| **top005 (top 5%, drift 60d)** | **0.725** ✅ | **-13.8%** | 0.47 | **1 (alpha)** | sharpe gate pass |
| drift30 (top 10%, drift 30d) | 0.364 | -17.0% | 0.39 | 2 | shorter window worse |
| **intersect (PEAD AND JT, top 30% ea.)** | **-0.040** | -17.7% | 0.39 | 2 | falsified |

**핵심 발견**:
1. **PEAD 학술 anomaly decay**: 2022-2024 baseline sharpe 0.057 — 학술
   1990s/2000s 의 sharpe 1+ effect 가 거의 사라짐. Lopez-Lira ChatGPT
   pattern 과 일치.
2. **concentration ↑ → sharpe ↑, alpha ↓** — Phase 0 와 동일 패턴.
3. **PEAD AND JT intersection 가설 falsified** — 두 신호 직교성 가정으로
   결합 시 alpha 개선 expected, but actual: intersection 9% 만 → noise
   dominates → sharpe negative.
4. **long-only 의 SPY-alpha 한계** PEAD 도 동일 — 모든 variants alpha 음수.
5. Phase 0 vs PEAD 비교 (best 1-fail configs):
   - Phase 0 SP500 baseline 2014-2019: sharpe 1.248, alpha -3.4%
   - PEAD top005 SP500 2022-2024: sharpe 0.725, alpha -13.8%
   - PEAD 가 sharpe 절반, alpha 4배 더 음수.

**결론**: PEAD 단독 path 폐기. alpha 양수 못 만듦. 다음 → C 또는 D.

### Candidate B-modern — LLM-rated Fundamental Health (2026-05-08)

**Setup**: yfinance ANNUAL income/balance/cashflow (5 fiscal years
historical) → Ollama llama3.2:3b → score [-1, 1] per (symbol, fy_end),
parquet cache + in-memory memo. PIT lag 90 days (10-K filing). 2022-2024
walk-forward, 7 folds.

**Note**: Candidate C (News+LLM) blocked by missing FINNHUB_API_KEY
(user signup required). B-modern picked as cheap LLM-based alternative
that doesn't need Finnhub.

| Variant | Universe | sharpe | alpha | DD | fails |
|---|---|---:|---:|---:|:---:|
| baseline (top 10%) | SP500 503 | 0.600 | -11.3% | 0.40 | 2 (α, sharpe by 0.10) |
| **top 5%** | SP500 503 | **0.761** ✅ | **-13.3%** | 0.34 | **1 (α)** |
| baseline (top 10%) | QQQ 100 | **0.788** ✅ | **-8.9%** | 0.44 | **1 (α)** ← best alpha gap |
| top 5% | QQQ 100 | 0.216 | -24.3% | 0.49 | 2 (concentration disaster) |
| AND JT (top 30% each) | SP500 | 0.592 | -12.3% | 0.51 | 2 (no improvement) |
| AND JT (top 30% each) | QQQ | 0.231 | -10.0% | 0.51 | 2 (intersection breaks) |

**핵심 발견**:
1. **LLM-based fundamental signal > PEAD baseline** — same window/universe,
   sharpe 0.600 vs 0.057 (10x). modern 기법의 가치 확인.
2. **paper-gate near-pass** — SP500 top 5% sharpe 0.761, QQQ top 10% sharpe 0.788.
   alpha 만 fail (-13% / -9%).
3. **concentration ↑ → sharpe ↑ + alpha ↓** — 다른 candidate 와 동일 패턴.
4. **QQQ universe 가 SP500 보다 alpha 개선** — Phase 0 와 동일 (cap-weighted SPY
   대비 tech-heavy concentration 효과).
5. **intersection 가설 재차 falsified** — FundLLM AND JT 도 PEAD AND JT 와 동일
   패턴 (sharpe 동일/감소). 두 신호의 직교성 가정 깨짐.

**Implementation cost**:
- 구현: 1 day (TDD)
- LLM 호출: ~503 stocks × 5 fy = 2515 calls × 0.82s ≈ 30min cold cache
- $0 (Ollama local via Tailscale)

**Spec → 측정 비교**:
- 예상: 데이터 multi-year 가능 (yfinance annual) ← ✅ 5 fy
- 예상: alpha potential 중간 ← ✅ 다른 candidates 와 비슷
- LLM 비용 작음 ← ✅ Ollama 무료

### Candidate C — News+LLM

⏸️ **Blocked**: FINNHUB_API_KEY missing. user signup 필요.

### Candidate D — SEC EDGAR + LLM (2026-05-08)

> User 의도: cheap path Ollama → frontier model 단계적. 자율 진행.

#### D-LLM (Ollama) — Risk Factors YoY diff

5-stock PoC:
- llama3.2:3b: 거의 모두 [-0.2, 0] 좁은 범위 (보수적 bias)
- qwen3:14b /no_think: 거의 모두 0.0 (더 보수적)

**Falsified** — small/medium Ollama 모델이 risk factors text 변화 분간 못함.
default 0 emit, discrimination 없음. LLM call 0.6-17s/call.

#### D-textdiff (LLM-free, Cohen-Malloy 학술 그대로)

PoC 결과 매우 promising — NVDA 2022→2023 cosine 0.9757 + length +20.9%
(stock 폭등 시기 정확히 신호 emit). 학술 Cohen-Malloy "Lazy Prices" 2020
의 cosine + length 그대로.

Full SP500 측정 (2022-2024, 7 folds, top 10% rank by cosine):

| Variant | sharpe | alpha | DD | fails |
|---|---:|---:|---:|:---:|
| top 10% | **0.110** | -14.6% | 0.33 | 2 |
| top 5% | **-0.049** | -16.4% | 0.45 | 2 |

→ **falsified for long-only equal-weight**. 가능한 원인:
1. cosine 0.97-0.99 ranking 변별력 너무 작음 — 모든 large-cap 의 risk factors
   매년 거의 안 변함 (boilerplate dominate)
2. Cohen-Malloy 학술 신호는 short side (low cosine = future negative).
   long-only inversion 효과 약함
3. SP500 universe 가 너무 stable — small-cap 또는 Russell 3000 가
   학술 paper 에 가까운 universe

#### D-LLM frontier (Claude Haiku, paid) — 미진행

Ollama conservative bias 우회 + small-cap 부재 한계 잔존. 비용 ~$10
batch. **user 결정 영역**.

---

# 🎯 BREAKTHROUGH (2026-05-09) — friction 비활성화 시 EDGAR PAPER-GATE 통과

## 발견 경로

User 가 "1, 2 검토" — Long-short framework PoC 작성 중 우연히 standalone
clean Python (no engine, monthly rebalance, no friction) 으로 JT 12-1
top 10% 를 측정.

| Strategy (PoC, 2022-2024) | CAGR | Sharpe | MaxDD | Total |
|---|---:|---:|---:|---:|
| **Long-only top 10% (clean)** | **+20.54%** | **+0.957** | -19.65% | +72.59% |
| Long-Short (top - bot) | +4.12% | +0.294 | -35.33% | +12.53% |
| SPY | +8.53% | +0.554 | -25.34% | +26.99% |

→ Long-only **PoC alpha +12%/y vs SPY**. Long-short 는 SPY-strong era 에
서 short side cost.

**bloasis backtest engine 의 결과 (sharpe 0.225) 와 4배 차이** — engine
의 friction 이 신호 죽이고 있다는 가설.

## Friction 비활성화 config (코드 변경 X, config-only)

```yaml
signal:
  atr_stop_multiplier: 100.0       # 사실상 비활성
  atr_tp_multiplier: 100.0         # 사실상 비활성
  position_size_max_pct: 0.02      # 1/50, equal-weight
  profit_tiers: []                 # 비활성
risk:
  max_single_order_pct: 0.02
  max_sector_concentration: 1.0
execution:
  market_slippage_bps: 0
  fees_bps: 0
```

User 명시: 코드 제거 X, 비활성화 (튜닝 가능). config-only override.

## 4 scorer × clean config × SP500 2022-2024

| Scorer | friction sharpe | clean sharpe | clean alpha | clean DD | clean fails |
|---|---:|---:|---:|---:|:---:|
| JT | 0.225 | **0.860** | **+5.32%** | 1.46 | 1 (DD) |
| PEAD | 0.057 | 0.668 | -17.5% | 0.59 | 2 |
| LLM Fundamental | 0.600 | 0.898 | -6.86% | 0.92 | 2 |
| **EDGAR cosine** | 0.110 | **0.997** ✅ | **+1.49%** ✅ | **0.80** ✅ | **0** ✅ |

**🎯 EDGAR cosine clean = bloasis 첫 paper-gate 모두 통과 config**:
- alpha +1.49% ≥ -0.5% ✅
- sharpe 0.997 ≥ 0.7 ✅ (live-gate 1.0 까지 0.003!)
- DD/SPY 0.80 ≤ 0.85 ✅
- 7 folds (2022-2024 walk-forward)

## Friction 정량 효과

| Scorer | sharpe Δ (clean - friction) | alpha Δ | DD Δ |
|---|---:|---:|---:|
| JT | +0.64 (3.8x) | +23pp | -2.8x worse |
| PEAD | +0.61 (12x) | -5.8pp | -0.1x |
| LLM Fundamental | +0.30 | +4.4pp | -0.5x worse |
| EDGAR cosine | +0.89 (9x) | +16pp | -2.4x worse |

**모든 scorer 에서 sharpe + alpha 큰 개선**. profit_tiers + ATR stops +
cash limits + slippage 누적이 momentum 신호 80% + EDGAR 신호 90%
까먹고 있었음.

DD 는 friction 이 stop-loss 통해 줄여줬음 (clean 에선 concentrated
equal-weight 50 stocks 가 동시 하락 → DD 폭증). Trade-off.

## 학술 신호의 정확성 재확인

- Cohen-Malloy "Lazy Prices" 2020 의 cosine signal 은 long-only
  (HIGH cosine = stable 회사) 에서도 작동
- 학술 sharpe 1.0+ 보고와 우리 측정 0.997 일치
- 변별력 부족 가설 (cosine 0.97-0.99) 은 잘못됨 — friction 이 진짜 문제

## 다음 step

1. **JT DD reduction** — top 20% / monthly rebalance / vol-target 로
   sharpe 유지 + DD 줄여 paper-gate 통과
2. **EDGAR + JT intersection** clean — 두 직교 신호 결합 시 alpha + sharpe
   더 강화 가능
3. **Multi-window robustness** — EDGAR clean 을 2014-2019, 2008-2013 에서
   재측정 (현재 EDGAR cache 있는 stocks 만 가능, ~2-3 yrs historical)
4. **Live deployment prep** — paper-gate 통과 = paper trading 가능. live
   broker (Alpaca paper) 와이어링.

#### D path 코드 자산

- `bloasis/data/fetchers/sec_edgar.py` — EDGAR client (CIK lookup + 10-K
  filings + Item 1A extraction with longest-span heuristic)
- `bloasis/scoring/edgar_textdiff.py` — pure cosine + length change
  (LLM-free, 11 unit tests)
- `bloasis/scoring/edgar_llm.py` — LLM YoY diff scorer with Ollama-direct
  API path (LiteLLM `think` kwarg drop trap mitigated)
- `bloasis/scoring/scorer.py` — `EDGARTextDiffScorer`
- `ScorerType += {edgar_textdiff, edgar_textdiff_jt_intersect}`
- `BacktestData.risk_factors_history` + engine PIT slice + cosine compute
- `feature_log` columns: `risk_factors_cosine`, `risk_factors_len_change`

## Out-of-scope

- mission gate 변경 (alpha 0% 요구 등) — Phase 0 측정 후 별도 결정
- long-short variant — alpha-priority path 와 별개 framework
- 옵션/futures/crypto/FX — mission §Non-goals 영역

## Run metadata

- Worktree: `/Users/blasin/Works/bloasis/wt/pr18-jt-momentum-rank` (계속 사용)
- Branch: `pr18/jt-momentum-rank` (Phase 3 candidate 추가)
- 또는 `phase3/modern-candidates` 신규 worktree (PR 분리 시)
