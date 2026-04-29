"""BLOASIS CLI entry point.

Commands implemented:
  PR1
    bloasis version
    bloasis init-db [--db-path PATH]
    bloasis config show <yaml> [--set k.v=val]...
  PR2 (data layer)
    bloasis universe show <source> [--config YAML] [--as-of DATE] [--count]
    bloasis fetch ohlcv <SYMBOL> [--days N] [--config YAML]
    bloasis fetch fundamentals [--config YAML] [--max N]
    bloasis sentiment <SYMBOL> [--config YAML]
  PR3 (feature layer)
    bloasis features <SYMBOL> [--config YAML] [--days N]
  PR4 (scorer + signals)
    bloasis analyze SYM1 SYM2 [...] [--config YAML] [--top N] [--days N]
  PR5 (backtest)
    bloasis backtest --config YAML --start DATE --end DATE [--symbols ...]
    bloasis runs list [--limit N]
    bloasis runs show <run_id>
  PR6 (trade + composer)
    bloasis runs compare <run_id1> <run_id2>
    bloasis trade dry-run --config YAML -s SYM ...
    bloasis trade paper   --config YAML -s SYM ...
    bloasis trade live    --config YAML --from-run <id> -s SYM ... [--i-am-sure]
  PR7 (polish)
    backtest_runs.passed_acceptance + acceptance_reasons_json persisted
    `trade live` checks passed_acceptance directly + halt-condition gate
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.table import Table as RichTable

from bloasis import __version__
from bloasis.backtest.result import BacktestResult
from bloasis.config import StrategyConfig, config_hash, load_config
from bloasis.scoring.features import FeatureVector
from bloasis.storage import create_all, get_engine, metadata

if TYPE_CHECKING:
    from bloasis.broker import BrokerAdapter
    from bloasis.signal import CandidateData

app = typer.Typer(
    name="bloasis",
    help="Deterministic + ML trading research and execution CLI.",
    no_args_is_help=True,
    add_completion=False,
)

config_app = typer.Typer(name="config", help="Inspect and validate strategy configs.")
universe_app = typer.Typer(name="universe", help="Show universe membership.")
fetch_app = typer.Typer(name="fetch", help="Fetch and cache market data.")
runs_app = typer.Typer(name="runs", help="Inspect past backtest runs.")
trade_app = typer.Typer(name="trade", help="Execute strategy signals against a broker.")
app.add_typer(config_app, name="config")
app.add_typer(universe_app, name="universe")
app.add_typer(fetch_app, name="fetch")
app.add_typer(runs_app, name="runs")
app.add_typer(trade_app, name="trade")

console = Console()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_or_default_config(path: Path | None) -> StrategyConfig:
    """Load a YAML config if given, else return defaults (incl. data settings)."""
    if path is None:
        return StrategyConfig()
    return load_config(path)


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise typer.BadParameter(f"date must be YYYY-MM-DD, got {value!r}") from exc


# ---------------------------------------------------------------------------
# Existing commands (PR1)
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print the installed BLOASIS version."""
    console.print(f"bloasis {__version__}")


@app.command("init-db")
def init_db(
    db_path: Path = typer.Option(  # noqa: B008
        None,
        "--db-path",
        help="SQLite database path. Defaults to BLOASIS_DB_PATH or ./bloasis.db.",
    ),
) -> None:
    """Create the SQLite database and all tables.

    Idempotent — running on an existing database does not modify schema.
    """
    engine = get_engine(db_path)
    create_all(engine)

    table_names = sorted(metadata.tables.keys())
    console.print(f"[green]✓[/green] database initialized at [bold]{engine.url.database}[/bold]")
    console.print(f"  tables: {', '.join(table_names)}")


@config_app.command("show")
def config_show(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),  # noqa: B008
    set_overrides: list[str] = typer.Option(  # noqa: B008
        None,
        "--set",
        help="Inline override 'key.path=value'. Repeatable.",
    ),
) -> None:
    """Load a YAML config, apply overrides, validate, and print the resolved view."""
    cfg = load_config(path, overrides=set_overrides)
    digest = config_hash(cfg)

    summary = RichTable(title=f"{path.name}  ({digest})", show_header=False)
    summary.add_column("key", style="cyan")
    summary.add_column("value")

    summary.add_row("config_hash", digest)
    summary.add_row("universe.source", cfg.universe.source)
    summary.add_row("scorer.type", cfg.scorer.type)
    summary.add_row(
        "scorer.weights",
        ", ".join(f"{k}={v:.3f}" for k, v in cfg.scorer.weights.model_dump().items()),
    )
    summary.add_row(
        "scorer.entry/exit",
        f"{cfg.scorer.entry_threshold:.2f} / {cfg.scorer.exit_threshold:.2f}",
    )
    summary.add_row("execution.fill_mode", cfg.execution.fill_mode)
    summary.add_row(
        "allocation",
        ", ".join(f"{s.name}={s.weight:.2f}" for s in cfg.allocation.strategies) or "(empty)",
    )
    summary.add_row(
        "acceptance_criteria",
        f"alpha≥{cfg.acceptance_criteria.median_alpha_annualized:+.3f}, "
        f"sharpe≥{cfg.acceptance_criteria.median_sharpe_vs_spy:.2f}, "
        f"dd_ratio≤{cfg.acceptance_criteria.median_max_dd_ratio_to_spy:.2f}",
    )

    console.print(summary)
    console.print()
    console.print("[dim]Full resolved config (canonical JSON):[/dim]")
    console.print_json(json.dumps(json.loads(cfg.model_dump_json()), indent=2))


# ---------------------------------------------------------------------------
# Universe (PR2)
# ---------------------------------------------------------------------------


@universe_app.command("show")
def universe_show(
    source: str = typer.Argument(..., help="sp500 | sp500_historical | custom_csv"),
    as_of: str = typer.Option(  # noqa: B008
        None, "--as-of", help="Point-in-time membership (YYYY-MM-DD)."
    ),
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
    count_only: bool = typer.Option(  # noqa: B008
        False, "--count", help="Print count only, not the list."
    ),
    custom_csv_path: Path = typer.Option(  # noqa: B008
        None, "--csv", help="Required when source=custom_csv."
    ),
) -> None:
    """Resolve the universe to concrete tickers and print them."""
    from bloasis.config import UniverseConfig
    from bloasis.data.universe import load_universe

    cfg = _load_or_default_config(config_path)
    if source != cfg.universe.source or custom_csv_path is not None:
        # CLI override of universe source for ad-hoc inspection.
        universe_cfg = UniverseConfig(
            source=source,  # type: ignore[arg-type]
            custom_csv_path=custom_csv_path,
        )
    else:
        universe_cfg = cfg.universe

    as_of_date = _parse_date(as_of)
    if universe_cfg.source == "sp500_historical" and as_of_date is None:
        raise typer.BadParameter("sp500_historical requires --as-of YYYY-MM-DD")

    symbols = load_universe(universe_cfg, cfg.data, as_of=as_of_date)
    if count_only:
        console.print(len(symbols))
    else:
        console.print(f"[bold]{universe_cfg.source}[/bold]: {len(symbols)} symbols")
        console.print(", ".join(symbols))


# ---------------------------------------------------------------------------
# Fetch (PR2)
# ---------------------------------------------------------------------------


@fetch_app.command("ohlcv")
def fetch_ohlcv(
    symbol: str = typer.Argument(...),
    days: int = typer.Option(90, "--days", min=1),  # noqa: B008
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
) -> None:
    """Fetch and cache daily OHLCV for a symbol."""
    from bloasis.data.cache import ParquetCache
    from bloasis.data.fetchers.yfinance_ohlcv import YfOhlcvFetcher

    cfg = _load_or_default_config(config_path)
    cache = ParquetCache(cfg.data.cache_dir, namespace="ohlcv")
    fetcher = YfOhlcvFetcher(cache=cache, max_age_hours=cfg.data.ohlcv_cache_max_age_hours)

    end = datetime.now(tz=UTC).date()
    start = end - timedelta(days=days)
    df = fetcher.fetch(symbol, start, end)
    console.print(
        f"[green]✓[/green] {symbol}: {len(df)} bars "
        f"({df.index.min().date()} .. {df.index.max().date()})"
    )
    console.print(f"  cached at: {cache.root}")


@fetch_app.command("fundamentals")
def fetch_fundamentals(
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
    max_count: int = typer.Option(1000, "--max", min=1),  # noqa: B008
) -> None:
    """Bulk-fetch fundamentals via yfinance Screener and write to fundamentals_cache."""
    from datetime import timedelta as _td

    from sqlalchemy import insert

    from bloasis.data.fetchers.yfinance_screener import YfFundamentalsFetcher
    from bloasis.storage import fundamentals_cache

    cfg = _load_or_default_config(config_path)
    engine = get_engine()
    create_all(engine)

    fetcher = YfFundamentalsFetcher()
    rows = fetcher.fetch_bulk(max_count=max_count)
    if not rows:
        console.print("[yellow]no rows returned from screener[/yellow]")
        raise typer.Exit(code=1)

    expires_at = rows[0].fetched_at + _td(hours=cfg.data.fundamentals_cache_max_age_hours)
    with engine.begin() as conn:
        for row in rows:
            conn.execute(
                insert(fundamentals_cache).values(
                    symbol=row.symbol,
                    fetched_at=row.fetched_at,
                    sector=row.sector,
                    industry=row.industry,
                    market_cap=row.market_cap,
                    pe_ratio_ttm=row.pe_ratio_ttm,
                    pb_ratio=row.pb_ratio,
                    dollar_volume_avg=row.dollar_volume_avg,
                    profit_margin=row.profit_margin,
                    roe=row.roe,
                    debt_to_equity=row.debt_to_equity,
                    current_ratio=row.current_ratio,
                    expires_at=expires_at,
                )
            )
    console.print(f"[green]✓[/green] fetched {len(rows)} fundamentals rows")


# ---------------------------------------------------------------------------
# Sentiment (PR2)
# ---------------------------------------------------------------------------


@app.command("sentiment")
def sentiment_show(
    symbol: str = typer.Argument(...),
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
    force_refresh: bool = typer.Option(  # noqa: B008
        False, "--refresh", help="Bypass cache."
    ),
) -> None:
    """Score recent news sentiment for a symbol."""
    from bloasis.data.fetchers.finnhub_news import FinnhubNewsFetcher
    from bloasis.data.sentiment import SentimentScorer

    cfg = _load_or_default_config(config_path)
    finnhub_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not finnhub_key:
        console.print("[red]FINNHUB_API_KEY env var required[/red]")
        raise typer.Exit(code=1)

    engine = get_engine()
    create_all(engine)

    news = FinnhubNewsFetcher(finnhub_key, rate_per_minute=cfg.data.finnhub_rate_per_minute)
    scorer = SentimentScorer(
        news_fetcher=news,
        db_engine=engine,
        cache_ttl_hours=cfg.data.sentiment_cache_max_age_hours,
        lookback_days=cfg.data.sentiment_lookback_days,
    )
    result = scorer.score(symbol, force_refresh=force_refresh)

    summary = RichTable(title=f"sentiment: {result.symbol}", show_header=False)
    summary.add_column("key", style="cyan")
    summary.add_column("value")
    summary.add_row("score", f"{result.score:+.3f}")
    summary.add_row("article_count", str(result.article_count))
    summary.add_row("rationale", result.rationale)
    summary.add_row("fetched_at", result.fetched_at.isoformat())
    console.print(summary)


# ---------------------------------------------------------------------------
# Features (PR3)
# ---------------------------------------------------------------------------


@app.command("features")
def features_show(
    symbol: str = typer.Argument(...),
    days: int = typer.Option(  # noqa: B008
        365, "--days", min=60, help="OHLCV window in days (>=60 for momentum_60d)."
    ),
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
) -> None:
    """Extract a FeatureVector for a symbol at the latest bar.

    Live mode: pulls OHLCV via yfinance + uses default fundamentals (none
    pre-fetched). Sentiment is NaN — run `bloasis sentiment <SYMBOL>` first
    if you want sentiment populated.
    """
    from bloasis.data.cache import ParquetCache
    from bloasis.data.fetchers.yfinance_market import YfMarketContextFetcher
    from bloasis.data.fetchers.yfinance_ohlcv import YfOhlcvFetcher
    from bloasis.scoring.extractor import ExtractionContext, FeatureExtractor
    from bloasis.scoring.regime import classify_regime

    cfg = _load_or_default_config(config_path)
    cache = ParquetCache(cfg.data.cache_dir, namespace="ohlcv")
    ohlcv_fetcher = YfOhlcvFetcher(cache=cache, max_age_hours=cfg.data.ohlcv_cache_max_age_hours)
    market_fetcher = YfMarketContextFetcher(ohlcv=ohlcv_fetcher)

    end = datetime.now(tz=UTC).date()
    start = end - timedelta(days=days)

    ohlcv = ohlcv_fetcher.fetch(symbol, start, end)
    market = market_fetcher.fetch(start, end)

    ts = ohlcv.index[-1].to_pydatetime()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    ctx = ExtractionContext(
        timestamp=ts,
        symbol=symbol.upper(),
        feature_version=FeatureExtractor.VERSION,
        sector=None,
        ohlcv=ohlcv,
        fundamentals={},
        vix_series=market.vix,
        spy_close_series=market.spy_close,
        sentiment_score=None,
        news_count=None,
    )
    fv = FeatureExtractor().extract(ctx)
    regime = classify_regime(fv.vix, fv.spy_above_sma200)

    summary = RichTable(title=f"features: {fv.symbol}", show_header=True)
    summary.add_column("name", style="cyan")
    summary.add_column("value", justify="right")
    for col in fv.FEATURE_COLUMNS:
        v = getattr(fv, col)
        if isinstance(v, float) and v != v:
            display = "[dim]NaN[/dim]"
        else:
            display = f"{v:+.4f}" if isinstance(v, float) else str(v)
        summary.add_row(col, display)
    summary.add_row("[bold]regime[/bold]", f"[bold]{regime}[/bold]")
    console.print(summary)


# ---------------------------------------------------------------------------
# Analyze (PR4)
# ---------------------------------------------------------------------------


@app.command("analyze")
def analyze(
    symbols: list[str] = typer.Argument(  # noqa: B008
        ..., help="Two or more symbols to score in cross-section."
    ),
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
    days: int = typer.Option(  # noqa: B008
        365, "--days", min=60, help="OHLCV window in days (>=60 for momentum_60d)."
    ),
    top: int = typer.Option(  # noqa: B008
        10, "--top", min=1, help="Show this many top-ranked symbols."
    ),
) -> None:
    """Extract features, build composites, score, and emit signals.

    Cross-section z-scoring requires at least two symbols. The CLI
    bypasses universe loading — pass the symbols you want to compare.
    `last_close` and ATR for signal levels come from the same yfinance
    OHLCV pull as the features.
    """
    from bloasis.data.cache import ParquetCache
    from bloasis.data.fetchers.yfinance_market import YfMarketContextFetcher
    from bloasis.data.fetchers.yfinance_ohlcv import YfOhlcvFetcher
    from bloasis.risk import MarketState, PortfolioState, RiskEvaluator
    from bloasis.scoring.composites import CompositeBuilder
    from bloasis.scoring.extractor import ExtractionContext, FeatureExtractor
    from bloasis.scoring.scorer import RuleBasedScorer
    from bloasis.signal import CandidateData, SignalGenerator

    if len(symbols) < 2:
        raise typer.BadParameter("analyze requires at least 2 symbols for cross-section z-score")

    cfg = _load_or_default_config(config_path)
    cache = ParquetCache(cfg.data.cache_dir, namespace="ohlcv")
    ohlcv_fetcher = YfOhlcvFetcher(cache=cache, max_age_hours=cfg.data.ohlcv_cache_max_age_hours)
    market_fetcher = YfMarketContextFetcher(ohlcv=ohlcv_fetcher)
    extractor = FeatureExtractor()

    end = datetime.now(tz=UTC).date()
    start = end - timedelta(days=days)
    market = market_fetcher.fetch(start, end)

    # 1. Extract per-symbol feature vectors + last close.
    feature_vectors: list[FeatureVector] = []
    last_closes: dict[str, float] = {}
    for sym in symbols:
        ohlcv = ohlcv_fetcher.fetch(sym.upper(), start, end)
        ts = ohlcv.index[-1].to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        ctx = ExtractionContext(
            timestamp=ts,
            symbol=sym.upper(),
            feature_version=FeatureExtractor.VERSION,
            sector=None,
            ohlcv=ohlcv,
            fundamentals={},
            vix_series=market.vix,
            spy_close_series=market.spy_close,
        )
        fv = extractor.extract(ctx)
        feature_vectors.append(fv)
        last_closes[fv.symbol] = float(ohlcv["close"].iloc[-1])

    # 2. Cross-section composites.
    composites = CompositeBuilder().build(feature_vectors)
    cv_by_symbol = {c.symbol: c for c in composites}

    # 3. Score.
    scorer = RuleBasedScorer(cfg.scorer)
    scored = [scorer.score(fv, cv_by_symbol[fv.symbol]) for fv in feature_vectors]
    scored.sort(key=lambda s: s.score, reverse=True)

    # 4. Signals (no held positions in CLI demo).
    signal_gen = SignalGenerator(cfg.scorer, cfg.signal)
    candidates = [
        CandidateData(
            scored=s,
            feature_vector=next(fv for fv in feature_vectors if fv.symbol == s.symbol),
            last_close=last_closes[s.symbol],
        )
        for s in scored
    ]
    signals = signal_gen.generate(candidates, held=())
    signal_by_symbol = {s.symbol: s for s in signals}

    # 5. Risk evaluation against an empty portfolio (no concentration).
    market_vix = float(feature_vectors[0].vix) if feature_vectors else float("nan")
    market_state = MarketState(timestamp=feature_vectors[0].timestamp, vix=market_vix)
    portfolio = PortfolioState()
    risk = RiskEvaluator(cfg.risk)

    # 6. Render top N.
    table = RichTable(title=f"analyze ({len(symbols)} symbols, top {top})", show_lines=True)
    table.add_column("rank", style="dim", justify="right")
    table.add_column("symbol", style="cyan")
    table.add_column("score", justify="right")
    table.add_column("signal", style="bold")
    table.add_column("size%", justify="right")
    table.add_column("entry", justify="right")
    table.add_column("SL", justify="right")
    table.add_column("TP", justify="right")
    table.add_column("triggers / risks")

    for rank, sc in enumerate(scored[:top], start=1):
        sig = signal_by_symbol.get(sc.symbol)
        if sig is not None and sig.action == "BUY":
            decision = risk.evaluate(sig, portfolio, market_state)
            applied_size = (
                decision.adjusted_size_pct
                if decision.adjusted_size_pct is not None
                else sig.target_size_pct
            )
            sig_label = sig.action if decision.action != "REJECT" else f"{sig.action} → REJECT"
            entry = f"{sig.entry_price:.2f}" if sig.entry_price is not None else "-"
            sl = f"{sig.stop_loss:.2f}" if sig.stop_loss is not None else "-"
            tp = f"{sig.take_profit:.2f}" if sig.take_profit is not None else "-"
            size_str = f"{applied_size * 100:.2f}%"
        else:
            sig_label = "HOLD"
            entry = sl = tp = "-"
            size_str = "-"

        flags = ", ".join(sc.rationale.triggers + sc.rationale.risks) or "-"
        table.add_row(
            str(rank),
            sc.symbol,
            f"{sc.score:.3f}",
            sig_label,
            size_str,
            entry,
            sl,
            tp,
            flags,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Backtest (PR5)
# ---------------------------------------------------------------------------


@app.command("backtest")
def backtest(
    start: str = typer.Option(..., "--start", help="YYYY-MM-DD"),  # noqa: B008
    end: str = typer.Option(..., "--end", help="YYYY-MM-DD"),  # noqa: B008
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
    symbols: list[str] = typer.Option(  # noqa: B008
        None,
        "--symbol",
        "-s",
        help="Symbol to include. Repeatable. Required (universe fetching is PR6).",
    ),
    name: str = typer.Option(None, "--name", help="Optional run label."),  # noqa: B008
    train_days: int = typer.Option(  # noqa: B008
        365 * 3, "--train-days", min=30, help="Walk-forward train window."
    ),
    test_days: int = typer.Option(  # noqa: B008
        180, "--test-days", min=10, help="Walk-forward test window."
    ),
    step_days: int = typer.Option(180, "--step-days", min=1),  # noqa: B008
) -> None:
    """Run a walk-forward backtest, persist the run, and print metrics."""
    import pandas as pd

    from bloasis.backtest import BacktestData, Backtester
    from bloasis.config import config_hash as compute_config_hash
    from bloasis.data.cache import ParquetCache
    from bloasis.data.fetchers.yfinance_market import YfMarketContextFetcher
    from bloasis.data.fetchers.yfinance_ohlcv import YfOhlcvFetcher
    from bloasis.scoring.extractor import FeatureExtractor
    from bloasis.storage import writers

    if not symbols:
        raise typer.BadParameter("at least one --symbol/-s is required")

    cfg = _load_or_default_config(config_path)
    start_d = _parse_date(start)
    end_d = _parse_date(end)
    if start_d is None or end_d is None:
        raise typer.BadParameter("--start and --end are required (YYYY-MM-DD)")

    # Pre-fetch OHLCV with warmup. The backtester slices per-day internally.
    cache = ParquetCache(cfg.data.cache_dir, namespace="ohlcv")
    ohlcv = YfOhlcvFetcher(cache=cache, max_age_hours=cfg.data.ohlcv_cache_max_age_hours)
    market = YfMarketContextFetcher(ohlcv=ohlcv)

    warmup = timedelta(days=300)
    fetch_start = start_d - warmup
    bars: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        bars[sym.upper()] = ohlcv.fetch(sym.upper(), fetch_start, end_d)
    market_ctx = market.fetch(fetch_start, end_d)

    data = BacktestData(
        symbols=[s.upper() for s in symbols],
        bars=bars,
        vix_series=market_ctx.vix,
        spy_close_series=market_ctx.spy_close,
    )

    engine = get_engine()
    create_all(engine)

    cfg_hash = compute_config_hash(cfg)
    cfg_json = cfg.model_dump_json()
    run_id = writers.create_backtest_run(
        engine,
        name=name,
        config_hash=cfg_hash,
        config_json=cfg_json,
        scorer_type=cfg.scorer.type,
        feature_version=FeatureExtractor.VERSION,
        start_date=datetime(start_d.year, start_d.month, start_d.day, tzinfo=UTC),
        end_date=datetime(end_d.year, end_d.month, end_d.day, tzinfo=UTC),
        initial_capital=cfg.execution.initial_capital,
    )

    try:
        bt = Backtester(cfg, data, db_engine=engine)
        result = bt.run(
            start_d,
            end_d,
            run_id=run_id,
            train_days=train_days,
            test_days=test_days,
            step_days=step_days,
        )
        from dataclasses import replace

        result = replace(result, config_hash=cfg_hash)
        writers.finalize_backtest_run(engine, run_id, result)
    except Exception as exc:
        writers.fail_backtest_run(engine, run_id, str(exc))
        raise

    _render_backtest_result(result, cfg_hash)


@runs_app.command("list")
def runs_list(
    limit: int = typer.Option(20, "--limit", min=1, max=200),  # noqa: B008
) -> None:
    """List the most recent backtest runs."""
    from sqlalchemy import select

    from bloasis.storage import backtest_runs as br_table

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                br_table.c.run_id,
                br_table.c.name,
                br_table.c.config_hash,
                br_table.c.start_date,
                br_table.c.end_date,
                br_table.c.status,
                br_table.c.alpha_vs_spy,
                br_table.c.sharpe,
                br_table.c.n_trades,
                br_table.c.started_at,
            )
            .order_by(br_table.c.started_at.desc())
            .limit(limit)
        ).fetchall()

    table = RichTable(title=f"runs (latest {len(rows)})")
    table.add_column("run_id", justify="right")
    table.add_column("name")
    table.add_column("hash", style="dim")
    table.add_column("period")
    table.add_column("status")
    table.add_column("alpha", justify="right")
    table.add_column("sharpe", justify="right")
    table.add_column("trades", justify="right")
    for r in rows:
        table.add_row(
            str(r.run_id),
            r.name or "-",
            r.config_hash,
            f"{r.start_date.date()} ~ {r.end_date.date()}",
            r.status,
            f"{r.alpha_vs_spy:+.3f}" if r.alpha_vs_spy is not None else "-",
            f"{r.sharpe:.2f}" if r.sharpe is not None else "-",
            str(r.n_trades) if r.n_trades is not None else "-",
        )
    console.print(table)


@runs_app.command("show")
def runs_show(run_id: int = typer.Argument(...)) -> None:
    """Show details + acceptance result for a single backtest run."""
    from sqlalchemy import select

    from bloasis.storage import backtest_runs as br_table

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(select(br_table).where(br_table.c.run_id == run_id)).first()
    if row is None:
        console.print(f"[red]run_id {run_id} not found[/red]")
        raise typer.Exit(code=1)

    summary = RichTable(title=f"run {run_id} ({row.config_hash})", show_header=False)
    summary.add_column("key", style="cyan")
    summary.add_column("value")
    for col, label in [
        ("name", "name"),
        ("scorer_type", "scorer"),
        ("status", "status"),
        ("start_date", "start"),
        ("end_date", "end"),
        ("initial_capital", "initial $"),
        ("final_equity", "final $"),
        ("total_return", "total return"),
        ("annualized_return", "annualized"),
        ("sharpe", "sharpe"),
        ("max_drawdown", "max DD"),
        ("alpha_vs_spy", "alpha vs SPY"),
        ("win_rate", "win rate"),
        ("n_trades", "trades"),
    ]:
        v = getattr(row, col)
        if v is None:
            display = "-"
        elif isinstance(v, float):
            display = f"{v:.4f}"
        else:
            display = str(v)
        summary.add_row(label, display)
    # Acceptance gate result.
    accept_label = "[green]YES[/green]" if row.passed_acceptance else "[red]NO[/red]"
    if row.passed_acceptance is None:
        accept_label = "-"
    summary.add_row("passed_acceptance", accept_label)
    if row.acceptance_reasons_json:
        for line in json.loads(row.acceptance_reasons_json):
            color = "green" if line.startswith("PASS") else "red"
            summary.add_row(f"  {line[:4]}", f"[{color}]{line[5:]}[/{color}]")
    if row.error_message:
        summary.add_row("[red]error[/red]", row.error_message)
    console.print(summary)


def _render_backtest_result(
    result: BacktestResult,
    cfg_hash: str,
) -> None:
    """Render a BacktestResult to console."""
    table = RichTable(title=f"backtest run {result.run_id} ({cfg_hash})", show_header=True)
    table.add_column("fold", style="dim", justify="right")
    table.add_column("test period")
    table.add_column("alpha", justify="right")
    table.add_column("sharpe", justify="right")
    table.add_column("DD/SPY", justify="right")
    table.add_column("trades", justify="right")
    for f in result.fold_results:
        table.add_row(
            str(f.fold_index),
            f"{f.test_start} .. {f.test_end}",
            f"{f.annualized_alpha:+.3f}",
            f"{f.sharpe:.2f}",
            f"{f.max_dd_ratio_to_spy:.2f}",
            str(f.n_trades),
        )
    console.print(table)

    summary = RichTable(title="aggregate (median)", show_header=False)
    summary.add_column("key", style="cyan")
    summary.add_column("value")
    summary.add_row("median_alpha_annualized", f"{result.median_alpha_annualized:+.4f}")
    summary.add_row("median_sharpe_vs_spy", f"{result.median_sharpe_vs_spy:.3f}")
    summary.add_row("median_max_dd_ratio_to_spy", f"{result.median_max_dd_ratio_to_spy:.3f}")
    summary.add_row("median_total_return", f"{result.median_total_return:+.4f}")
    summary.add_row("median_spy_total_return", f"{result.median_spy_total_return:+.4f}")
    summary.add_row("n_folds", str(result.n_folds))
    summary.add_row("n_trades_total", str(result.n_trades_total))
    summary.add_row(
        "passed_acceptance",
        "[green]YES[/green]" if result.passed_acceptance else "[red]NO[/red]",
    )
    console.print(summary)

    console.print()
    console.print("[bold]Acceptance gate:[/bold]")
    for line in result.acceptance_reasons:
        if line.startswith("PASS"):
            console.print(f"  [green]{line}[/green]")
        else:
            console.print(f"  [red]{line}[/red]")


# ---------------------------------------------------------------------------
# runs compare (PR6)
# ---------------------------------------------------------------------------


@runs_app.command("compare")
def runs_compare(
    run_id_a: int = typer.Argument(..., metavar="RUN_A"),  # noqa: B008
    run_id_b: int = typer.Argument(..., metavar="RUN_B"),  # noqa: B008
) -> None:
    """Side-by-side metric + config diff between two backtest runs."""
    from sqlalchemy import select

    from bloasis.storage import backtest_runs as br_table

    engine = get_engine()
    with engine.connect() as conn:
        rows = {
            r.run_id: r
            for r in conn.execute(
                select(br_table).where(br_table.c.run_id.in_([run_id_a, run_id_b]))
            ).fetchall()
        }
    if run_id_a not in rows or run_id_b not in rows:
        missing = [r for r in (run_id_a, run_id_b) if r not in rows]
        console.print(f"[red]run_id(s) not found: {missing}[/red]")
        raise typer.Exit(code=1)

    a, b = rows[run_id_a], rows[run_id_b]
    table = RichTable(title=f"compare run {run_id_a} vs {run_id_b}")
    table.add_column("metric", style="cyan")
    table.add_column(f"#{run_id_a}", justify="right")
    table.add_column(f"#{run_id_b}", justify="right")
    table.add_column("delta", justify="right", style="bold")

    for col, label in [
        ("config_hash", "config_hash"),
        ("scorer_type", "scorer"),
        ("status", "status"),
        ("passed_acceptance", "passed"),
        ("total_return", "total_return"),
        ("annualized_return", "annualized"),
        ("sharpe", "sharpe"),
        ("max_drawdown", "max_dd"),
        ("alpha_vs_spy", "alpha_vs_spy"),
        ("win_rate", "win_rate"),
        ("n_trades", "trades"),
    ]:
        va, vb = getattr(a, col), getattr(b, col)
        delta_str = "-"
        if (
            isinstance(va, (int, float))
            and isinstance(vb, (int, float))
            and (va is not None and vb is not None)
        ):
            delta = vb - va
            delta_str = f"{delta:+.4f}" if isinstance(delta, float) else f"{delta:+d}"
        table.add_row(label, _fmt_cell(va), _fmt_cell(vb), delta_str)
    console.print(table)


def _fmt_cell(v: object) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


# ---------------------------------------------------------------------------
# trade (PR6)
# ---------------------------------------------------------------------------


@trade_app.command("dry-run")
def trade_dry_run(
    symbols: list[str] = typer.Option(  # noqa: B008
        None, "--symbol", "-s", help="Symbol to consider. Repeatable."
    ),
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
    days: int = typer.Option(  # noqa: B008
        365, "--days", min=60, help="OHLCV window for feature extraction."
    ),
) -> None:
    """Generate signals and route through InMemoryPaperBroker — no network.

    Useful as a final sanity check that the wiring works before pointing
    at a real Alpaca account.
    """
    from bloasis.broker import InMemoryPaperBroker

    if not symbols or len(symbols) < 2:
        raise typer.BadParameter("at least 2 --symbol/-s entries required")

    cfg = _load_or_default_config(config_path)
    candidates, last_closes = _build_live_candidates(cfg, symbols, days)

    if not candidates:
        console.print("[yellow]no candidates produced (need 2+ symbols with data)[/yellow]")
        raise typer.Exit(code=1)

    broker = InMemoryPaperBroker(
        price_fn=lambda s: last_closes.get(s, 0.0),
        initial_cash=cfg.execution.initial_capital,
        slippage_bps=cfg.execution.market_slippage_bps,
    )
    _execute_against_broker(cfg, candidates, broker, label="dry-run")


@trade_app.command("paper")
def trade_paper(
    symbols: list[str] = typer.Option(  # noqa: B008
        None, "--symbol", "-s"
    ),
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
    days: int = typer.Option(365, "--days", min=60),  # noqa: B008
) -> None:
    """Submit BUY/SELL signals to Alpaca paper account."""
    from bloasis.broker import AlpacaBrokerAdapter

    if not symbols or len(symbols) < 2:
        raise typer.BadParameter("at least 2 --symbol/-s entries required")

    cfg = _load_or_default_config(config_path)
    candidates, _last_closes = _build_live_candidates(cfg, symbols, days)
    if not candidates:
        console.print("[yellow]no candidates produced[/yellow]")
        raise typer.Exit(code=1)

    broker = AlpacaBrokerAdapter(mode="paper")
    _execute_against_broker(cfg, candidates, broker, label="paper")


@trade_app.command("live")
def trade_live(
    symbols: list[str] = typer.Option(  # noqa: B008
        None, "--symbol", "-s"
    ),
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
    from_run: int = typer.Option(  # noqa: B008
        ..., "--from-run", help="Backtest run_id whose acceptance gate gates this."
    ),
    i_am_sure: bool = typer.Option(  # noqa: B008
        False, "--i-am-sure", help="Skip the interactive confirmation prompt."
    ),
    days: int = typer.Option(365, "--days", min=60),  # noqa: B008
) -> None:
    """Submit BUY/SELL signals to Alpaca LIVE account.

    Multi-stage gate (per docs/mission.md):
      1. ALPACA_LIVE_API_KEY must be set.
      2. --from-run <id> required and run must exist.
      3. backtest_runs[id].status == 'completed'.
      4. backtest_runs[id].passed_acceptance is True.
      5. Halt-condition: realized PnL over rolling window must be above floor.
      6. Interactive 'I AM SURE' OR --i-am-sure flag.
    """
    from sqlalchemy import select

    from bloasis.broker import AlpacaBrokerAdapter
    from bloasis.runtime.halt import evaluate_halt
    from bloasis.storage import backtest_runs as br_table

    if not symbols or len(symbols) < 2:
        raise typer.BadParameter("at least 2 --symbol/-s entries required")

    # Gate 1: live key present.
    if not os.environ.get("ALPACA_LIVE_API_KEY"):
        console.print("[red]ALPACA_LIVE_API_KEY not set; refusing live mode[/red]")
        raise typer.Exit(code=1)

    # Gate 2/3/4: read backtest run + acceptance.
    cfg = _load_or_default_config(config_path)
    engine = get_engine()
    with engine.connect() as conn:
        run_row = conn.execute(select(br_table).where(br_table.c.run_id == from_run)).first()
    if run_row is None:
        console.print(f"[red]backtest run {from_run} not found[/red]")
        raise typer.Exit(code=1)
    if run_row.status != "completed":
        console.print(f"[red]run {from_run} status={run_row.status}; cannot promote[/red]")
        raise typer.Exit(code=1)
    if not run_row.passed_acceptance:
        console.print(f"[red]run {from_run} did not pass acceptance gate; refusing live[/red]")
        raise typer.Exit(code=1)

    # Gate 5: halt-condition check on recent live realized PnL.
    halt = evaluate_halt(
        engine,
        cfg.risk,
        initial_capital=cfg.execution.initial_capital,
        now=datetime.now(tz=UTC),
    )
    if halt.should_halt:
        console.print(f"[red]HALT: {halt.reason}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[dim]halt check: {halt.reason}[/dim]")

    # Gate 6: interactive confirmation.
    if not i_am_sure:
        console.print(
            f"[yellow]About to submit LIVE orders. Run #{from_run} alpha "
            f"{run_row.alpha_vs_spy:+.4f}.[/yellow]"
        )
        confirm = typer.prompt("Type 'I AM SURE' to proceed")
        if confirm.strip() != "I AM SURE":
            console.print("aborted")
            raise typer.Exit(code=1)

    candidates, _last_closes = _build_live_candidates(cfg, symbols, days)
    if not candidates:
        console.print("[yellow]no candidates produced[/yellow]")
        raise typer.Exit(code=1)

    broker = AlpacaBrokerAdapter(mode="live")
    _execute_against_broker(cfg, candidates, broker, label="live")


def _build_live_candidates(
    cfg: StrategyConfig,
    symbols: list[str],
    days: int,
) -> tuple[list[CandidateData], dict[str, float]]:
    """Pull OHLCV + market context, build candidates ranked by score.

    Returned tuple is `(candidates, last_close_by_symbol)`. Empty list
    when fewer than 2 symbols produced features (cross-section z-score
    requires ≥ 2).
    """
    from bloasis.data.cache import ParquetCache
    from bloasis.data.fetchers.yfinance_market import YfMarketContextFetcher
    from bloasis.data.fetchers.yfinance_ohlcv import YfOhlcvFetcher
    from bloasis.scoring.composites import CompositeBuilder
    from bloasis.scoring.extractor import ExtractionContext, FeatureExtractor
    from bloasis.scoring.scorer import RuleBasedScorer
    from bloasis.signal import CandidateData

    cache = ParquetCache(cfg.data.cache_dir, namespace="ohlcv")
    ohlcv_fetcher = YfOhlcvFetcher(cache=cache, max_age_hours=cfg.data.ohlcv_cache_max_age_hours)
    market_fetcher = YfMarketContextFetcher(ohlcv=ohlcv_fetcher)
    extractor = FeatureExtractor()

    end = datetime.now(tz=UTC).date()
    start = end - timedelta(days=days)
    market = market_fetcher.fetch(start, end)

    feature_vectors: list[FeatureVector] = []
    last_closes: dict[str, float] = {}
    for sym in symbols:
        ohlcv = ohlcv_fetcher.fetch(sym.upper(), start, end)
        ts = ohlcv.index[-1].to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        ctx = ExtractionContext(
            timestamp=ts,
            symbol=sym.upper(),
            feature_version=FeatureExtractor.VERSION,
            sector=None,
            ohlcv=ohlcv,
            fundamentals={},
            vix_series=market.vix,
            spy_close_series=market.spy_close,
        )
        feature_vectors.append(extractor.extract(ctx))
        last_closes[sym.upper()] = float(ohlcv["close"].iloc[-1])

    if len(feature_vectors) < 2:
        return [], last_closes
    composites = CompositeBuilder().build(feature_vectors)
    cv_by_sym = {c.symbol: c for c in composites}
    scorer = RuleBasedScorer(cfg.scorer)
    scored = [scorer.score(fv, cv_by_sym[fv.symbol]) for fv in feature_vectors]
    candidates = [
        CandidateData(
            scored=s,
            feature_vector=next(fv for fv in feature_vectors if fv.symbol == s.symbol),
            last_close=last_closes[s.symbol],
        )
        for s in scored
    ]
    return candidates, last_closes


def _execute_against_broker(
    cfg: StrategyConfig,
    candidates: list[CandidateData],
    broker: BrokerAdapter,
    *,
    label: str,
) -> None:
    """Translate signals into broker orders and print the result table."""
    from bloasis.allocation.composer import StrategyComposer
    from bloasis.broker import BrokerAdapter, BrokerOrder
    from bloasis.signal import SignalGenerator

    assert isinstance(broker, BrokerAdapter), "broker must implement BrokerAdapter"

    sig_gen = SignalGenerator(cfg.scorer, cfg.signal)
    signals = sig_gen.generate(candidates, held=())

    account = broker.get_account()
    composer = StrategyComposer(cfg.allocation)
    plan = composer.plan(total_capital=account.cash, spy_price=None)

    table = RichTable(title=f"trade {label}")
    table.add_column("symbol", style="cyan")
    table.add_column("side", style="bold")
    table.add_column("qty", justify="right")
    table.add_column("status")
    table.add_column("filled $", justify="right")
    table.add_column("reason")

    # Use plan.strategy_capital (slice for this strategy) to size orders.
    capital_for_strategy = plan.strategy_capital if plan.strategy_capital > 0 else account.cash

    for sig in signals:
        if sig.action != "BUY":
            continue
        if sig.entry_price is None or sig.entry_price <= 0:
            continue
        target = capital_for_strategy * sig.target_size_pct
        qty = target / float(sig.entry_price)
        if qty <= 0:
            continue
        order = BrokerOrder(
            symbol=sig.symbol,
            side="buy",
            qty=qty,
            client_order_id=f"bloasis-{label}-{sig.symbol}-{int(sig.timestamp.timestamp())}",
        )
        result = broker.place_market_order(order)
        table.add_row(
            sig.symbol,
            "buy",
            f"{qty:.4f}",
            result.status,
            f"{result.filled_avg_price * result.filled_qty:.2f}",
            result.reason or sig.reason,
        )

    console.print(table)
    console.print(
        f"[dim]broker={broker.mode} | strategy_capital=${capital_for_strategy:,.2f} | "
        f"spy_qty={plan.spy_share_qty}[/dim]"
    )


if __name__ == "__main__":
    app()
