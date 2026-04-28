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
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table as RichTable

from bloasis import __version__
from bloasis.config import StrategyConfig, config_hash, load_config
from bloasis.storage import create_all, get_engine, metadata

app = typer.Typer(
    name="bloasis",
    help="Deterministic + ML trading research and execution CLI.",
    no_args_is_help=True,
    add_completion=False,
)

config_app = typer.Typer(name="config", help="Inspect and validate strategy configs.")
universe_app = typer.Typer(name="universe", help="Show universe membership.")
fetch_app = typer.Typer(name="fetch", help="Fetch and cache market data.")
app.add_typer(config_app, name="config")
app.add_typer(universe_app, name="universe")
app.add_typer(fetch_app, name="fetch")

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
        None, "--config", "-c"
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
        None, "--config", "-c"
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
        None, "--config", "-c"
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


if __name__ == "__main__":
    app()
