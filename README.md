# BLOASIS

CLI-based trading research and execution. Deterministic factor scoring on
US large caps with VIX-based regime de-risking, optional ML and LLM
sentiment as ranked features, and walk-forward backtesting.

> **Read first**: [`docs/mission.md`](./docs/mission.md). The system targets
> SPY parity with lower drawdown (M2). It does **not** promise alpha.

## Status

Phase 1 (M2 foundation), pre-alpha. See [`docs/roadmap.md`](./docs/roadmap.md).

## Quick start

```bash
# install
uv sync --extra dev

# initialize SQLite database
bloasis init-db

# inspect a config (with optional inline overrides)
bloasis config show configs/baseline.yaml
bloasis config show configs/baseline.yaml --set scorer.weights.momentum=0.25
```

Backtest, analyze, and trade commands land in PR2-PR6.

## Architecture (target)

```
bloasis/
  cli.py               # typer entry point
  config/              # pydantic schema + YAML loader + --set overrides
  storage/             # SQLAlchemy core tables (SQLite)
  data/
    universe/          # sp500, sp500_historical, custom_csv
    fetchers/          # OhlcvFetcher, FundamentalsFetcher, NewsFetcher (Protocols)
    extractor.py       # pure FeatureExtractor (look-ahead protected)
  scoring/
    features.py        # FeatureVector + composite computation
    scorer.py          # Scorer Protocol
    rule_scorer.py     # weights × composites with regime multipliers
    ml_scorer.py       # LightGBM stub for Phase 3
  signal.py            # ATR-based SL/TP, profit tiers
  risk.py              # deterministic risk rules
  backtest/
    engine.py          # core simulator
    walk_forward.py    # train/test split iterator
    fills.py           # limit_with_fallback fill simulation
    metrics.py         # Sharpe, DD, alpha, IR
    statistical.py     # bootstrap CI, white reality check
    attribution.py     # per-factor PnL attribution
  allocation/
    composer.py        # core (SPY) + satellite (strategy) blending
  broker/
    alpaca.py          # paper trading adapter
configs/               # YAML strategy configs
docs/                  # mission, roadmap, limitations, retrospectives
tests/                 # pytest, mirrors bloasis/ structure
```

## Design principles

1. **Mission-driven** — every feature must serve the M2 → M1 progression
   defined in `docs/mission.md`.
2. **Honest measurement** — all metrics report relative to SPY benchmark.
   Walk-forward only; no full-history optimization.
3. **Look-ahead protection at the interface level** — `ExtractionContext`
   asserts data slicing.
4. **Pure core, I/O at edges** — `bloasis/scoring/` has no I/O. Same
   FeatureExtractor runs in live and backtest.
5. **Acceptance gates** — configs declare phase gates; CLI refuses to
   promote a config without walk-forward clearance.

## License

See [LICENSE](./LICENSE).
