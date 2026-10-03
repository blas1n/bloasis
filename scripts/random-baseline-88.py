"""Pre-registered no-skill baseline for issue #88.

Runs the `edgar-rolling2` portfolio frame (2% positions, top-10% selection,
monthly rebalance, ATR stops / take-profits, no sector cap) with the signal
replaced by deterministic random numbers, and reports the distribution of
median DD ratio and alpha across seeds. It tells whether the 0.85 DD bar in
the paper gate asks for skill, or whether it is out of reach of the frame
itself.

Two random signals:

- ``R1``: a fresh random rank every rebalance (no persistence).
- ``R2``: one random rank per symbol per calendar year (persists like a
  signal that moves with annual 10-Ks).

Pre-registration, decision rule and results:
``docs/research/Random_Baseline_2026-10-03.md``.

Usage (never against the shared cache -- clone it first)::

    uv run python scripts/random-baseline-88.py \
        --cache-dir /tmp/bloasis-cache-clone --out /tmp/random-88.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import date
from pathlib import Path
from typing import Any

from rich.console import Console

BASE_CONFIG = Path("configs/edgar-rolling2.yaml")
TRAIN_DAYS, TEST_DAYS, STEP_DAYS = 180, 120, 120
WINDOWS = {
    "dev": (date(2022, 1, 1), date(2024, 10, 17), date(2024, 12, 31)),
    "H2": (date(2018, 1, 1), date(2021, 12, 31), date(2021, 12, 31)),
}
SEEDS = tuple(range(1, 21))
BAR = 0.85


def _uniform(*parts: object) -> float:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _quantiles(xs: list[float]) -> dict[str, float]:
    q = statistics.quantiles(xs, n=10)
    return {"p10": q[0], "p50": statistics.median(xs), "p90": q[-1]}


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
    from bloasis.scoring.features import FeatureVector
    from bloasis.scoring.scorer import JTMomentumScorer

    def make_scorer(kind: str, seed: int) -> type:
        class RandomScorer(JTMomentumScorer):
            """JT's top-pct selection with a random signal in place of momentum."""

            def __init__(self, cfg: Any) -> None:
                super().__init__(cfg, top_pct=0.10)

            def _signal(self, fv: FeatureVector) -> float:
                ts = fv.timestamp
                period = ts.year if kind == "R2" else ts.date().isoformat()
                return _uniform(kind, seed, fv.symbol, period)

        return RandomScorer

    console = Console()
    cache = args.cache_dir.expanduser().resolve()
    cfg = apply_overrides(
        load_config(BASE_CONFIG),
        {"data.cache_dir": str(cache), "data.ohlcv_cache_max_age_hours": 24 * 3650},
    )
    report: dict[str, Any] = {"runs": {}, "summary": {}}
    for window, (start, end, as_of) in WINDOWS.items():
        syms = list_sp500_at(as_of, cache_dir=cache)
        # Prices only: prefetch with a price-only scorer type, so no 10-K work.
        price_cfg = apply_overrides(cfg, {"scorer.type": "jt_momentum"})
        data = prefetch_backtest_data(
            price_cfg, syms, start, end, scorer_types={"jt_momentum"}, console=console
        )
        report.setdefault("coverage", {})[window] = {
            "universe": len(syms),
            "with_bars": len(data.bars),
        }
        for kind in ("R1", "R2"):
            rows = []
            for seed in SEEDS:
                r = Backtester(price_cfg, data, scorer_factory=make_scorer(kind, seed)).run(
                    start, end, train_days=TRAIN_DAYS, test_days=TEST_DAYS, step_days=STEP_DAYS
                )
                rows.append(
                    {
                        "seed": seed,
                        "folds": r.n_folds,
                        "dd": r.median_max_dd_ratio_to_spy,
                        "alpha": r.median_alpha_annualized,
                        "sharpe": r.median_sharpe_vs_spy,
                        "trades": r.n_trades_total,
                    }
                )
                console.print(f"[cyan]{window} {kind} seed {seed}: {rows[-1]}[/cyan]")
                report["runs"][f"{window}/{kind}"] = rows
                args.out.write_text(json.dumps(report, indent=2, default=str))
            dds = [x["dd"] for x in rows]
            report["summary"][f"{window}/{kind}"] = {
                "dd": _quantiles(dds),
                "alpha": _quantiles([x["alpha"] for x in rows]),
                "share_dd_at_or_below_bar": sum(1 for d in dds if d <= BAR) / len(dds),
            }
            args.out.write_text(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
