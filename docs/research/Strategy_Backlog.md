# Bloasis Strategy Backlog (2026-05-09)

PR21-23 측정 (41 combos / 1 미세 lift) 후 daily-horizon 영역의 직관적
local optimum 확인. 추가 알파 후보를 horizon 별로 정리.

## Daily / weekly horizon (현 알고리즘 클래스)

이 영역은 우리 backtest infra (walk-forward, EDGAR/JT factors) 와 호환.
PR45-47 paper trading layer 가 검증 채널.

### 알파 stacking
- **Vol-targeted JT residual** — PR23-B 가설을 EDGAR 가 아닌 JT residual base 에 적용
- **News sentiment integration** — 라이브 환경에서만 가능 (backtest look-ahead 위험). paper A/B 로 측정
- **Alt-data factors** — Glassdoor sentiment, satellite, credit card panel — 데이터 비용 vs 측정 가치 검토 필요
- **Larger LLM fundamental** — qwen3:14b / ministral-3:14b / frontier model on smaller universe

### Risk / execution
- **Bracket orders (Alpaca)** — BUY + stop + TP atomic submission, broker-side enforcement
- **TWAP/VWAP execution** — market order 대신 시간 분할 entry → 1-3 bps slippage 절감
- **Risk parity weighting** — score 기반이 아닌 vol-inverse weighting

### Universe expansion
- **International (developed)** — Japan, EU large caps. 같은 EDGAR-style filing 없음 → JT 만 작동 가능
- **Mid-cap extension** — Russell 2000 ex-SP500. PEAD 가 다시 살아날 가능성 (Bernard-Thomas 원 universe)

## Sub-daily horizon (별도 strategy class)

**중요:** 이건 현 알고리즘의 자연 확장이 아님. 완전히 다른 알파 source +
infra + risk model. 별도 prefix (e.g., `bloasis intraday ...`) 로 분리 권장.

### Pre-decision considerations
- **Alpha source 가 다름** — JT/EDGAR 의 horizon 은 monthly-yearly. 분/시간 봉으로
  옮기면 같은 신호가 노이즈로 변함. 새 신호 class 필요.
- **Friction 폭발** — round-trip 빈도 30-50× 증가, Alpaca commission/spread 가
  backtest α 의 multiple 을 먹음
- **Latency arms race** — 50-200ms (Alpaca + retail) vs HFT μs. 마찬가지로
  marginal alpha 가 더 빠른 player 에게 빼앗김 (Kearns et al. 2010)
- **Data infra 비용 +1 자릿수** — Polygon.io ($200-500/월) 또는 IEX Cloud
  ($100-300/월), 저장소 1000×, 새 backtester engine

### 가능한 진입 시나리오
다음 셋이 동시에 만족될 때 검토:
1. **Daily horizon 에서 paper-validated α** (현 +4.1% 가 friction 후 +2-3% 살아남는 게 확정)
2. **자본 규모 > $500k** — fixed cost amortization 가능
3. **Latency-tolerant intraday alpha 후보 발굴** — 예: opening auction reversion
   (open vs prior close gap 의 mean reversion), close auction VWAP arbitrage —
   1-30분 horizon 이라 latency arms race 회피 가능

### 후보 alpha sources (사전 리서치 필요)
- **Opening gap reversion** — 8:30 ET open vs prev close gap, 첫 30분 reversion
- **Close auction imbalance** — 15:50 ET imbalance feed, MOC order
- **Earnings reaction (intraday)** — earnings release 후 첫 60분 momentum/reversal
- **Intraday momentum after halt** — circuit breaker 해제 후 30분 drift

### 필요 인프라 (Phase N — 검토 시)
- Polygon.io 또는 Alpaca data sub
- 1-min bar storage (Postgres 또는 timescale)
- 새 backtester (intraday bars + 분 단위 fill model)
- Bracket / OCO order 지원 broker layer (현 Alpaca adapter 에 추가 가능)
- 별도 risk model (intraday VaR, halt scenario)

## Multi-asset horizon (별도 + 별도)

- **Crypto** — 24/7 운영. JT 12-1 + EDGAR 같은 텍스트 신호 부재 → 마찬가지로 새 알고리즘 class
- **Futures** — leverage built-in, term-structure carry 같은 다른 알파
- **Options** — IV surface arb, 완전히 다른 risk class

이쪽은 daily-horizon 알파 1개 ship 후 자본 규모 기준으로 검토.

## 우선순위 결정 framework

후보가 들어오면 다음 4 점수 비교:

1. **Marginal alpha potential** — 같은 자본 추가 시 expected α (bps/year)
2. **Code/data infra delta** — 0 (기존 활용) ~ 10 (새 backtester)
3. **Friction sensitivity** — α 가 trade frequency 와 함께 늘어나는가
4. **Concept overlap** — 기존 신호와 독립 (높을수록 portfolio 분산 효과)

현재 1순위: paper trading 데이터로 daily α validate 후 알파 stacking.
2순위: bracket orders / 더 큰 LLM.
3순위 이하: 별도 horizon (intraday/multi-asset/crypto).
