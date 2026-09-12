# Bloasis PR12 — Design Lock-in (2026-05-07)

## Context

Phase 1 measurement (run 1) → acceptance gate FAIL (sharpe 0.30, alpha
-18.3%, DD 0.46). Two pilots + 4 research dives 완료:

- **JT 12-1 momentum** standalone pilot (`/tmp/jt_momentum_pilot.py`):
  alpha +7.6%, sharpe ratio 1.21, DD ratio **1.15** (FAIL DD)
- **Robustness analysis** (`/tmp/jt_momentum_robustness.py`): 87% CPCV
  combos pass sharpe ≥ 1.0, 91% bootstrap reps positive alpha. signal
  real, alpha concentrated in 2020/2022/2024 (regime-shift years)
- **Cost sensitivity** (`/tmp/factor_compare.py`): JT @ 25bps round-trip
  → still sharpe 1.10, alpha +5.7%. realistic 5-15bps fine
- **Multi-factor blend (price-based proxies)**: mom + low_vol → DD
  1.15 → 1.01 ✅ but alpha 7.6% → 0.8%. Low-vol/quality proxies have
  *negative* alpha 2019-2024 (ZIRP era artifact)
- **Research Daniel-Moskowitz**: long-only 에 순수 DM 절반만 적용 →
  Barroso-Santa-Clara constant-vol + bear gate 권장
- **Research AQR**: score-blend integrated 확정. live fund 상한 sharpe
  1.25 (QCELX), 우리 합리적 목표 sharpe 0.7-0.9. **DD 통제 멀티팩터
  만으로 불가** → vol overlay 필수
- **Research qlib**: PR12 즉시 4개 features (KMID2, KSFT2, ROC120,
  CORR_PV_20)

## Design lock-in

PR12 를 **세 단계 PR** 로 분할 (AQR agent 권고).

### PR12a — Foundation: long-term momentum + qlib features + new weights

#### Feature additions (총 5개)

| Feature | Spec | Composite |
|---|---|---|
| `momentum_252_21` | `momentum(close, 252, skip=21)` (PR10 helper 활용) | momentum (replace OR add) |
| `roc_120` | `(close[-1] - close[-121]) / close[-121]` | momentum |
| `kmid2` | `(close - open) / (high - low + 1e-12)` | technical (또는 신규 microstructure) |
| `ksft2` | `(2*close - high - low) / (high - low + 1e-12)` | technical (또는 신규 microstructure) |
| `corr_pv_20` | 20-day Pearson corr of close pct returns vs log volume | liquidity |

`feature_version` 1 → 2 bump. `feature_log` schema column 추가 5개.

#### Composite changes

- `momentum` composite: 현재 `(momentum_20d, +1), (momentum_60d, +1), (rsi_14, +1)` →
  add `(momentum_252_21, +1), (roc_120, +1)` → 5 constituents
- `technical`: add `(kmid2, +1), (ksft2, +1)` (또는 신규 composite — TBD by 코드 review)
- `liquidity`: add `(corr_pv_20, +1)` (음의 상관일 때 정보 거래자 우세 가설 — 부호 검토 필요)

#### Weights — `configs/baseline-v2.yaml` (AQR 권장)

```yaml
scorer:
  weights:
    value:      0.22  # 코어
    quality:    0.22  # 코어
    momentum:   0.22  # 코어 (long-term + short-term blend)
    volatility: 0.14  # 코어 (low-vol overlay)
    technical:  0.08  # 보조
    liquidity:  0.04  # 보조
    sentiment:  0.08  # 보조 (Lopez-Lira 2026 시점 cap 권장 5-10%)
  regime_multipliers: {}  # 일단 비활성, PR12b 의 vol overlay 가 더 정밀
```

기존 baseline.yaml: 코어 51% (mom+val+qual = 0.18+0.18+0.15) → 신 80%
(mom+val+qual+vol = 0.22×3 + 0.14 = 0.80).

#### TDD scope

- `test_derived.py` 또는 `test_indicators.py`: 5 features 단위 테스트
- `test_features.py`: `momentum_252_21` 등 FeatureVector 필드 + `to_array()`
  ordering 호환성
- `test_extractor.py`: real OHLCV fixture 로 추출 round-trip
- `test_composites.py`: 새 constituents 로 composite 정상 작동
- `test_writers.py`: `feature_log` schema column 추가 + version bump
  마이그레이션
- `test_cli_backtest_smoke.py`: baseline-v2 config 로 smoke 통과

#### Measurement

PR12a 단독 walk-forward (PR9 동일 명령, config 만 baseline-v2.yaml):
- 기대 alpha: +2-3% / yr (AQR live fund 35% deflate 적용)
- 기대 sharpe ratio: 0.7-0.9
- DD 변화: minimal (vol overlay 없으니 1.15 그대로)
- **acceptance pass 가능성: 낮음** (DD 임계 fail 그대로)

PR12a 의 의의: 신호 풍부화 + AQR-style 가중치. PR12b 위에 올릴 foundation.

### PR12b — Vol overlay: BSC constant-vol + DM bear gate

#### Implementation

신규 모듈 `bloasis/scoring/regime_overlay.py`:

```python
import math

import numpy as np
import pandas as pd

SIGMA_TARGET = 0.12     # annualized
VOL_LOOKBACK = 126      # trading days (BSC default)
BEAR_LOOKBACK = 504     # ~24 months
BEAR_SCALE = 0.5
SCALE_CLIP = (0.0, 1.5)


def compute_regime_scale(spy_daily_returns: pd.Series) -> float:
    """Barroso-Santa-Clara constant-vol scaling + Daniel-Moskowitz bear gate.

    `spy_daily_returns` is daily log or pct returns of SPY (close-to-close),
    most recent observation last. Returns a scaling factor in [0, 1.5] —
    multiply per-symbol composite scores or position sizes by this.

    Empirical anchor (acceptance test):
        2020-03 → ~0.30 (panic)
        2009-03 → ≤ 0.20 (bear gate active)
        2017-06 → 1.5 (calm bull, ceiling)
    """
    if len(spy_daily_returns) < VOL_LOOKBACK:
        return 1.0  # cold start: no scaling
    realized_vol = float(spy_daily_returns.tail(VOL_LOOKBACK).std()) * math.sqrt(252)
    bsc_scale = float(np.clip(SIGMA_TARGET / max(realized_vol, 0.05), *SCALE_CLIP))
    bear_state = float(spy_daily_returns.tail(BEAR_LOOKBACK).sum()) <= 0
    return bsc_scale * (BEAR_SCALE if bear_state else 1.0)
```

#### Wiring into engine

[bloasis/backtest/engine.py:240-280](~/Works/bloasis/bloasis/backtest/engine.py#L240) 의 BUY 로직에서:

```python
regime_scale = compute_regime_scale(spy_returns_to_date)
size_pct = base_size_pct * regime_scale
```

또는 score 측: composite_score *= regime_scale (entry threshold 자연 통과
어려워짐). 권장: **size 측에 적용** (signal 은 보존, exposure 만 줄임 — DM
원전과 일치).

또한 [risk.py](~/Works/bloasis/bloasis/risk.py) 의 VIX-based gates (vix_high
30, vix_extreme 40) 와 충돌 검토 필요. 단순 합쳐 적용해도 idempotent.

#### TDD

- `test_regime_overlay.py` (신규):
  - `compute_regime_scale` 가 known SPY return series 에 대해 expected
    scale 반환
  - 2020-03 fixture (실제 SPY data) → 0.25 ≤ scale ≤ 0.40
  - 2017-06 fixture → 1.5 ceiling
  - cold start (lookback 미충족) → 1.0
  - bear gate trigger (504d sum ≤ 0) → ×0.5 적용
- `test_backtest_engine.py`: engine 이 regime_scale 을 size_pct 곱셈에 포함
- 기존 backtest smoke tests 깨지지 않아야 — overlay 가 default 1.0 이거나
  config 토글로 비활성

#### Config

```yaml
# baseline-v2.yaml 추가
regime_overlay:
  enabled: true
  sigma_target: 0.12
  vol_lookback_days: 126
  bear_lookback_days: 504
  bear_scale: 0.5
  scale_clip: [0.0, 1.5]
```

#### Measurement

PR12a + PR12b 합산 walk-forward:
- 기대 alpha: +2-3% (PR12a 와 비슷, overlay 가 alpha 약간 잠식)
- 기대 sharpe ratio: **1.0+ 도달** (vol normalize 효과)
- 기대 DD ratio: **0.85 통과** (BSC + bear gate 가 2020 노출 줄임)
- **acceptance pass 가능성: 높음**

이게 mission Phase 1 Exit Gate 첫 진짜 통과 후보.

### PR12c (선택) — 4-pillar QMJ quality

PR12a/b 가 acceptance pass 면 enhancement, fail 이면 critical path.

추가 features:
- GPOA (gross profitability / total assets)
- 5y earnings growth
- β safety (24m rolling β to SPY)
- payout ratio

추가 fundamentals 가져오기 작업 비교적 큼 (yfinance 외 source 검토 — Finnhub
fundamentals 또는 SimFin 등). 별도 PR 분할.

PR12a + PR12b 결과 보고 결정.

## Implementation order — PR12a + PR12b 한 PR 묶기 vs 분할

**권장: 한 PR (PR12) 에 묶기**. 이유:
1. 합쳐야 acceptance gate 통과 가능 (12a 단독은 DD fail)
2. measurement 한번에 끝 — sharpe 갭 자체가 vol overlay 영향 받음
3. 단순 split overhead (review 두번, branch 두개) > integration 가치

**TDD 순서**:

1. PR12a foundation:
   - 5 features 단위 테스트 (RED)
   - `derived.py` / `indicators.py` 에 함수 구현 (GREEN)
   - `FeatureVector` + `FEATURE_COLUMNS` + `feature_version` 2 (RED)
   - `extractor.py` 에 추출 wiring (GREEN)
   - `feature_log` schema migration (RED — `test_writers.py` 에 새 컬럼
     assert)
   - `composites.py` `COMPOSITE_SPEC` 업데이트 (GREEN — `test_composites.py`
     기존 테스트 일부 수정 필요 — 새 constituents)
   - `configs/baseline-v2.yaml` 작성 (smoke)
2. PR12b overlay:
   - `test_regime_overlay.py` known fixtures (RED)
   - `regime_overlay.py` 구현 (GREEN)
   - `engine.py` size_pct 와이어링 (RED — engine integration test)
   - config schema `RegimeOverlayConfig` 추가
3. 풀 walk-forward 측정 + 결과 핸드오프 노트

**예상 작업 시간**: 4-6 시간 (TDD 포함, 측정 시간 별도 ~30분).

## Risk register

| Risk | Mitigation |
|---|---|
| qlib feature signs 잘못 → composite 신호 반대 | 단위 테스트로 known input 에 대해 z-score 부호 검증. cross-section sanity check (S&P top 10 으로 spot check) |
| `momentum_252_21` 와 기존 `momentum_20d/60d` 가 같은 composite 에서 dilute | "long_momentum" 별도 composite 분리 옵션 검토 — 일단 함께 두고 측정, 나쁘면 split |
| `regime_overlay` 가 alpha 너무 잠식 (over-conservative) | scale_clip lower 0.0 → 0.3 floor 검토 옵션 — 측정 후 fine-tune |
| AQR weights 가 우리 데이터 (2019-2024 ZIRP-bull) 에 over-fit | walk-forward + CPCV 가 detect — 결과 보고 가중치 조정 |
| feature_version bump 가 기존 DB 깨뜨림 | `bloasis init-db` 가 idempotent — `MetaData.create_all` 신규 컬럼 add. 데이터 재생성 안 필요 (live 운영 데이터 없음) |
| live deflate (35% from QSPRX 사례) | 우리 mission 은 paper trading 우선이므로 mitigation 보다 awareness — acceptance 통과시 paper 단계 길게 운영 |

## Acceptance criteria (PR12 머지 게이트)

코드:
- [ ] 401 → 420+ tests pass
- [ ] coverage ≥ 80% 유지
- [ ] mypy strict clean
- [ ] ruff clean
- [ ] `bloasis backtest --config configs/baseline-v2.yaml ...` smoke

측정 (PR12 머지 후 풀 walk-forward 산출):
- [ ] median_alpha_annualized ≥ -0.005 (현재 -0.183, 기대 +0.020)
- [ ] median_sharpe_vs_spy ≥ 1.0 (현재 0.30, 기대 1.0+)
- [ ] median_max_dd_ratio_to_spy ≤ 0.85 (현재 0.46 — strategy slice
      기준이라 통과지만 100% 투자 시 1.15 — overlay 가 ≤ 0.85 만들어야
      live trading 의미 있음)

기대 결과 시나리오:
- **best**: 모든 acceptance pass → mission M3 (live paper trading)
  진입
- **likely**: sharpe ~0.9, alpha 2-3%, DD ratio 0.85 borderline → tuning
  PR (entry/exit threshold, regime overlay clip range) 1-2회
- **worst**: sharpe < 0.8 → PR12c (QMJ quality) 또는 ML scorer (Phase 2)
  필요

## 참조 docs

- `docs/research/Phase1_Measurement_2026-05-05.md` — 첫 측정 결과
- `docs/research/Quant_Robustness_2026-05-07.md` — bootstrap/CPCV/LOO
- `docs/research/Quant_References.md` — initial 5 토픽
- `docs/research/Research_DM_Dynamic_Momentum.md` — overlay 구현 spec
- `docs/research/Research_AQR_Factor_Blend.md` — weights 구조
- `docs/research/Research_Qlib_Features.md` — feature cherry-pick
- `/tmp/jt_momentum_pilot.py`, `/tmp/jt_momentum_robustness.py`,
  `/tmp/factor_compare.py` — 검증 스크립트

## 다음 단계

1. **이 doc 사용자 confirm** (가중치 / overlay parameter 변경 가능)
2. PR10 (#28) 머지 wait — 새 worktree base 확보
3. PR12 worktree 생성 (`pr12/momentum-blend-overlay`)
4. TDD 순서대로 구현 (위 §Implementation order)
5. 풀 walk-forward 측정 + 결과 doc → `docs/research/PR12_Measurement_<date>.md`
