# Modern AI Investing References — Bloasis 재설계 참고 (2026-05-07)

Phase 1/2 중단 (rule + LightGBM, 23 features, S&P 500, 5개월) 직후, 단독 JT 12-1 모멘텀이 동일 데이터에서 sharpe 1.21을 보여 합성/threshold 프레임워크가 병목임이 확인된 시점. 본 문서는 2024-2026 실무 관점에서 "지금 무엇이 작동하는가"를 정리한 redesign 입력이다. 학계 클래식(Fama-French, JT, Lopez de Prado AFML)은 `docs/research/Quant_References.md`에 이미 정리되어 있으므로 중복하지 않는다.

## 1. Modern AI Investing YouTube 채널 + 실무자 영상

### Robot Wealth — "edge first, ML second"
- 채널 운영자 Kris Longmore, Robot James (Hodges) 중심. 13,000+ 뉴스레터 구독. 핵심 메시지는 **"왜 누가 너에게 반대편을 잡아주고 돈을 줄 것인가를 먼저 답하라, 모델은 그 다음"**. 트랜스포머/LSTM 비판이 일관됨.
- "Machine Learning for Trading - What Does it Really Look Like?"는 David Aronson 류 실험을 따라 한 시리즈로, 결론은 "**raw price feature + 복잡 모델은 거의 항상 노이즈를 학습한다**". (https://robotwealth.com/machine-learning-financial-prediction-david-aronson/)
- Bloasis 시사점: ML scorer가 IC -0.035 였던 것은 모델 잘못이 아니라 input feature pool 설계 단계의 edge 부재 가능성이 크다. 23 features 중 economic prior가 명확한 게 몇 개인지 다시 셀 것.

### QuantConnect / LEAN
- LEAN은 사실상 retail-grade 인프라의 표준이 되어가는 중. 300+ 헤지펀드, Python 3.11, Lean CLI로 로컬 개발 + 클라우드 백테스트 동기화 가능. (https://www.lean.io/, https://github.com/QuantConnect/Lean)
- 2024-2025 핵심 업데이트: research-to-live parity (백테스트 코드 그대로 라이브 배포), Strategy Library (학술 논문 → LEAN 구현 포팅).
- Bloasis 시사점: Phase 3에서 라이브 paper trading을 하려면 자체 인프라 짜는 대신 LEAN으로 옮기는 것을 진지하게 검토. universe loader, factor pipeline 재구현 비용보다 LEAN 통합 비용이 작을 가능성.

### Algovibes (https://www.youtube.com/c/Algovibes)
- 입문자 친화적 Python pandas 백테스트. 본격 ML 콘텐츠는 부족, 대체로 RSI/MACD/MA 류 기술적 지표 + 단순 ML wrapper. **hype 측 — quant 진지한 작업에는 reference로 쓰기 어려움**.

### Sentdex (Harrison Kinsley, https://www.youtube.com/channel/UCfzlCWGWYyIQ0aLC5w48gBQ)
- ML/Python 일반 채널. 2017년 Quantopian 시리즈 이후 finance 본격 콘텐츠는 사실상 dormant. **시청 우선순위 낮음**.

### Hayden Van Der Post / The Plain Bagel
- "Plain Bagel"은 Richard Coffin (전 portfolio manager), 일반 투자 교육 채널 — quant ML 직접 신호는 없음. Hayden Van Der Post는 Amazon의 Python 트레이딩 책 시리즈를 다수 출판하지만 **AI generated content 의심이 많고 실증 numbers가 거의 없다**. 무시 권장.

### Tucker Balch (Georgia Tech "Computational Investing")
- Coursera 강의 + Lucena Research. 클래식 (2015-2019) 콘텐츠는 가치 있으나 2024-2026 신규 활동은 미미. **레퍼런스용**.

### 한국어 채널 / 자료
- **퀀티랩 (quantylab)** GitHub — Keras 기반 강화학습 주식 투자 코드/책. (https://github.com/quantylab) 한국 내 한정으로 가장 진지한 오픈소스. 다만 기본 framework 수준이고 alpha-bearing 시스템은 아님.
- "AI 트레이딩" 키워드 한국어 검색 결과 대부분이 광고성 ("48% META 수익률") — **거의 모두 hype, 무시**. 진지한 한국어 콘텐츠는 학회 논문 (한국재무학회) 외에는 사실상 없음.

## 2. 최신 (2024-2026) 학술 + 실무 논문

### LLM 기반 stock prediction — Lopez-Lira (UF) 시리즈
- 핵심 finding: GPT-4가 헤드라인 → 다음날 수익률 방향을 예측. **그러나 sharpe가 시간이 지날수록 급격히 감소: 2021Q4 sharpe 6.54 → 2022 3.68 → 2023 2.33 → 2024 1.22**. (https://arxiv.org/abs/2304.07619 v6, 2025-10-28)
- Cutoff 이전 데이터에서 90% hit rate인 반면 cutoff 이후에서는 drift만 살짝 잡힘. **결론: alpha decay가 빠르고, 무엇보다 GPT 자체의 학습 데이터가 retroactively contamination 되는 구조. 표면 수치 그대로 못 믿는다.**

### Time-Series Foundation Models — TimesFM, Chronos, Kronos
- Google **TimesFM 2.5** (2025-10) — 100B time points 사전학습, zero-shot univariate forecasting. (https://github.com/google-research/timesfm)
- Amazon **Chronos-2** (2025-10-20) — multivariate, covariate 지원. Chronos-Bolt: 250x 추론 속도 개선. (https://github.com/amazon-science/chronos-forecasting)
- **Kronos** (2025) — 금융 전용 foundation model, 12B+ K-line records 사전학습 (45 거래소). (https://jonathankinlay.com/2026/02/time-series-foundation-models-for-financial-markets-kronos-and-the-rise-of-pre-trained-market-models/)
- Recent benchmark "Re(Visiting) Time Series Foundation Models in Finance" (https://arxiv.org/html/2511.18578v1) 논문 conclusion: **generic TSFM은 financial-specific 모델보다 underperform**. zero-shot로 직접 트레이딩 알파를 뽑는 시도는 거의 실패.

### Reinforcement Learning — FinRL Contests 2024-2025
- 종합 결과: **single-agent PPO sharpe 0.69 → CVaR-PPO/sentiment-augment sharpe 1.08**, 단 cumulative return 기준이지 cross-section ranking은 아니다. (https://arxiv.org/html/2504.02281v3)
- Crypto: ensemble sharpe 0.28 (사실상 noise). Hi-DARTS hierarchical agent on AAPL: sharpe 0.75, return 25.17% vs SPY 20.01%.
- **냉정 평가: FinRL 경연의 sharpe 1.0 근방 결과들은 single-stock 또는 small basket이고, S&P 500 cross-section에 옮기면 대부분 깨진다**. RL을 portfolio construction에 쓸 때 noise reduction이 가장 큰 문제.

### LLM Multi-Agent Trading — TradingAgents (NeurIPS 2025)
- Tauric Research의 framework. 분석가/리서처/리스크 매니저 역할별 LLM agent + agentic debate. 보고된 sharpe ratio improvement는 인상적이지만 **백테스트 윈도우가 매우 짧고 cherry-pick 가능성**이 매우 큼. (https://github.com/TauricResearch/TradingAgents, https://arxiv.org/abs/2412.20138)
- FinAgent, FinMem, P1GPT 모두 비슷한 패턴. **2026 시점 실무 컨센서스: agent debate로 latency cost가 산처럼 늘고 alpha contribution은 미미. paper trading 이상으로 쓴 사람을 본 적이 없다**.

### Risk-Aware Loss — Sharpe-loss / CVaR-loss
- Sharpe-loss는 SGD에서 biased gradient 문제 (음의 PnL에서 unstable). 최근 CARA utility loss로 대체 제안. (https://arxiv.org/pdf/2507.16717)
- CVaR-RP model sharpe 48.78% vs EW 12.93% — 단 universe가 작은 etf 셋이라 일반화 불확실. (https://www.sciencedirect.com/science/article/abs/pii/S0927538X25001945)
- **Bloasis 직접 시사점: LightGBM에서 MSE → ranking-aware loss (LambdaRank pairwise) 또는 직접 sharpe-loss로 전환하는 게 redesign 1순위 후보**.

### Numerai 2024 — JPMorgan $500M
- 2024년 Numerai 글로벌 주식 헤지펀드 **net return 25.45%, sharpe 2.75, single down month** — 그들 역사상 최고. JPM이 2025-08에 $500M capacity 투입. (https://blog.numer.ai/jpmorgan-secures-500m-capacity/)
- 우승 모델 패턴: tree ensembles + transformer + LLM-engineered features의 메타 앙상블. **single 모델이 이긴 적은 거의 없다**. 사용자 contribution은 "Numerai가 아직 갖지 않은 직교 신호" 위주.
- Bloasis 시사점: 단일 LightGBM scorer 1개로 sharpe 1.0을 노리는 것은 Numerai 스택에 비추면 unrealistic. 최소한 (a) tree + linear ridge + 단순 momentum baseline의 weighted ensemble 또는 (b) Numerai 스타일의 era-balanced training이 필요.

### 텍스트 임베딩 팩터
- 10-K tone (Loughran-McDonald + GPT-4o-mini)이 cross-section 수익을 5% 유의수준에서 예측. (https://www.sciencedirect.com/science/article/abs/pii/S1544612325007317)
- "War Discourse and the Cross Section of Expected Stock Returns" (J. Finance 2025) — 미디어 기반 war 팩터가 138개 anomaly를 설명. (https://onlinelibrary.wiley.com/doi/10.1111/jofi.13482)
- 시사점: 풀 임베딩 (e.g. Qwen3-embed) 추출 후 sparse PCA로 cross-section factor 만드는 path가 2026 학계 mainstream.

## 3. Practitioner 블로그 / X 콘텐츠

### AQR — Cliff Asness "AI believer 전향" (2025-04)
- (https://www.bloomberg.com/news/articles/2025-04-23/aqr-bets-on-machine-learning-as-cliff-asness-becomes-ai-believer)
- AQR 플래그십 멀티스트래티지의 **약 1/5 trading signals가 ML 기반**. earnings call transcripts parsing, signal weight assignment에 ML 사용.
- 인용: "even split between economic intuition... and hard data saying that this really works." **즉, 끝까지 economic prior를 버리지 않는다 — 순수 black-box 거부**.

### @macrocephalopod (cephalopod, ex-Citadel quant director)
- "24 days of backtest errors" 어드벤트 시리즈 (https://x.com/macrocephalopod/status/1598823745681903616) — backtest를 망치는 24가지 방법. **Bloasis가 phase 1/2에서 몇 개 밟았는지 회고용으로 강추**.
- 핵심 quote: "do less backtesting" — 매번 새 아이디어를 시험할 때마다 universe-wide multi-period 백테스트를 돌리는 패턴이 본질적인 multiple-testing 문제를 만든다.

### Robot James (@therobotjames)
- 인용 (https://x.com/therobotjames/status/1782212452710797548): "many are dunking on this. it's a good example of how NOT to look for trading edge: assume market is full of inefficiency / try random trading rules / find something that looked good in past / assume it'll carry / 'trading is easy'"
- 거의 매주 X에서 LSTM/Transformer 헤드라인-알파 hype에 회의 thread를 올림. **2024-2026 실무 컨센서스의 voice**.

### Two Sigma Insights (https://www.twosigma.com/insights/)
- 2025-02 LLM frameworks landscape; ICML 2025 papers commentary. 직접 trading signal은 공개 안 하지만 ML infra/ops 글이 양질.
- Bloasis가 직접 차용할만한 패턴: feature drift 모니터링, walk-forward에서 train-test boundary 자동 탐지.

### Goldman Sachs / Robeco
- 두 곳 모두 2024-2026 publication에서 "ML factor extension는 알파보다 risk control 측면에서 먼저 가치를 낸다"는 결론. 즉, **ML로 alpha를 짜내려는 것보다 covariance/turnover 추정을 강화하는 데 쓰는 게 ROI 높음**.

## 4. Open-Source Frameworks 업데이트

| 프레임워크 | 2024-2026 상태 | Bloasis 적합도 |
|---|---|---|
| **qlib (Microsoft)** + RD-Agent (2024-08) | LLM-driven 자동 alpha 마이닝, Alpha-158/360 baseline 표준화. 한국에서 의외로 production case 많음. (https://github.com/microsoft/qlib) | **높음** — Phase 1 feature pool과 직접 호환 |
| **NautilusTrader** | Rust core + Python PyO3, nanosecond 백테스트, multi-venue. (https://nautilustrader.io/) | 중 — HFT 색채 강함, daily rebalance에는 overkill |
| **LEAN (QuantConnect)** | 라이브-백테스트 parity, 300+ 헤지펀드 쓰는 사실상 표준 | **높음** — Phase 3 paper-trading 후보 |
| **vectorbt PRO** | Sam Tinnerholm "Going Live in 2025" 가이드, AI workflow native 지원 | 중 — Phase 1 코드 재활용 어려움 |
| **FinRL / FinRL-Meta** | 2025 contest 활성, DeepSeek 통합. RL은 여전히 academic 색채 | 낮음 — cross-section 적용 어려움 |
| **TensorTrade** | dormant (2023 이후) | **사용 X** |
| **pyfolio/alphalens/empyrical** | quantopian 본진 dormant. **stefan-jansen "reloaded" 포크가 사실상 표준** (3.13/numpy 2.0 호환) (https://x.com/ml4trading/status/1948303607729631620) | 높음 — Bloasis 분석 레이어에 즉시 사용 가능 |
| **QuantStats** | pyfolio 대체로 가장 인기 | 높음 |
| **StrateQueue** (2025 신규) | vectorbt/backtesting.py/backtrader/zipline 전략을 Alpaca/IBKR으로 1-command 배포 | 중 — Phase 3 검토 |
| **TradingAgents / FinMem / P1GPT** | LLM 다중 에이전트 — 거의 academic toy | 낮음 |

한국어 framework는 quantylab이 거의 유일하고 production-ready 수준은 아니다.

## 5. Direct LLM-as-Trader 실험

### 직접 prompting 결과
- Lopez-Lira 후속: post-cutoff 헤드라인에서도 GPT-4 portfolio-day hit rate ~90% — **단 sharpe가 1년에 절반씩 감소**. (cf. §2)
- "FinGPT + RL" (2025-10, https://arxiv.org/html/2510.10526v1): 2024-07~2025-06 OOS에서 annualized return 53.87%, sharpe 1.702 vs buy-and-hold sharpe 0.765. **단 cherry-picked single basket 가능성, S&P 500 cross-section reproducibility 미검증**.

### Citizen quant
- ChatGPT/Claude로 직접 종목 픽 — Reddit r/algotrading, r/quant 2024-2026 토론은 거의 일관: **단기 paper trading에서 momentum과 별 차이 없음, 거래비용 반영 시 underperform**. 진지한 retail의 컨센서스는 "LLM은 risk narrative, 전체 시황 sense-making 보조에 쓰고, position sizing은 systematic에 맡긴다."

### 실무 활용 패턴 (현재 작동하는 것)
1. **Earnings call sentiment** — FactSet, MarketPsych 같은 vendor가 LLM scoring 상품화. "disapproval 상위 5%" 종목이 다음 달 underperform이 유의 (MarketPsych 2024).
2. **10-K/10-Q risk factor 임베딩** — embedding cosine similarity로 cluster, "uncertainty intensity" → 1m forward return 신호.
3. **News headline tape interpretation** — single-name 이벤트 driven, 그러나 §2의 alpha decay 빠름.

## 6. Hype vs Robust — 솔직한 평가

### 2023 떠들썩 → 2026 hype 판명
- **순수 LSTM/Transformer가 OHLCV에서 알파 추출** — Aronson, Robot James, Marcos Lopez de Prado 모두 회의. Nature 2025 "myth" 논문도 동의.
- **LLM 멀티에이전트 토론으로 portfolio construction** — TradingAgents 류. 인상적 데모, 0 production case.
- **End-to-end RL로 portfolio weights 직접 최적화** — FinRL 5년차에도 cross-section sharpe 1.0 깨끗하게 보여준 reproduction은 거의 없음.

### 조용했지만 robust로 판명
- **Cross-sectional momentum (JT-style 12-1, top decile)** — 2024년 S&P 500에서 **96th percentile 50년래 excess return**. 디자인이 단순한 만큼 reproducible. (이것이 Bloasis baseline의 sharpe 1.21).
- **Quality + momentum 결합** (AQR style) — 2024 backtest excess return 13.66% annualized.
- **Vol-scaled momentum, conditioning on market state** — 단순 modification으로 momentum crash 위험 절반.
- **Earnings revision factor** — 학계 1990년대 신호인데 여전히 살아있음.

### 잠재성 있으나 미검증
- **LLM-engineered cross-section feature** — Numerai-scale ensemble 안에서는 가치 있음, single contribution은 misleading.
- **Foundation TSFM (TimesFM, Kronos)** — generic은 패배, financial-specific은 데이터 우위 충분치 않음.
- **Risk-aware loss 직접 학습** — academic에서 가능성 보이나 retail-scale 데이터에서 단일 backbone로는 fragile.

### 비용 vs marginal alpha — practitioner 컨센서스
- 2026 컨센서스: **알파의 80%는 universe selection + factor design + 거래비용 처리에서 나온다. ML 모델 선택은 마지막 20%이고 그 안에서도 단순 ridge/lightgbm으로 95% 도달.** 트랜스포머/foundation/RL은 추가 5%를 위해 10-100x 인프라 비용. retail에 안 맞다.

## 7. Bloasis 재설계 — Top 5 Path

전제: Phase 1/2 자산 (universe loader, feature pipeline, walk-forward 백테스트, 23 features)은 살아있고, JT 12-1 단독이 sharpe 1.21 (acceptance gate 1.0 통과). 따라서 "ML 더 강하게"가 아니라 **"이미 통과한 baseline 위에서 robust하게 쌓는다"** 가 본질.

### Path A — 모멘텀 baseline + 단일 risk overlay (1-2주, P(통과) 매우 높음)
JT 12-1 (top decile, equal-weight, monthly rebalance)을 그대로 두고 **vol-scaled position sizing + market-state filter (10m SMA above/below)** 만 추가. SSGA 2024 보고서 기준 momentum crash 위험을 절반으로 줄임. ML 0줄 추가. **Sharpe target: 1.3-1.5, MDD 25% → 15%**. 가장 안전한 ship-it path.

### Path B — Quality + Momentum 2-factor blend (2-3주, P(통과) 높음)
JT 12-1과 quality 신호(ROIC, asset turnover, accruals 음수) 합성. AQR 2024 결과처럼 **두 직교 팩터 단순 평균이 single momentum보다 sharpe와 turnover 모두 개선**. Phase 1의 23개 feature 중 quality-flavored 것들 4-5개만 이미 있을 가능성. 합성 방식은 z-score 평균 (분위 평균 X, threshold X — 이게 Phase 2의 병목이었음).

### Path C — Numerai-style era-balanced ensemble (3-5주, P(통과) 중-높음)
LightGBM 단일 모델 → **(LightGBM rank-objective) + (Ridge on standardized features) + (raw JT momentum) 3-way 등가중 앙상블**. Era (월별) balanced batch sampling. 핵심 변경: MSE → LambdaRank pairwise (cross-section ranking이 진짜 task). Phase 2 코드 80% 재사용. **Sharpe target: 1.0-1.4. 이 path는 단일 path 중에서 가장 modern AI를 끌어들이면서도 hype 위험 낮음**.

### Path D — qlib + Alpha-158 baseline 통째로 채택 (4-6주, P(통과) 중)
자체 feature pipeline → qlib로 이주. Alpha-158 (이미 학계 baseline으로 검증) 위에 LightGBM/MLP. **장점: factor design 부담 사라짐, RD-Agent로 LLM-driven 추가 alpha 자동 마이닝 가능**. 단점: Phase 1 코드 상당량 폐기, qlib 버전/PIT-data 함정 학습 곡선. ROI는 큰데 effort도 큼.

### Path E — JT 단독 ship + Phase 3로 LLM 텍스트 alpha 신규 윈도 (1주 ship + 별도 4-8주 R&D)
가장 opinionated 권장. **Phase 1/2의 합성 framework는 폐기하고 JT 12-1 단독을 v1으로 ship한다**. 동시에 Phase 3에서 별도 트랙으로 (a) earnings call transcript embedding, (b) 10-K risk-factor uncertainty, (c) headline event drift — 셋 중 가장 직교한 것 1개만 골라 add-on factor로 합류. JT 자체는 commodity가 되었지만 거기에 직교한 텍스트 알파 1개 더하면 sharpe 1.3+ 달성 사례가 풍부. **현재 Bloasis가 직면한 가장 큰 함정은 "Phase 2의 ML 자산을 살리려는 정서적 sunk cost"** — 5개월 LightGBM 작업이 sharpe -0.04인데 1주 baseline이 1.21이면 모델이 아닌 framework를 버리는 게 정답이다.

### 권장 우선순위
1. **즉시 (이번 주)**: Path A로 v1 ship. 회의 정서적 배경 청산.
2. **다음 sprint (2-3주)**: Path B 또는 Path C 선택. C가 학습 가치 ↑, B가 안전.
3. **Phase 3 (별 트랙, 1-2개월)**: Path E의 텍스트 alpha 1개 prototype. Path D는 trigger 없으면 보류 — qlib 이주는 redesign 결정 후가 아니라 기존 framework가 alpha 기준에 부족할 때 결정.

핵심 원칙: **edge → robustness → ML complexity** 순서. Phase 1/2는 거꾸로 갔다. 이번엔 edge가 baseline에서 이미 입증되었으니 robustness만 단단히 쌓고, ML은 Path C/E의 보조 layer 정도로 제한할 것.

## Sources

- Robot Wealth ML — https://robotwealth.com/category/machine-learning/
- QuantConnect LEAN — https://github.com/QuantConnect/Lean, https://www.lean.io/
- Lopez-Lira & Tang ChatGPT prediction v6 — https://arxiv.org/abs/2304.07619
- TFT-GNN stock — https://www.mdpi.com/2673-9909/5/4/176
- FinRL Contests 2025 — https://arxiv.org/html/2504.02281v3
- Numerai JPMorgan $500M — https://blog.numer.ai/jpmorgan-secures-500m-capacity/
- FinGPT + RL OOS — https://arxiv.org/html/2510.10526v1
- TradingAgents — https://arxiv.org/abs/2412.20138, https://github.com/TauricResearch/TradingAgents
- AQR / Cliff Asness 전향 — https://www.bloomberg.com/news/articles/2025-04-23/aqr-bets-on-machine-learning-as-cliff-asness-becomes-ai-believer
- @macrocephalopod backtest errors — https://x.com/macrocephalopod/status/1598823745681903616
- @therobotjames edge thread — https://x.com/therobotjames/status/1782212452710797548
- TimesFM — https://github.com/google-research/timesfm
- Chronos / Kronos — https://github.com/amazon-science/chronos-forecasting, https://jonathankinlay.com/2026/02/time-series-foundation-models-for-financial-markets-kronos-and-the-rise-of-pre-trained-market-models/
- Re(Visiting) TSFM in Finance — https://arxiv.org/html/2511.18578v1
- qlib + RD-Agent — https://github.com/microsoft/qlib
- NautilusTrader — https://nautilustrader.io/
- pyfolio-reloaded by stefan-jansen — https://x.com/ml4trading/status/1948303607729631620
- 10-K tone Loughran-McDonald + GPT-4o-mini — https://www.sciencedirect.com/science/article/abs/pii/S1544612325007317
- War Discourse cross-section — https://onlinelibrary.wiley.com/doi/10.1111/jofi.13482
- CARA loss vs Sharpe loss — https://arxiv.org/pdf/2507.16717
- SSGA Momentum 2024 review — https://www.ssga.com/us/en/intermediary/insights/what-drove-momentums-strong-2024-and-what-it-could-mean-for-2025
- Lazy-Man's Momentum (Estrada 2025) — https://blog.iese.edu/jestrada/files/2025/10/LMMS.pdf
- 퀀티랩 (한국 quant 오픈소스) — https://github.com/quantylab
