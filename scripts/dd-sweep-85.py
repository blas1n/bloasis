"""Pre-registered DD-reduction sweep for issue #85.

`configs/edgar-rolling2.yaml` fails the Phase 1 exit gate on one criterion
only: median max-DD ratio to SPY 0.873 against a 0.85 bar (sharpe 1.013 and
alpha +3.74%/yr pass). This script measures whether the regime overlay or
position sizing / concentration can pull DD under the bar *without* losing
sharpe >= 1.0 and alpha >= -0.5%.

Pre-registration, decision rule and results:
``docs/research/DD_Reduction_Sweep_2026-10-01.md``.

Why a script instead of two `bloasis grid run` invocations: every arm must
see byte-identical inputs. One process does one prefetch and hands the same
``BacktestData`` panel to all arms, so no cache expiry or yfinance
re-adjustment can drift between blocks. Nothing is written to the run DB.

Usage (never against the shared cache -- clone it first)::

    uv run python scripts/dd-sweep-85.py \
        --cache-dir /tmp/bloasis-cache-clone \
        --out /tmp/dd-sweep-85.json
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from rich.console import Console

# Canonical protocol -- configs/grids/pr21-edgar-rolling.yaml.
START = date(2022, 1, 1)
END = date(2024, 10, 17)
TRAIN_DAYS = 180
TEST_DAYS = 120
STEP_DAYS = 120
UNIVERSE_AS_OF = date(2024, 12, 31)

BASE_CONFIG = Path("configs/edgar-rolling2.yaml")

# Gate (docs/mission.md, live-trading entry).
DD_BAR = 0.85
SHARPE_BAR = 1.0
ALPHA_BAR = -0.005
MIN_FOLDS = 5

#: Pre-registered arms. Block A varies the regime overlay only; block B
#: varies position cap and sector concentration only. `max_single_order_pct`
#: tracks the position cap because the effective size is
#: ``min(position_size_max_pct, max_single_order_pct)`` -- sweeping the two
#: independently would only re-measure the smaller of them.
ARMS: list[tuple[str, dict[str, Any]]] = []

# --- Block 0: control (identical to the live config) -----------------------
ARMS.append(("baseline", {}))

# --- Block A: regime overlay (2 x 2 x 2 = 8) ------------------------------
for sigma in (0.08, 0.12):
    for bear in (0.25, 0.50):
        for clip in ((0.0, 1.0), (0.0, 1.5)):
            ARMS.append(
                (
                    f"A/overlay sigma={sigma} bear={bear} clip={clip[1]}",
                    {
                        "regime_overlay.enabled": True,
                        "regime_overlay.sigma_target": sigma,
                        "regime_overlay.bear_scale": bear,
                        "regime_overlay.scale_clip": list(clip),
                    },
                )
            )

# --- Block B: sizing / concentration (3 x 3 = 9, one of which is baseline) -
for pos in (0.01, 0.02, 0.03):
    for sector in (0.20, 0.40, 1.0):
        if pos == 0.02 and sector == 1.0:
            continue  # == baseline; measured once in block 0
        ARMS.append(
            (
                f"B/size pos={pos} sector={sector}",
                {
                    "signal.position_size_max_pct": pos,
                    "risk.max_single_order_pct": pos,
                    "risk.max_sector_concentration": sector,
                },
            )
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--cache-dir",
        required=True,
        type=Path,
        help="Cloned ~/.cache/bloasis. Never point this at the shared cache.",
    )
    ap.add_argument("--out", required=True, type=Path, help="JSON results path.")
    ap.add_argument(
        "--ohlcv-max-age-hours",
        type=int,
        default=24 * 3650,
        help=(
            "Serve cached OHLCV parquet regardless of age (default). Keeps every "
            "arm on the same prices and keeps the sweep off the network."
        ),
    )
    ap.add_argument(
        "--only",
        default=None,
        help="Substring filter on arm name -- for a single-arm control run.",
    )
    args = ap.parse_args()

    from bloasis.backtest.engine import Backtester
    from bloasis.backtest.grid import apply_overrides
    from bloasis.backtest.prefetch import prefetch_backtest_data
    from bloasis.backtest.walk_forward import generate_folds
    from bloasis.config import load_config
    from bloasis.data.universe.sp500_historical import list_sp500_at

    console = Console()

    cache_dir = args.cache_dir.expanduser().resolve()
    base = load_config(BASE_CONFIG)
    base = apply_overrides(
        base,
        {
            "data.cache_dir": str(cache_dir),
            "data.ohlcv_cache_max_age_hours": args.ohlcv_max_age_hours,
        },
    )

    n_folds_expected = len(list(generate_folds(START, END, TRAIN_DAYS, TEST_DAYS, STEP_DAYS)))
    console.print(
        f"[cyan]protocol: {START}..{END} {TRAIN_DAYS}/{TEST_DAYS}/{STEP_DAYS} "
        f"-> {n_folds_expected} folds[/cyan]"
    )
    if n_folds_expected != 7:
        console.print("[red]protocol does not yield 7 folds -- aborting[/red]")
        return 2

    symbols = list_sp500_at(UNIVERSE_AS_OF, cache_dir=cache_dir)
    console.print(f"[cyan]universe sp500_at:{UNIVERSE_AS_OF}: {len(symbols)} symbols[/cyan]")

    data = prefetch_backtest_data(
        base,
        symbols,
        START,
        END,
        scorer_types={base.scorer.type},
        console=console,
    )
    console.print(
        f"[green]prefetch done: {len(data.symbols)} symbols with bars, "
        f"{len(data.risk_factors_history)} with 10-K history[/green]"
    )

    arms = [a for a in ARMS if args.only is None or args.only in a[0]]
    rows: list[dict[str, Any]] = []
    for i, (name, overrides) in enumerate(arms, start=1):
        cfg = apply_overrides(base, overrides)
        result = Backtester(cfg, data).run(
            START,
            END,
            train_days=TRAIN_DAYS,
            test_days=TEST_DAYS,
            step_days=STEP_DAYS,
        )
        dd = result.median_max_dd_ratio_to_spy
        sharpe = result.median_sharpe_vs_spy
        alpha = result.median_alpha_annualized
        qualifies = (
            result.n_folds >= MIN_FOLDS
            and dd <= DD_BAR
            and sharpe >= SHARPE_BAR
            and alpha >= ALPHA_BAR
        )
        row = {
            "arm": name,
            "overrides": overrides,
            "folds": result.n_folds,
            "dd_ratio": dd,
            "sharpe_vs_spy": sharpe,
            "alpha_annualized": alpha,
            "trades": result.n_trades_total,
            "total_return": result.median_total_return,
            "spy_total_return": result.median_spy_total_return,
            "qualifies": qualifies,
            "fold_dd_ratios": [f.max_dd_ratio_to_spy for f in result.fold_results],
        }
        rows.append(row)
        console.print(
            f"  [{i}/{len(arms)}] {name} -- folds {result.n_folds}, DD {dd:.3f}, "
            f"sharpe {sharpe:.3f}, alpha {alpha:+.4f}, trades {result.n_trades_total}"
            f" {'[green]QUALIFIES[/green]' if qualifies else ''}"
        )
        args.out.write_text(json.dumps(rows, indent=2, default=str))

    n_qual = sum(1 for r in rows if r["qualifies"])
    console.print(f"[green]{len(rows)} arms run, {n_qual} qualify -> {args.out}[/green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
