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
import sys
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
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
ml_app = typer.Typer(name="ml", help="Phase 2 ML pipeline (training, prediction).")
grid_app = typer.Typer(
    name="grid",
    help="Combinatorial backtest grid runner (PR21). See docs/e2e/grid-runner-checklist.md.",
)
paper_app = typer.Typer(
    name="paper",
    help="Inspect paper-trading sessions (PR47): list, show details, friction, close.",
)
app.add_typer(config_app, name="config")
app.add_typer(universe_app, name="universe")
app.add_typer(fetch_app, name="fetch")
app.add_typer(runs_app, name="runs")
app.add_typer(trade_app, name="trade")
app.add_typer(ml_app, name="ml")
app.add_typer(grid_app, name="grid")
app.add_typer(paper_app, name="paper")

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


@app.command("label-features")
def label_features(
    config_path: Path = typer.Option(  # noqa: B008
        None, "--config", "-c", help="Strategy YAML (uses defaults if omitted)."
    ),
    db_path: Path = typer.Option(  # noqa: B008
        None,
        "--db-path",
        help="SQLite database path. Defaults to BLOASIS_DB_PATH or ./bloasis.db.",
    ),
) -> None:
    """Fill `forward_return_5d/20d/60d` for all unlabeled `feature_log` rows.

    Reads close-series from the local OHLCV parquet cache (whichever cache
    file for a symbol covers the latest forward bar). Symbols with no
    cached OHLCV are skipped — re-run after fetching to pick them up.

    Idempotent + cron-friendly: rows with `label_filled_at IS NOT NULL`
    are not retouched. Rows whose forward window doesn't fit in the cache
    still get `label_filled_at` set (NULL labels) so they don't replay.
    """
    import pandas as pd

    from bloasis.ml.labeling import label_unlabeled_features

    cfg = _load_or_default_config(config_path)
    engine = get_engine(db_path)
    create_all(engine)

    parquet_dir = cfg.data.cache_dir / "parquet" / "ohlcv"

    def _load_widest_for_symbol(symbol: str) -> pd.Series | None:
        """Pick the parquet file for `symbol` covering the longest date
        span. Same symbol can have multiple cache windows from different
        backtest fetches (e.g. `<sym>_2013-03_2019-12`, `<sym>_2018-03_2024-12`,
        `<sym>_2025-05-05_2026-05-05` — a 1-day fresh fetch).

        Picking by row count alone is wrong (1-day file has 1 row, but a
        7-year file has ~1750 — both can lose to a 5-year file by raw count
        if compression varies). Picking by `index.max()` is also wrong
        (a 1-day file dated tomorrow wins). Picking by **span** (max - min
        in days) correctly prefers the 7-year file in every case.

        Returns the close series (tz-naive), or None when no cache hit.
        """
        if not parquet_dir.exists():
            return None
        candidates = list(parquet_dir.glob(f"{symbol}_*.parquet"))
        if not candidates:
            return None
        best_df: pd.DataFrame | None = None
        best_span_days = -1
        for p in candidates:
            try:
                df = pd.read_parquet(p)
            except Exception:  # noqa: BLE001 — corrupt parquet, skip
                continue
            if "close" not in df.columns or df.empty:
                continue
            span = (pd.Timestamp(df.index.max()) - pd.Timestamp(df.index.min())).days
            if span > best_span_days:
                best_df = df
                best_span_days = span
        if best_df is None:
            return None
        s = best_df["close"].sort_index()
        s.index = pd.DatetimeIndex(s.index).tz_localize(None)
        return s

    n = label_unlabeled_features(engine, ohlcv_provider=_load_widest_for_symbol)
    console.print(f"[green]✓[/green] labeled [bold]{n}[/bold] feature_log rows")


@ml_app.command("train")
def ml_train(
    feature_version: int = typer.Option(  # noqa: B008
        2, "--feature-version", help="feature_log version to train on (default: 2)."
    ),
    label: str = typer.Option(  # noqa: B008
        "forward_return_20d",
        "--label",
        help="Label column: forward_return_5d/20d/60d.",
    ),
    n_folds: int = typer.Option(5, "--n-folds", min=2, help="Walk-forward CV folds."),  # noqa: B008
    embargo_days: int = typer.Option(  # noqa: B008
        21, "--embargo-days", min=0, help="Train/test gap to prevent label leakage."
    ),
    output: Path = typer.Option(  # noqa: B008
        Path("~/.cache/bloasis/models/lightgbm.pkl"),
        "--output",
        help="Where to save model.pkl (sidecar .json gets written next to it).",
    ),
    db_path: Path = typer.Option(  # noqa: B008
        None,
        "--db-path",
        help="SQLite database path. Defaults to BLOASIS_DB_PATH or ./bloasis.db.",
    ),
    train_start: str = typer.Option(  # noqa: B008
        None,
        "--train-start",
        help="(PR17) Earliest feature_log timestamp to train on, YYYY-MM-DD.",
    ),
    train_end: str = typer.Option(  # noqa: B008
        None,
        "--train-end",
        help="(PR17) Latest feature_log timestamp to train on, YYYY-MM-DD. "
        "Use this to hold out a later evaluation window.",
    ),
) -> None:
    """Train a LightGBM regressor on labeled feature_log rows.

    Reads `feature_log` rows where `feature_version=<N>` AND
    `label_filled_at IS NOT NULL` AND `<label> IS NOT NULL`. Runs purged
    walk-forward CV (default 5 folds, 21-day embargo), reports per-fold
    Information Coefficient, refits on all data, and saves the model
    pickle + metadata sidecar.

    Pre-requisite: `bloasis backtest` runs (populates feature_log) +
    `bloasis label-features` (fills forward returns).
    """
    from bloasis.ml.training import save_model, train_walk_forward
    from bloasis.scoring.features import FEATURE_COLUMNS
    from bloasis.storage.readers import VALID_LABEL_COLUMNS, load_labeled_feature_log

    if label not in VALID_LABEL_COLUMNS:
        raise typer.BadParameter(f"--label must be one of {VALID_LABEL_COLUMNS}, got {label!r}")

    output = output.expanduser()
    engine = get_engine(db_path)
    create_all(engine)

    train_start_dt = _parse_date(train_start)
    train_end_dt = _parse_date(train_end)
    start_arg = (
        datetime(train_start_dt.year, train_start_dt.month, train_start_dt.day, tzinfo=UTC)
        if train_start_dt is not None
        else None
    )
    end_arg = (
        datetime(train_end_dt.year, train_end_dt.month, train_end_dt.day, tzinfo=UTC)
        if train_end_dt is not None
        else None
    )

    df = load_labeled_feature_log(
        engine,
        feature_version=feature_version,
        label_column=label,
        start_date=start_arg,
        end_date=end_arg,
    )
    if df.empty:
        console.print(
            "[red]✗[/red] no labeled rows for "
            f"feature_version={feature_version}, label={label}. "
            "Run `bloasis backtest` then `bloasis label-features` first."
        )
        raise typer.Exit(code=1)

    window_msg = ""
    if start_arg or end_arg:
        window_msg = f" (window {train_start or '...'} .. {train_end or '...'})"
    console.print(
        f"[cyan]loaded[/cyan] {len(df)} labeled rows, "
        f"feature_version={feature_version}, label={label}{window_msg}"
    )

    X = df[list(FEATURE_COLUMNS)]
    y = df[label]
    ts = df["timestamp"]
    result = train_walk_forward(X, y, ts, n_folds=n_folds, embargo_days=embargo_days)

    summary = RichTable(title=f"LightGBM walk-forward CV ({len(result.fold_ics)} folds)")
    summary.add_column("fold", style="cyan")
    summary.add_column("IC", justify="right")
    for i, ic in enumerate(result.fold_ics):
        summary.add_row(str(i), f"{ic:+.4f}")
    summary.add_row("[bold]mean[/bold]", f"[bold]{result.mean_ic:+.4f}[/bold]")
    console.print(summary)

    save_model(
        result,
        output,
        feature_version=feature_version,
        label_name=label,
        extra={
            "n_folds": n_folds,
            "embargo_days": embargo_days,
            "n_labeled_rows": len(df),
        },
    )
    console.print(f"[green]✓[/green] saved model to [bold]{output}[/bold]")
    console.print(f"  metadata sidecar: {output.with_suffix('.json')}")
    console.print(f"  mean IC: [bold]{result.mean_ic:+.4f}[/bold]")


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
    refresh: bool = typer.Option(  # noqa: B008
        False, "--refresh", help="Force re-download of network-backed datasets."
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

    symbols = load_universe(universe_cfg, cfg.data, as_of=as_of_date, refresh=refresh)
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


@fetch_app.command("fixtures")
def fetch_fixtures(
    symbols: list[str] = typer.Option(  # noqa: B008
        ..., "-s", "--symbol", help="Symbol(s); pass -s repeatedly for multiple."
    ),
    start: str = typer.Option(..., "--start", help="YYYY-MM-DD inclusive."),  # noqa: B008
    end: str = typer.Option(..., "--end", help="YYYY-MM-DD inclusive."),  # noqa: B008
    out_dir: Path = typer.Option(  # noqa: B008
        Path("tests/fixtures/ohlcv"),
        "--out-dir",
        help="Output directory for {symbol}.parquet files.",
    ),
) -> None:
    """Snapshot real OHLCV via yfinance into committable parquet fixtures.

    Writes one flat `{out_dir}/{safe_symbol}.parquet` per symbol covering the
    full [start, end] window. `^VIX` -> `IDX_VIX.parquet`. Tests load these
    and slice to the per-test window — no cache-key coupling.

    Network-dependent. Run once locally; commit the result.
    """
    from bloasis.data.fetchers.yfinance_ohlcv import YfOhlcvFetcher

    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date is None or end_date is None:
        raise typer.BadParameter("--start and --end are required (YYYY-MM-DD).")

    out_dir.mkdir(parents=True, exist_ok=True)
    fetcher = YfOhlcvFetcher(cache=None)

    for symbol in symbols:
        df = fetcher.fetch(symbol, start_date, end_date)
        safe = symbol.replace("^", "IDX_")
        path = out_dir / f"{safe}.parquet"
        df.to_parquet(path, index=True)
        console.print(
            f"[green]✓[/green] {symbol}: {len(df)} bars "
            f"({df.index.min().date()} .. {df.index.max().date()}) -> {path}"
        )


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
    from bloasis.backtest import Backtester
    from bloasis.backtest.prefetch import prefetch_backtest_data
    from bloasis.config import config_hash as compute_config_hash
    from bloasis.scoring.extractor import FeatureExtractor
    from bloasis.storage import writers

    if not symbols:
        raise typer.BadParameter("at least one --symbol/-s is required")

    cfg = _load_or_default_config(config_path)
    start_d = _parse_date(start)
    end_d = _parse_date(end)
    if start_d is None or end_d is None:
        raise typer.BadParameter("--start and --end are required (YYYY-MM-DD)")

    try:
        data = prefetch_backtest_data(cfg, symbols, start_d, end_d, console=console)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

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
    session: str = typer.Option(  # noqa: B008
        None,
        "--session",
        help="Persist orders + equity snapshots under this session name. "
        "Idempotent — re-running with the same name resumes the session.",
    ),
) -> None:
    """Submit BUY/SELL signals to Alpaca paper account.

    When `--session NAME` is provided, every order is persisted to
    `paper_orders` and an end-of-run mark-to-market snapshot is appended
    to `paper_equity_snapshots`. Without `--session`, the run is
    fire-and-forget (legacy behavior).
    """
    from bloasis.broker import AlpacaBrokerAdapter
    from bloasis.storage import create_all, writers

    if not symbols or len(symbols) < 2:
        raise typer.BadParameter("at least 2 --symbol/-s entries required")

    cfg = _load_or_default_config(config_path)
    candidates, _last_closes = _build_live_candidates(cfg, symbols, days)
    if not candidates:
        console.print("[yellow]no candidates produced[/yellow]")
        raise typer.Exit(code=1)

    session_id: int | None = None
    if session is not None:
        engine = get_engine()
        create_all(engine)
        session_id = writers.create_paper_session(
            engine,
            name=session,
            config_hash=config_hash(cfg),
            config_json=cfg.model_dump_json(),
        )
        console.print(f"[dim]paper session: {session} (id={session_id})[/dim]")

    broker = AlpacaBrokerAdapter(mode="paper")
    _execute_against_broker(cfg, candidates, broker, label="paper", session_id=session_id)


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
    """Pull OHLCV + scorer-specific data, build candidates ranked by score.

    PR48 — runs the **same scoring pipeline as the backtester** by
    delegating to `prefetch_backtest_data` (so EDGAR / earnings /
    financials prefetch happen exactly as in backtest) and then to
    `Backtester._build_candidates(latest_bar_date, scorer)` which uses
    the shared scorer factory + cross-section scoring. Without this, the
    live path silently fell back to a per-symbol RuleBasedScorer
    regardless of `cfg.scorer.type`, so paper trading never tested the
    actual strategy that backtests measure.

    Returned tuple is `(candidates, last_close_by_symbol)`. Empty list
    when fewer than 2 symbols produced features (cross-section z-score
    requires ≥ 2).
    """
    from bloasis.backtest.engine import Backtester
    from bloasis.backtest.prefetch import prefetch_backtest_data

    end = datetime.now(tz=UTC).date()
    start = end - timedelta(days=days)
    upper_syms = [s.upper() for s in symbols]
    data = prefetch_backtest_data(cfg, upper_syms, start, end)

    if not data.bars:
        return [], {}

    # The latest bar present in the prefetched panel — yfinance can be
    # 1-2 trading days behind for some symbols, so use the max across
    # everything we got.
    latest = max(df.index[-1] for df in data.bars.values())
    latest_date = latest.to_pydatetime().date()

    bt = Backtester(cfg, data)
    scorer = bt._build_scorer(start, end)
    candidates, _fvs = bt._build_candidates(latest_date, scorer)
    last_closes = {c.feature_vector.symbol: c.last_close for c in candidates}
    return list(candidates), last_closes


def _execute_against_broker(
    cfg: StrategyConfig,
    candidates: list[CandidateData],
    broker: BrokerAdapter,
    *,
    label: str,
    session_id: int | None = None,
) -> None:
    """Translate signals into broker orders and print the result table.

    When `session_id` is set (paper trading), every submitted order is
    persisted to `paper_orders` with its broker fill response, and a
    daily equity snapshot is appended to `paper_equity_snapshots`. The
    CLI handler resolves the session via `writers.create_paper_session`
    before calling this helper.
    """
    from bloasis.broker.protocols import BrokerAdapter as _BrokerAdapterAlias
    from bloasis.risk import MarketState, PortfolioState
    from bloasis.signal import HeldPosition
    from bloasis.storage import writers
    from bloasis.strategy.runner import execute_strategy_step

    assert isinstance(broker, _BrokerAdapterAlias), "broker must implement BrokerAdapter"

    # Fetch what we currently hold so SignalGenerator can emit SELL signals
    # for positions whose score has dropped below exit_threshold (or are no
    # longer in the candidate universe entirely). Without this the strategy
    # can never rotate — first day's BUYs sit forever.
    broker_positions = broker.get_positions()
    held = [
        HeldPosition(
            symbol=bp.symbol,
            quantity=bp.quantity,
            avg_cost=bp.avg_cost,
        )
        for bp in broker_positions
    ]

    table = RichTable(title=f"trade {label}")
    table.add_column("symbol", style="cyan")
    table.add_column("side", style="bold")
    table.add_column("qty", justify="right")
    table.add_column("status")
    table.add_column("filled $", justify="right")
    table.add_column("reason")

    engine = get_engine() if session_id is not None else None
    submitted_at = datetime.now(tz=UTC)

    # Build market / portfolio state for the runner. Live has no precomputed
    # VIX series — pass 0.0; risk_evaluator's VIX gate only fires on backtest
    # bars exceeding cfg.risk.max_vix anyway. SPY returns also empty for the
    # live one-shot call → regime overlay defaults to scale=1.0 (no shrink).
    import pandas as pd_mod

    market_state = MarketState(timestamp=submitted_at, vix=0.0)
    portfolio_state = PortfolioState(
        total_value=broker.get_account().equity,
        sector_concentrations={},  # broker doesn't report sector mix
    )
    spy_returns_to_date = pd_mod.Series([], dtype=float)

    step = execute_strategy_step(
        cfg=cfg,
        candidates=candidates,
        held_positions=held,
        market_state=market_state,
        spy_returns_to_date=spy_returns_to_date,
        portfolio_state=portfolio_state,
        signal_date=submitted_at,
        executor=broker,
        prev_buy_set=None,
        label=label,
    )

    for order, result, sig in step.submitted:
        target_capital = 0.0
        entry_hint: float | None = None
        if order.side == "buy" and sig.entry_price is not None:
            entry_hint = float(sig.entry_price)
            # Re-derive target_capital so the persisted row mirrors what the
            # runner sized to; runner uses equity * (size_pct * regime_scale).
            target_capital = order.qty * entry_hint
        if session_id is not None and engine is not None:
            slip = None
            if (
                order.side == "buy"
                and result.filled_avg_price > 0
                and entry_hint is not None
                and entry_hint > 0
            ):
                slip = ((result.filled_avg_price - entry_hint) / entry_hint) * 10_000.0
            writers.write_paper_order(
                engine,
                session_id=session_id,
                ts=submitted_at,
                symbol=order.symbol,
                side=order.side,
                qty=order.qty,
                target_capital=target_capital,
                entry_price_hint=entry_hint,
                filled_qty=result.filled_qty,
                filled_avg_price=result.filled_avg_price,
                broker_status=result.status,
                broker_order_id=order.client_order_id,
                slippage_bps=slip,
                fees=0.0,
                rationale_json=json.dumps({"reason": sig.reason or ""}),
            )
        table.add_row(
            order.symbol,
            order.side,
            f"{order.qty:.4f}",
            result.status,
            f"{result.filled_avg_price * result.filled_qty:.2f}",
            result.reason or sig.reason,
        )

    console.print(table)
    account_after = broker.get_account()
    console.print(
        f"[dim]broker={broker.mode} | equity=${account_after.equity:,.2f} | "
        f"cash=${account_after.cash:,.2f}[/dim]"
    )

    if session_id is not None and engine is not None:
        # End-of-run mark-to-market: account state already reflects the
        # orders we just placed (broker / sim mutated it inline).
        positions_value = max(0.0, account_after.equity - account_after.cash)
        writers.snapshot_paper_equity(
            engine,
            session_id=session_id,
            ts=submitted_at,
            cash=account_after.cash,
            positions_value=positions_value,
            equity=account_after.equity,
            n_positions=len(step.submitted),
        )


# ---------------------------------------------------------------------------
# Grid runner (PR21) — combinatorial backtest matrix sharing prefetch cost
# ---------------------------------------------------------------------------


def _resolve_universe_symbols(
    universe: str | None, symbols: list[str] | None, cache_dir: Path
) -> list[str]:
    """Resolve a grid spec's universe / symbols into a concrete ticker list."""
    if symbols:
        return [s.upper() for s in symbols]
    if not universe:
        raise typer.BadParameter("grid spec must provide 'universe' or 'symbols'")
    if universe == "sp500":
        from bloasis.data.universe.sp500 import list_sp500

        return list_sp500(cache_dir=cache_dir)
    if universe.startswith("sp500_at:"):
        from bloasis.data.universe.sp500_historical import list_sp500_at

        as_of = date.fromisoformat(universe.split(":", 1)[1])
        return list_sp500_at(as_of, cache_dir=cache_dir)
    if universe == "russell2000":
        from bloasis.data.universe.russell2000 import list_russell2000

        return list_russell2000(cache_dir=cache_dir)
    raise typer.BadParameter(
        f"unknown universe '{universe}'. Use sp500, sp500_at:YYYY-MM-DD, russell2000, "
        "or pass explicit 'symbols' in the spec."
    )


@grid_app.command("run")
def grid_run(
    spec_path: Path = typer.Argument(  # noqa: B008
        ..., exists=False, help="Path to grid axes YAML."
    ),
) -> None:
    """Execute every combination in `spec_path`, sharing one prefetch."""
    from bloasis.backtest.grid import (
        expand_combinations,
        load_grid_spec,
        run_grid,
    )
    from bloasis.backtest.prefetch import prefetch_backtest_data
    from bloasis.config import config_hash as compute_config_hash
    from bloasis.scoring.extractor import FeatureExtractor
    from bloasis.storage import writers

    spec = load_grid_spec(spec_path)
    base_cfg = load_config(spec.base_config_path)

    start_d = (
        spec.walk_forward["start"]
        if isinstance(spec.walk_forward["start"], date)
        else date.fromisoformat(str(spec.walk_forward["start"]))
    )
    end_d = (
        spec.walk_forward["end"]
        if isinstance(spec.walk_forward["end"], date)
        else date.fromisoformat(str(spec.walk_forward["end"]))
    )

    symbols = _resolve_universe_symbols(spec.universe, spec.symbols, base_cfg.data.cache_dir)

    # Union of scorer types across every combination — so prefetch fans out
    # exactly the data sources any combo will consume.
    from bloasis.backtest.grid import apply_overrides as _apply

    combos = expand_combinations(spec)
    scorer_types = {_apply(base_cfg, c).scorer.type for c in combos}

    console.print(
        f"[cyan]grid {spec.name}: {len(combos)} combinations across "
        f"{len(symbols)} symbols, scorers {sorted(scorer_types)}[/cyan]"
    )

    try:
        data = prefetch_backtest_data(
            base_cfg,
            symbols,
            start_d,
            end_d,
            scorer_types=scorer_types,
            console=console,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    engine = get_engine()
    create_all(engine)

    def _persist(gr: object) -> None:
        # late import to avoid circular ref via bloasis.backtest.grid
        from bloasis.backtest.grid import GridRunResult

        assert isinstance(gr, GridRunResult)
        cfg_hash = compute_config_hash(gr.config)
        run_id = writers.create_backtest_run(
            engine,
            name=gr.run_name,
            config_hash=cfg_hash,
            config_json=gr.config.model_dump_json(),
            scorer_type=gr.config.scorer.type,
            feature_version=FeatureExtractor.VERSION,
            start_date=datetime(start_d.year, start_d.month, start_d.day, tzinfo=UTC),
            end_date=datetime(end_d.year, end_d.month, end_d.day, tzinfo=UTC),
            initial_capital=gr.config.execution.initial_capital,
        )
        gr.run_id = run_id
        if gr.error is not None:
            writers.fail_backtest_run(engine, run_id, gr.error.splitlines()[0])
        elif gr.result is not None:
            from dataclasses import replace

            finalized = replace(gr.result, config_hash=cfg_hash, run_id=run_id)
            writers.finalize_backtest_run(engine, run_id, finalized)
            gr.result = finalized

    def _progress(idx: int, total: int, gr: object) -> None:
        from bloasis.backtest.grid import GridRunResult

        assert isinstance(gr, GridRunResult)
        if gr.error:
            console.print(f"[red]  [{idx}/{total}] {gr.run_name} — FAILED[/red]")
            # Surface the traceback to stderr so users see *why* a combo
            # failed instead of having to dig through DB or guess.
            sys.stderr.write(f"\n--- traceback for {gr.run_name} ---\n{gr.error}\n")
            sys.stderr.flush()
        else:
            r = gr.result
            sharpe = f"{r.median_sharpe_vs_spy:.2f}" if r else "—"
            alpha = f"{r.median_alpha_annualized:+.3f}" if r else "—"
            gate = "PASS" if r and r.passed_acceptance else "fail"
            console.print(f"  [{idx}/{total}] {gr.run_name} — sharpe {sharpe}, α {alpha} ({gate})")

    results = run_grid(
        spec,
        base_cfg,
        data,
        persist=_persist,
        on_progress=_progress,
    )

    # n_ok: backtest produced a result AND persistence didn't error after.
    # n_pass: result passed acceptance AND no error path was hit (so we don't
    # double-count a combo that succeeded the backtest but failed persistence).
    n_ok = sum(1 for r in results if r.error is None and r.result is not None)
    n_pass = sum(
        1
        for r in results
        if r.error is None and r.result is not None and r.result.passed_acceptance
    )
    console.print(
        f"[green]grid {spec.name}: {n_ok}/{len(results)} completed, "
        f"{n_pass} passed acceptance[/green]"
    )


class _GridSortKey(StrEnum):
    """Allowed sort keys for `bloasis grid show --sort`.

    `sharpe` is `backtest_runs.sharpe` (avg fold sharpe, raw — not vs SPY).
    `alpha` is `alpha_vs_spy` (median alpha annualized).
    """

    sharpe = "sharpe"
    alpha = "alpha"


@grid_app.command("show")
def grid_show(
    grid_name: str = typer.Argument(...),  # noqa: B008
    limit: int = typer.Option(50, "--limit", min=1, max=500),  # noqa: B008
    sort: _GridSortKey = typer.Option(  # noqa: B008
        _GridSortKey.sharpe,
        "--sort",
        case_sensitive=False,
        help="Sort key: sharpe (default) or alpha.",
    ),
) -> None:
    """Render a leaderboard of all runs whose name starts with `<grid_name>#`."""
    from sqlalchemy import select

    from bloasis.storage import backtest_runs as br_table

    sort_col = br_table.c.alpha_vs_spy if sort is _GridSortKey.alpha else br_table.c.sharpe

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                br_table.c.run_id,
                br_table.c.name,
                br_table.c.alpha_vs_spy,
                br_table.c.sharpe,
                br_table.c.max_drawdown,
                br_table.c.passed_acceptance,
                br_table.c.status,
                br_table.c.n_trades,
            )
            .where(br_table.c.name.like(f"{grid_name}#%"))
            .order_by(sort_col.desc().nullslast())
            .limit(limit)
        ).fetchall()

    if not rows:
        console.print(f"[red]no runs found for grid '{grid_name}'[/red]")
        raise typer.Exit(code=1)

    table = RichTable(title=f"grid {grid_name} — top {len(rows)} by {sort.value}")
    table.add_column("run_id", justify="right")
    table.add_column("combo")
    table.add_column("sharpe", justify="right")
    table.add_column("alpha", justify="right")
    table.add_column("max_dd", justify="right")
    table.add_column("trades", justify="right")
    table.add_column("gate")

    best_idx: int | None = None
    for i, r in enumerate(rows):
        if r.passed_acceptance and r.sharpe is not None:
            best_idx = i
            break

    for i, r in enumerate(rows):
        combo = r.name.split("#", 1)[1] if "#" in (r.name or "") else (r.name or "")
        gate = "PASS" if r.passed_acceptance else (r.status or "fail")
        marker = "★ " if i == best_idx else ""
        table.add_row(
            str(r.run_id),
            f"{marker}{combo}",
            f"{r.sharpe:.3f}" if r.sharpe is not None else "—",
            f"{r.alpha_vs_spy:+.3f}" if r.alpha_vs_spy is not None else "—",
            f"{r.max_drawdown:.3f}" if r.max_drawdown is not None else "—",
            str(r.n_trades) if r.n_trades is not None else "—",
            gate,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Paper trading inspection (PR47)
# ---------------------------------------------------------------------------


def _format_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


@paper_app.command("sessions")
def paper_sessions_list() -> None:
    """List every paper session with order/snapshot counts and equity range."""
    from sqlalchemy import func, select

    from bloasis.storage import paper_equity_snapshots as eq_table
    from bloasis.storage import paper_orders as ord_table
    from bloasis.storage import paper_sessions as sess_table

    engine = get_engine()
    with engine.connect() as conn:
        sessions = conn.execute(
            select(sess_table).order_by(sess_table.c.started_at.desc())
        ).fetchall()

        if not sessions:
            console.print("[yellow]no paper sessions found[/yellow]")
            return

        order_counts: dict[int, int] = {
            int(r[0]): int(r[1])
            for r in conn.execute(
                select(ord_table.c.session_id, func.count()).group_by(ord_table.c.session_id)
            ).fetchall()
        }
        snap_min: dict[int, float] = {
            int(r[0]): float(r[1])
            for r in conn.execute(
                select(eq_table.c.session_id, func.min(eq_table.c.equity)).group_by(
                    eq_table.c.session_id
                )
            ).fetchall()
        }
        snap_max: dict[int, float] = {
            int(r[0]): float(r[1])
            for r in conn.execute(
                select(eq_table.c.session_id, func.max(eq_table.c.equity)).group_by(
                    eq_table.c.session_id
                )
            ).fetchall()
        }

    table = RichTable(title=f"paper sessions — {len(sessions)} total")
    table.add_column("id", justify="right")
    table.add_column("name", style="cyan")
    table.add_column("status")
    table.add_column("orders", justify="right")
    table.add_column("equity range", justify="right")
    table.add_column("started")

    for s in sessions:
        sid = s.session_id
        emin = snap_min.get(sid)
        emax = snap_max.get(sid)
        eq_str = f"${emin:,.0f} → ${emax:,.0f}" if emin is not None and emax is not None else "—"
        table.add_row(
            str(sid),
            s.name,
            s.status,
            str(order_counts.get(sid, 0)),
            eq_str,
            s.started_at.strftime("%Y-%m-%d") if s.started_at else "—",
        )
    console.print(table)


def _resolve_session_id(name: str) -> int:
    """Look up a session by name; raise typer.Exit on miss."""
    from sqlalchemy import select

    from bloasis.storage import paper_sessions as sess_table

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            select(sess_table.c.session_id).where(sess_table.c.name == name)
        ).fetchone()
    if row is None:
        console.print(f"[red]session '{name}' not found[/red]")
        raise typer.Exit(code=1)
    return int(row.session_id)


@paper_app.command("show")
def paper_show(
    session_name: str = typer.Argument(...),  # noqa: B008
) -> None:
    """Render session detail: equity curve summary, order count, total return."""
    from sqlalchemy import func, select

    from bloasis.storage import paper_equity_snapshots as eq_table
    from bloasis.storage import paper_orders as ord_table

    sid = _resolve_session_id(session_name)
    engine = get_engine()
    with engine.connect() as conn:
        snaps = conn.execute(
            select(eq_table.c.ts, eq_table.c.equity)
            .where(eq_table.c.session_id == sid)
            .order_by(eq_table.c.ts)
        ).fetchall()
        n_orders = conn.execute(
            select(func.count()).where(ord_table.c.session_id == sid)
        ).scalar_one()

    table = RichTable(title=f"paper session — {session_name}")
    table.add_column("metric", style="cyan")
    table.add_column("value", justify="right")

    if snaps:
        first = snaps[0].equity
        last = snaps[-1].equity
        ret = (last - first) / first if first > 0 else 0.0
        max_eq = max(s.equity for s in snaps)
        running_max = first
        max_dd = 0.0
        for s in snaps:
            running_max = max(running_max, s.equity)
            dd = (s.equity - running_max) / running_max if running_max > 0 else 0.0
            max_dd = min(max_dd, dd)
        table.add_row("snapshots", str(len(snaps)))
        table.add_row("equity start", f"${first:,.2f}")
        table.add_row("equity end", f"${last:,.2f}")
        table.add_row("equity peak", f"${max_eq:,.2f}")
        table.add_row("total return", _format_pct(ret))
        table.add_row("max drawdown", _format_pct(max_dd))
    else:
        table.add_row("snapshots", "0")

    table.add_row("orders submitted", str(n_orders))
    console.print(table)


@paper_app.command("friction")
def paper_friction(
    session_name: str = typer.Argument(...),  # noqa: B008
) -> None:
    """Median/p25/p75 slippage in bps for filled BUY orders in this session."""
    import statistics

    from sqlalchemy import select

    from bloasis.storage import paper_orders as ord_table

    sid = _resolve_session_id(session_name)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            select(ord_table.c.slippage_bps, ord_table.c.symbol).where(
                ord_table.c.session_id == sid,
                ord_table.c.broker_status == "filled",
                ord_table.c.slippage_bps.is_not(None),
            )
        ).fetchall()

    table = RichTable(title=f"paper friction — {session_name}")
    table.add_column("metric", style="cyan")
    table.add_column("value", justify="right")

    if not rows:
        console.print(f"[yellow]no filled orders with slippage data in '{session_name}'[/yellow]")
        return

    bps_values = [float(r.slippage_bps) for r in rows]
    bps_sorted = sorted(bps_values)
    n = len(bps_sorted)
    median = statistics.median(bps_sorted)
    p25 = bps_sorted[max(0, n // 4)] if n > 1 else bps_sorted[0]
    p75 = bps_sorted[min(n - 1, (3 * n) // 4)] if n > 1 else bps_sorted[0]

    table.add_row("filled orders", str(n))
    table.add_row("median slippage", f"{median:.1f} bps")
    table.add_row("p25 slippage", f"{p25:.1f} bps")
    table.add_row("p75 slippage", f"{p75:.1f} bps")
    table.add_row("max slippage", f"{max(bps_values):.1f} bps")
    console.print(table)


@paper_app.command("close")
def paper_close(
    session_name: str = typer.Argument(...),  # noqa: B008
) -> None:
    """Mark a paper session as closed (idempotent — safe to re-run)."""
    from bloasis.storage import writers

    sid = _resolve_session_id(session_name)
    engine = get_engine()
    writers.close_paper_session(engine, session_id=sid)
    console.print(f"[green]✓[/green] session '{session_name}' (id={sid}) closed")


if __name__ == "__main__":
    app()
