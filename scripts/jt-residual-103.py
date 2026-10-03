"""Pre-registered candidate under research protocol v2 (#103): JT residual momentum.

Same portfolio construction as `edgar-rolling2` (2% positions, monthly
rebalance, no sector cap); only the signal changes to residual 12-1 momentum
(Blitz-Hanauer-Vidojevic). Two arms: without and with the de-risk-only
volatility-target overlay (Barroso-Santa-Clara).

Stages run in order and are gated mechanically by the pre-registered rule:
development window -> fragility -> holdout H1 and H2. An arm that fails a
stage is not run on the next one.

Pre-registration, decision rule and results:
``docs/research/JT_Residual_2026-10-03.md``.

Usage (never against the shared cache -- clone it first)::

    uv run python scripts/jt-residual-103.py \
        --cache-dir /tmp/bloasis-cache-clone --out /tmp/jt-103.json
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from rich.console import Console

BASE_CONFIG = Path("configs/edgar-rolling2.yaml")
TRAIN_DAYS, TEST_DAYS, STEP_DAYS = 180, 120, 120

#: name -> (start, end, universe as-of)
WINDOWS = {
    "dev": (date(2022, 1, 1), date(2024, 10, 17), date(2024, 12, 31)),
    "H1": (date(2013, 1, 1), date(2017, 12, 31), date(2017, 12, 31)),
    "H2": (date(2018, 1, 1), date(2021, 12, 31), date(2021, 12, 31)),
}

SIGNAL = {
    "scorer.type": "jt_momentum",
    "scorer.jt_residual": True,
    "scorer.jt_top_pct": 0.10,
}
ARMS: dict[str, dict[str, Any]] = {
    "J0 residual": {**SIGNAL, "regime_overlay.enabled": False},
    "J1 residual + vol target": {
        **SIGNAL,
        "regime_overlay.enabled": True,
        "regime_overlay.sigma_target": 0.12,
        "regime_overlay.bear_scale": 0.5,
        "regime_overlay.scale_clip": [0.0, 1.0],
    },
}

# Gates (docs/mission.md paper gate on dev; protocol v2 holdout gate).
DEV = {"folds": 7, "alpha": -0.005, "sharpe": 0.7, "dd": 0.85}
HOLD = {"folds": 5, "alpha": 0.0, "dd": 0.85}
FRAGILITY_SEEDS = (1, 2, 3)
FRAGILITY_DROP = 0.05


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    from bloasis.backtest.engine import Backtester
    from bloasis.backtest.grid import apply_overrides
    from bloasis.backtest.prefetch import prefetch_backtest_data
    from bloasis.config import load_config
    from bloasis.data.universe.sp500_historical import list_sp500_at

    console = Console()
    cache = args.cache_dir.expanduser().resolve()
    base = apply_overrides(
        load_config(BASE_CONFIG),
        {"data.cache_dir": str(cache), "data.ohlcv_cache_max_age_hours": 24 * 3650},
    )
    report: dict[str, Any] = {"arms": {}}

    def save() -> None:
        args.out.write_text(json.dumps(report, indent=2, default=str))

    panels: dict[str, Any] = {}

    def panel(window: str) -> Any:
        if window not in panels:
            start, end, as_of = WINDOWS[window]
            syms = list_sp500_at(as_of, cache_dir=cache)
            cfg0 = apply_overrides(base, SIGNAL)
            panels[window] = prefetch_backtest_data(
                cfg0, syms, start, end, scorer_types={"jt_momentum"}, console=console
            )
            report.setdefault("coverage", {})[window] = {
                "universe": len(syms),
                "with_bars": len(panels[window].bars),
            }
        return panels[window]

    def run(arm: str, window: str, data: Any) -> dict[str, Any]:
        start, end, _ = WINDOWS[window]
        cfg = apply_overrides(base, ARMS[arm])
        r = Backtester(cfg, data).run(
            start, end, train_days=TRAIN_DAYS, test_days=TEST_DAYS, step_days=STEP_DAYS
        )
        return {
            "folds": r.n_folds,
            "alpha": r.median_alpha_annualized,
            "sharpe": r.median_sharpe_vs_spy,
            "dd": r.median_max_dd_ratio_to_spy,
            "trades": r.n_trades_total,
            "fold_alpha": [f.annualized_alpha for f in r.fold_results],
        }

    for arm in ARMS:
        rec: dict[str, Any] = {}
        report["arms"][arm] = rec

        # Stage 1 -- development window, paper gate.
        dev = run(arm, "dev", panel("dev"))
        dev["pass"] = (
            dev["folds"] >= DEV["folds"]
            and dev["alpha"] >= DEV["alpha"]
            and dev["sharpe"] >= DEV["sharpe"]
            and dev["dd"] <= DEV["dd"]
        )
        rec["dev"] = dev
        console.print(f"[cyan]{arm} dev: {dev}[/cyan]")
        save()
        if not dev["pass"]:
            rec["stopped_at"] = "dev"
            continue

        # Stage 2 -- fragility: drop 5% of the universe at random, 3 seeds.
        full = panel("dev")
        alphas = []
        for seed in FRAGILITY_SEEDS:
            rng = random.Random(seed)
            keep = [s for s in full.symbols if rng.random() >= FRAGILITY_DROP]
            sub = replace(full, symbols=keep, bars={s: full.bars[s] for s in keep})
            alphas.append(run(arm, "dev", sub)["alpha"])
        frag_pass = all(a > 0 for a in alphas) and statistics.median(alphas) >= 0.5 * dev["alpha"]
        rec["fragility"] = {"alphas": alphas, "pass": frag_pass}
        console.print(f"[cyan]{arm} fragility: {rec['fragility']}[/cyan]")
        save()
        if not frag_pass:
            rec["stopped_at"] = "fragility"
            continue

        # Stage 3 -- holdouts, each once.
        for window in ("H1", "H2"):
            h = run(arm, window, panel(window))
            h["pass"] = (
                h["folds"] >= HOLD["folds"] and h["alpha"] > HOLD["alpha"] and h["dd"] <= HOLD["dd"]
            )
            rec[window] = h
            console.print(f"[cyan]{arm} {window}: {h}[/cyan]")
            save()
        rec["stopped_at"] = None if rec["H1"]["pass"] and rec["H2"]["pass"] else "holdout"
        save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
