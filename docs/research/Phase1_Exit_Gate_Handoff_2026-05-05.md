# Bloasis — Phase 1 Exit Gate 인수인계서

**작성**: 2026-05-05 / **PR9 머지 직후**

## TL;DR

Phase 1 (M2) 골격은 완성. PR1~PR9 머지. 387 tests / 88% coverage / mypy strict.
**그러나 acceptance gate를 통과하는 strategy는 아직 없음** — 5심볼 baseline에서 median α –18%, sharpe 0.50 (vs SPY 1.0 필요). 그리고 **Phase 1 Exit Gate (S&P 500 5+ years) 자체를 실행 불가** — universe loader가 upstream 데이터셋 URL 404로 깨졌음.

다음 작업은 한 세션짜리가 아닌 **strategy research** 영역. 머지된 코드는 라이브로 거래 안 함 (multi-gate가 막음 — 별도 §6 참조).

## 1. 현재 상태 (2026-05-05 기준)

- main HEAD: `73b34a3 PR9: real OHLCV fixture capture + replay smoke (#27)`
- 5심볼(AAPL/MSFT/GOOGL/NVDA/JPM) × 2020-01-01..2024-12-31 walk-forward backtest 결과:
  ```
  median_alpha_annualized    -0.1850
  median_sharpe_vs_spy       0.500
  median_max_dd_ratio_to_spy 0.101
  median_total_return        +0.0047
  median_spy_total_return    +0.0636
  n_folds                    12
  n_trades_total             70
  passed_acceptance          NO
  ```
- 실측: rule-based scorer는 SPY를 명백히 underperform. 70 trades 동안 +0.47% 총 수익. SPY는 같은 기간 +6.36%.
- Phase 1 Exit Gate 임계값 (configs/baseline.yaml):
  - `walk_forward_min_folds: 5` ✅
  - `median_alpha_annualized: -0.005` ❌ (-0.185 < -0.005)
  - `median_sharpe_vs_spy: 1.0` ❌ (0.500)
  - `median_max_dd_ratio_to_spy: 0.85` ✅ (0.101)

## 2. Phase 1 Exit Gate 차단 이슈 (즉시 fix 필요)

### 2.1 S&P 500 universe loader 404 — **PR10 후보**

`bloasis universe show sp500 --count` → HTTP 404.

원인: [bloasis/data/universe/sp500_historical.py:33-36](https://github.com/blas1n/bloasis/blob/main/bloasis/data/universe/sp500_historical.py#L33-L36) 의 `DEFAULT_DATASET_URL` 이 upstream `fja05680/sp500` 레포의 파일명에 박힌 날짜(`02-21-2025`)를 기준으로 하드코딩됨. upstream이 더 최신 스냅샷으로 파일명을 갱신하면 404.

```python
DEFAULT_DATASET_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes(02-21-2025).csv"
)
```

코드는 이 fragility를 인지하고 있고 `SP500_HISTORICAL_URL` env override 지원. 현재 upstream의 최신 파일명을 찾아서:
1. 임시 우회: `export SP500_HISTORICAL_URL='https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes(<현재 날짜>).csv'`
2. 영구 fix: `DEFAULT_DATASET_URL` 갱신 + 더 강건하게 GitHub API로 master 브랜치의 `*.csv` 파일을 list해서 가장 최신 가져오는 방식으로 변경

**Phase 1 Exit Gate는 이 fix 없이는 진행 불가.** S&P 500 5+ years 검증이 mission.md 요구사항.

### 2.2 sentiment 비활성 (의심)

baseline.yaml의 scorer weight 중 `sentiment: 0.15`. 그러나 백테스트 trades의 rationale에 모두 `sentiment_score: NaN, news_count: NaN` — Finnhub key 미설정 또는 sentiment cache 0건. 15% 가중치를 NaN으로 0 contribution하면 effective scoring weight 분포가 baseline.yaml 의도와 다름.

Action: `bloasis sentiment AAPL` 직접 호출해서 LLM API 키 + Finnhub 둘 다 살아있는지 확인. `news_sentiment_cache` 테이블에 row가 들어가는지 검증.

## 3. 다음 작업 path 옵션 (size 추정)

### Path A — Universe + sentiment fix → 다시 측정 (1~2 PR, 1세션)

가장 작고 빠른 path. 현재 acceptance 실패가 단순히 5심볼 sample bias + sentiment NaN 때문일 수 있음. 1차로 검증.

1. PR10: universe loader URL 갱신 + 강건화 (§2.1)
2. PR11: sentiment 파이프라인 검증 + 필요 시 cache 테이블 fix (§2.2)
3. 그 후 S&P 500 전체 (~500 심볼) × 5+ years walk-forward 백테스트 재실행

예상 소요: yfinance 500 종목 × 5y 풀링은 ~30분 + 캐시 후 backtest 실행 5~10분. 첫 실행이 가장 비싸고 fundamentals/sentiment 캐시 채우면 그 다음부터는 빠름.

만약 그래도 acceptance 실패면 → Path B 또는 C.

### Path B — Baseline tuning (research, 멀티 PR)

scorer weights, regime multipliers, entry/exit thresholds 를 데이터 기반으로 튜닝.

위험: full-history optimization은 CLAUDE.md §4가 금지. walk-forward 안에서 IS 튜닝 → OOS 평가 구조 필요. 이건 단순 튜닝이 아니라 별도 ML pipeline 추가에 가까움.

### Path C — Phase 2 ML scorer 활성화 (멀티 세션)

가장 본격적. roadmap.md Phase 2의 작업.

서브태스크:
1. **labeling job**: `feature_log` 테이블에 forward returns 라벨 채우기 (`label_5d`, `label_20d` 등). 새 CLI 명령 + storage migration.
2. **training pipeline**: LightGBM, time-series CV, hyperparam search. `bloasis ml train --from-feature-log --feature-version V` 명령 추가.
3. **inference**: `MLScorerStub` ([bloasis/scoring/scorer.py](https://github.com/blas1n/bloasis/blob/main/bloasis/scoring/scorer.py))를 진짜 LightGBM predict 으로 교체. 모델 직렬화 + 로딩.
4. **SHAP rationale**: rule-based의 contribution 등가물.
5. **acceptance gate** 재실행, ML vs rule 비교.

추정: 4~6 PR, 1~2주.

### Path D — 전략 자체를 단순화

mission.md 의 "Reset, simplify, or halt" 옵션. 현재 22 features + 7 composites + 5 regimes는 너무 넓음. 단일 신호 (e.g., 12-month momentum + mean reversion) 으로 reset 후 SPY beat이 가능한지 먼저 확인.

이건 *연구* 결정이지 코드 결정 아님 — 사용자가 직접 strategy 방향을 잡아야 함.

## 4. 추천 — 즉시 다음 액션

> **Path A부터 — universe loader fix + 풀 S&P 500 백테스트.**
>
> 이유: 5심볼 결과만 보고 strategy를 폐기/Phase 2로 가는 건 표본이 너무 작음. mission.md 요구사항인 "5+ years of S&P 500" 결과를 먼저 봐야 진짜 acceptance 갭이 얼마인지 알고 다음 결정 가능. universe fix는 ~1시간 작업.

PR10 한 줄 스코프:
- `bloasis/data/universe/sp500_historical.py:DEFAULT_DATASET_URL` 갱신
- 가능하면 GitHub API로 가장 최신 `*.csv` 자동 발견 로직 추가
- 회귀 테스트: 404 에러 메시지가 "set SP500_HISTORICAL_URL or update DEFAULT_DATASET_URL" 식으로 actionable 하도록

## 5. PR9 처리 못한 작은 follow-ups

핸드오프 시점에 의도적으로 PR9에서 제외한 항목들:

- **`--set` inline override**: `backtest`/`trade` 명령에도 (현재 `config show`만 지원). 픽스처 테스트 임시 YAML 안 써도 됨.
- **`equity_curve.cash` / `invested` 항상 0**: `SimulatedPortfolio`가 cash/invested 분할을 timestep별로 안 노출. 현재 `total_equity`만 의미 있음.
- **`AlpacaBrokerAdapter.cancel_order` 예외 swallow**: `# noqa: BLE001`로 silence. 운영 시 logging 필요.
- **pre-commit infra fix**: `.pre-commit-config.yaml`에 `default_language_version: python: python3.11` 추가. macOS의 homebrew python3.14 + libexpat ABI bug로 hook 환경 생성 실패 (skill: `precommit-python314-libexpat`). pre-commit 자체를 pipx + python3.11로 재설치하면 우회 가능 (현재 사용자는 그렇게 우회 중).
- **L009 close — MTM halt**: realized PnL만 보지만 unrealized도 봐야 함. `equity_snapshot` 테이블 + broker.get_account() 주기 기록 + `evaluate_halt`에 unrealized 합산.
- **`test_ohlcv_caret_symbol_keyed_safely` flake**: 단일 파일 실행 시 pyarrow `pandas.period` double-registration 으로 fail. 풀 suite에서는 import 순서가 달라서 패스. mock 방식 변경 (sys.modules patch → 모듈 함수 직접 patch) 으로 안정화 가능. PR9에서 새 capture command 테스트는 이미 안전한 방식으로 작성됨.

## 6. 안전 막 (라이브 거래 절대 안 됨)

질문 받았던 부분 — 현재 코드 그대로 돌려도 거래 발생 안 함. 6단계 gate ([cli.py:1000-1083](https://github.com/blas1n/bloasis/blob/main/bloasis/cli.py)):

1. `ALPACA_LIVE_API_KEY` env 미설정 시 거부
2. `--from-run <id>` 필수
3. run.status == "completed"
4. **`run.passed_acceptance is True`** ← 현재 모든 run이 False라 차단
5. halt-condition (realized PnL drawdown floor)
6. `--i-am-sure` 또는 대화형 `"I AM SURE"` 입력

자동 트리거 없음. daemon/cron/launchd 없음. CLI 명령을 사람이 직접 쳐야 거래 시도 발생.

## 7. 빠른 참조

```bash
# 1. Worktree 생성
~/Works/_infra/scripts/create-worktree.sh bloasis pr10/sp500-loader-fix
cd ~/Works/bloasis/wt/pr10-sp500-loader-fix
uv sync --extra dev --extra data --extra ta --extra llm --extra broker

# 2. CI chain (commit 전)
uv run ruff check bloasis/ tests/ && \
uv run ruff format --check bloasis/ tests/ && \
uv run mypy bloasis/ && \
uv run pytest tests/ --cov=bloasis --cov-fail-under=80

# 3. 풀 S&P 500 백테스트 (universe loader fix 후)
uv run bloasis universe show sp500 --count                          # ~500 기대
uv run bloasis universe show sp500 > /tmp/sp500.txt
SYMBOLS=$(tail -1 /tmp/sp500.txt | tr -d ' ')
uv run bloasis backtest --config configs/baseline.yaml \
    --start 2019-01-01 --end 2024-12-31 \
    $(echo $SYMBOLS | tr ',' '\n' | sed 's/^/-s /' | xargs) \
    --train-days 365 --test-days 120 --step-days 120 \
    --name phase1-exit-gate-sp500-v1

# 4. 결과 확인
uv run bloasis runs show <run_id>

# 5. Worktree 정리 (PR 머지 후)
~/Works/_infra/scripts/remove-worktree.sh bloasis pr10-sp500-loader-fix
```

## 8. 핵심 파일 빠른 인덱스

- `bloasis/cli.py` — 모든 CLI 진입점
- `bloasis/data/universe/sp500_historical.py` — **PR10 fix 대상**
- `bloasis/data/fetchers/yfinance_ohlcv.py` — PR9에서 tz normalize 추가됨
- `bloasis/scoring/scorer.py` — `MLScorerStub` 가 Path C에서 진짜 LightGBM 으로 교체될 곳
- `bloasis/scoring/extractor.py` — 22 features, look-ahead 어서션
- `bloasis/backtest/engine.py` — walk-forward 엔진
- `bloasis/runtime/halt.py` — halt-condition gate (L009 확장 대상)
- `configs/baseline.yaml` — 가중치/임계값/acceptance 기준
- `docs/mission.md`, `docs/roadmap.md`, `docs/limitations.md` — strategy 결정의 ground truth
- `tests/fixtures/ohlcv/` — PR9에서 추가된 7심볼 6년 parquet
- `tests/test_real_data_smoke.py` — 실데이터 replay smoke

## 핵심 메시지

Phase 1 골격 완료, 그러나 골격이 작동한다는 것 ≠ strategy가 작동한다는 것. 다음 conversation은 **engineering이 아니라 research 결정**이 필요. 추천 순서:

1. **PR10**: universe loader fix (1세션, 명확한 작업)
2. **풀 S&P 500 백테스트** (코드 변경 없음, 데이터만)
3. **결과 보고 strategy 방향 결정** — Path B(tuning) vs C(ML) vs D(simplify)

L009 close, --set, equity_curve cash 등 작은 follow-up은 위 큰 결정과 독립적으로 언제든 진행 가능.
