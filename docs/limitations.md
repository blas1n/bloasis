# BLOASIS Known Limitations

This file is the canonical catalog of system limitations. Each entry has an
ID, an impact estimate, current mitigation, and the planned resolution path.

The CLI surfaces relevant entries automatically in backtest output. Do not
silently fix limitations without updating this catalog.

---

## L001 — Survivorship bias (universe)

**Status**: open
**Severity**: medium (low for ≤2y backtests, severe for ≥10y)
**Affected components**: `bloasis/data/universe/*`, `bloasis/backtest/engine.py`

**Impact**: yfinance returns currently-listed stocks. Using "current S&P 500"
to backtest 2015 omits stocks that were delisted or removed during the
period (these typically underperformed). Inflates annualized return by
roughly +1-3% over 5-year periods.

**Current mitigation**:

- `universe.source: sp500_historical` mode uses
  [fja05680/sp500](https://github.com/fja05680/sp500) historical membership
  dataset (free, semi-maintained).
- Backtest output prints survivorship bias level (low/medium/high) based on
  delisted-ratio observed during the run.

**Planned resolution**: Phase 3 — EODHD ($30/mo) provides delisted equity
OHLCV and proper PIT membership.

---

## L002 — Fundamentals point-in-time inaccuracy

**Status**: open
**Severity**: low to medium
**Affected components**: `bloasis/data/fetchers/fundamentals.py`,
`bloasis/scoring/features.py`

**Impact**: yfinance returns the latest fundamentals snapshot. Backtests
using these as features for past dates leak future information (e.g., using
2024-Q3 P/E on a 2024-Q1 bar). Effect is small for slow-moving fundamentals
but real for earnings-related signals.

**Current mitigation**: assume quarterly lag-1 — i.e., fundamentals from
quarter Q are usable starting Q+1. Approximation, not perfect.

**Planned resolution**: Phase 3 — SEC EDGAR direct integration or EODHD
PIT fundamentals.

---

## L003 — News sentiment unavailable in backtest

**Status**: open
**Severity**: low
**Affected components**: `bloasis/data/fetchers/sentiment.py`

**Impact**: Finnhub free tier provides only ~1 year of historical news. For
backtests longer than 1 year, sentiment feature is NaN for older periods.
LightGBM handles NaN natively, RuleBasedScorer ignores NaN sentiment with no
contribution. Live behavior may differ measurably from backtest.

**Current mitigation**: sentiment column written as NULL in `feature_log`
during backtest; scorer designed to be sentiment-optional.

**Planned resolution**: Phase 3 — paid news API with deeper history (EODHD,
Polygon News).

---

## L004 — Daily bars only

**Status**: open
**Severity**: by design
**Affected components**: all

**Impact**: All signals computed on daily close. Cannot exploit intraday
patterns, gap behavior beyond previous-close anchoring, or microstructure.

**Current mitigation**: explicit non-goal in mission.

**Planned resolution**: not planned for v1. Phase 4 may revisit if a
concrete intraday edge is identified.

---

## L005 — Free-tier rate limits (Finnhub)

**Status**: open
**Severity**: operational
**Affected components**: `bloasis/data/fetchers/sentiment.py`

**Impact**: Finnhub free is 60 calls/min. With 100 symbols × 6h cache, we
fit comfortably. Scaling to Russell 1000 (1000 symbols) requires either
upgrade or longer cache TTL.

**Current mitigation**: token-bucket rate limiter (`aiolimiter`), 6h cache
TTL, batched fetch on cold start.

**Planned resolution**: Phase 3 — Finnhub paid tier or alternative.

---

## L006 — yfinance reliability

**Status**: open
**Severity**: operational
**Affected components**: all data layer

**Impact**: yfinance scrapes Yahoo Finance unofficial endpoints. Subject to
silent breakage when Yahoo changes their site. Has happened multiple times
historically (e.g., 0.2.x release line in 2024).

**Current mitigation**: yfinance pinned to specific version in
`pyproject.toml`. Local OHLCV cached to parquet to survive transient
failures. CI runs include a smoke test against yfinance.

**Planned resolution**: Phase 3 migration to EODHD reduces yfinance to a
fallback role.

---

## L007 — Look-ahead in technical indicator window

**Status**: monitored
**Severity**: low (defended by design but easy to break)
**Affected components**: `bloasis/scoring/features.py`,
`bloasis/data/extractor.py`

**Impact**: TA-Lib indicators computed correctly when given a properly
sliced OHLCV window, but trivially break if a developer passes the full
historical series and filters by date inside the indicator function.

**Current mitigation**: `ExtractionContext.__post_init__` asserts
`ohlcv.index.max() <= timestamp`. CI test suite includes a regression test
that constructs an "evil" extraction context with future data and verifies
the assertion fires.

**Planned resolution**: ongoing vigilance. Adding new fetchers or features
must extend the regression test.

---

## L008 — No live news sentiment historical replay

**Status**: open
**Severity**: low
**Affected components**: `bloasis/backtest/engine.py`

**Impact**: Live mode pulls news in real-time and scores via LLM. Backtest
cannot replay this exactly because (a) historical news is partial (L003),
(b) LLM responses are not deterministic and not stored. So a strategy
relying heavily on sentiment may show backtest/live divergence.

**Current mitigation**: backtest uses NULL sentiment; live sentiment is
treated as one of many features, not a dominant signal.

**Planned resolution**: Phase 2 — log every live LLM sentiment score with
its inputs to a sentiment_history table. Replay from that table for
backtests covering periods after live deployment started.

---

## L009 — Halt condition is realized-only and rolling-window

**Status**: open
**Severity**: low
**Affected components**: `bloasis/runtime/halt.py`

**Impact**: `evaluate_halt` reads `trades.realized_pnl` over
`risk.halt_drawdown_lookback_days` and refuses live submission when the
sum drops below `-halt_drawdown_pct * initial_capital`. It does **not**
include unrealized losses on open positions, and it does **not** consult
the live broker's own equity curve. A strategy with one large open loss
but no realized exits inside the window will not trip the halt; a string
of small losing exits in a quiet stretch can trip it unnecessarily.

**Current mitigation**: Conservative defaults (`halt_drawdown_pct=0.10`,
30-day lookback). The interactive `'I AM SURE'` prompt remains the
last-mile safety. Halt can be disabled with `halt_drawdown_pct=0`.

**Planned resolution**: Wire `AlpacaBrokerAdapter.get_account()` (or a
periodic equity snapshot table) into the halt check so MTM drawdown is
also considered. Likely Phase 2 once live equity history accumulates.

---

## How to add a limitation

1. Pick next free `L00N` ID.
2. Write entry following the template above.
3. Reference the ID in code comments where relevant: `# See L00N`.
4. If the limitation affects backtest results, register it with the
   `LimitationReporter` so the CLI surfaces it automatically.

## How to close a limitation

1. Implement the fix on the appropriate Phase branch.
2. Move the entry to the bottom of this file under a `## Resolved` section
   with the resolution PR link and date.
3. Remove `# See L00N` comments from code.
4. Adjust acceptance criteria if the closure changes expected backtest
   behavior.
