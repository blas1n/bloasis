"""BLOASIS CLI entry point.

Commands implemented in PR1:
  - bloasis version
  - bloasis init-db [--db-path PATH]
  - bloasis config show <yaml> [--set k.v=val]...

Commands landing in later PRs (PR2-PR6): fetch, universe, features, analyze,
backtest, runs, trade. They are not stubbed here to avoid creating the
illusion of working features.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table as RichTable

from bloasis import __version__
from bloasis.config import config_hash, load_config
from bloasis.storage import create_all, get_engine, metadata

app = typer.Typer(
    name="bloasis",
    help="Deterministic + ML trading research and execution CLI.",
    no_args_is_help=True,
    add_completion=False,
)

config_app = typer.Typer(name="config", help="Inspect and validate strategy configs.")
app.add_typer(config_app, name="config")

console = Console()


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


if __name__ == "__main__":
    app()
