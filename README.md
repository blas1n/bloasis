# BLOASIS

CLI-based trading research and execution. Deterministic factor scoring
on US large caps with VIX-based regime de-risking, an EDGAR text-diff
"Lazy Prices" scorer, walk-forward backtesting, and daily Alpaca paper
execution driven by launchd cron.

> **Read first**: [`docs/mission.md`](./docs/mission.md). The system
> targets SPY parity with lower drawdown (M2). It does **not** promise
> alpha.

## Status

**Phase 1 shipped** — CLI + backtest engine + walk-forward + paper
trading + research analysis all live. `edgar-rolling2` (EDGAR 10-K
text-diff, rolling=2, monthly rebalance) is the current shipped config
with a backtest live-gate pass (sharpe 1.334, α +4.09%/yr, maxDD 0.80).

**Live now** — Alpaca paper session `edgar-rolling2-paper-2026-05`
runs daily via launchd (Mon-Fri 08:00 KST). A mention-tracking pipeline
(Truth Social → sentiment-classified SP500 mentions → forward-tracked
5d excess vs baseline) runs alongside as a research candidate for
Phase 2.

See [`docs/roadmap.md`](./docs/roadmap.md) for phase gates and the
retrospective at PR20 that produced `edgar-rolling2`.

## Quick start

```bash
uv sync --extra dev                              # install
bloasis init-db                                  # SQLite + tables
bloasis config show configs/edgar-rolling2.yaml  # inspect shipped config
```

### Common commands

```bash
# Backtest — walk-forward, honest metrics vs SPY
bloasis backtest -s AAPL -s NVDA -c configs/edgar-rolling2.yaml \
  --start 2019-01-01 --end 2024-12-31

# Grid search — combinatorial spec sweeper
bloasis grid run --spec configs/grids/pr23.yaml

# Paper trading — session persistence, SELL rotation, analysis
bloasis trade paper -c configs/edgar-rolling2.yaml -s AAPL -s NVDA \
  --session my-session
bloasis paper show my-session
bloasis paper entry-gap my-session      # gap drift (NOT execution friction)
bloasis paper reconcile my-session      # backfill fills

# Research — post-hoc analyses on historical data
bloasis research correlations --window 60          # PR53
bloasis research event-study AAPL --spike 0.05     # PR54
bloasis research hub-earnings NVDA AMD MU AVGO     # PR54, Cohen-Frazzini
bloasis research mentions-fetch                     # PR55, Truth Social archive
bloasis research mentions-extract                   # PR58, hybrid LLM + regex NER
bloasis research mentions-study --sentiment negative --horizon 5
bloasis research mentions-track                     # PR57, predict + settle daily
bloasis research mentions-track-report              # PR57, predicted vs realized

# Runs, universe, ML, sentiment
bloasis runs list / show <id>
bloasis universe show sp500 --as-of 2024-12-31
bloasis ml train --start 2019-01-01
bloasis sentiment AAPL
```

## Architecture (current)

```
bloasis/
  cli.py                    # typer entry point — all commands above
  config/                   # pydantic schema + YAML loader + --set overrides
  storage/                  # SQLAlchemy core tables (SQLite)
    schema.py               # 13 tables: feature_log, backtest_runs, trades,
                            #   positions, equity_curve, fundamentals_cache,
                            #   news_sentiment_cache, paper_sessions/orders/
                            #   snapshots, social_posts, social_post_mentions,
                            #   mention_predictions
    writers.py / readers.py / db.py
  data/
    universe/               # sp500, sp500_historical (GitHub auto-discovery),
                            #   custom_csv, loader
    fetchers/               # OhlcvFetcher, FundamentalsFetcher, NewsFetcher,
                            #   EarningsFetcher, Sec10KFetcher, EdgarSubmissions
    cache.py                # parquet cache
    pre_filter.py           # SIC / mkt-cap early rejection
    sentiment.py            # LiteLLM-driven news sentiment (cached)
  scoring/                  # pure — NO I/O
    scorer.py               # unified RuleBasedScorer / hysteresis / regime
    factory.py              # PR48 — build_scorer() dispatch
    features.py             # FeatureVector + raw features
    composites.py           # composite scoring blocks
    derived.py              # momentum / vol / RSI / MA / ATR / MACD
    indicators.py           # ta-lib bindings
    regime.py               # VIX-driven multipliers
    regime_overlay.py       # multi-regime weight overlay
    extractor.py            # pure FeatureExtractor (look-ahead protected)
    edgar_textdiff.py       # Cohen-Malloy-Nguyen "Lazy Prices" scorer
    edgar_llm.py            # LLM-scored 10-K reader (opt-in)
    llm_fundamental.py      # LLM fundamentals scorer (opt-in)
    rationale.py            # per-signal rationale objects (SHAP-compat)
  strategy/
    runner.py               # PR49 — execute_strategy_step (backtest = live)
  signal.py                 # ATR-based SL/TP, profit tiers, hysteresis exits
  risk.py                   # deterministic sizing + limits
  backtest/
    engine.py               # core simulator
    walk_forward.py         # train/test split iterator
    fills.py                # limit_with_fallback fill simulation
    portfolio.py            # SimulatedPortfolio (BrokerAdapter-shaped)
    metrics.py              # Sharpe, DD, alpha, IR
    statistical.py          # bootstrap CI, White reality check
    attribution.py          # per-factor PnL attribution
    acceptance.py           # 2-gate (paper-trading / live-trading) enforcer
    grid.py                 # PR21 — combinatorial grid runner
    prefetch.py             # OHLCV batch pre-warm
    universe_resolver.py    # config → date-scoped ticker set
    result.py               # BacktestResult dataclass
  allocation/
    composer.py             # core (SPY) + satellite (strategy) blending
  broker/
    protocols.py            # BrokerAdapter protocol
    alpaca.py               # AlpacaBrokerAdapter (paper / live)
    paper_simulator.py      # in-memory adapter for backtests
  analysis/                 # research (post-hoc, not in the live path)
    correlations.py         # PR53 — clustering, spearman
    event_study.py          # PR54 — spike-triggered forward returns
    mention_pipeline.py     # PR55-58 — Truth Social → mentions (regex + LLM)
    mention_timing.py       # session-relative bucket classification
    mention_event_study.py  # per-ticker baseline + excess decomposition
  ml/                       # Phase 2 ML pipeline
    training.py             # PR14 — LightGBM training
    labeling.py             # PR13 — forward-return labels
  runtime/                  # live-only runtime
    halt.py                 # halt-condition enforcement
    llm.py                  # LLM client factory
configs/                    # YAML strategy configs (edgar-rolling2 shipped)
scripts/                    # launchd cron wrappers (paper-rotate,
                            #   mentions-track) + README
docs/                       # mission, roadmap, limitations, tune, e2e
tests/                      # pytest, ~770 tests, 84%+ coverage, mypy strict
```

## Design principles

1. **Mission-driven** — every feature must serve the M2 → M1 progression
   defined in `docs/mission.md`.
2. **Honest measurement** — all metrics report relative to SPY benchmark.
   Walk-forward only; no full-history optimization.
3. **Look-ahead protection at the interface level** — `ExtractionContext`
   asserts data slicing.
4. **Pure scoring, I/O at edges** — `bloasis/scoring/` has no I/O.
   `bloasis/strategy/runner.py` runs the *same* step in live and
   backtest (PR49) — dispatch is the only difference.
5. **Acceptance gates** — `configs/*.yaml` declare paper-trading and
   live-trading gates; `bloasis backtest` refuses to promote a config
   without walk-forward clearance.
6. **Retrospectives are load-bearing** — losing paths (PEAD, monolithic
   LLM extractor, bare-surname prefilter, hardcoded upstream URLs) are
   documented in `docs/limitations.md` and `docs/research/` so we
   don't rewalk them.

## License

See [LICENSE](./LICENSE).
