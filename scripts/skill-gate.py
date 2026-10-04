"""Skill-relative paper gate (#88): a candidate vs random books in its own frame.

Runs the candidate config on one walk-forward window, then the same config
with its signal replaced by a seeded random rank (R1: redrawn every
rebalance; R2: redrawn once per symbol per calendar year), 20 seeds each.
`bloasis.backtest.skill_gate.skill_gate` picks the random kind with the
nearest turnover and passes the candidate only if its DD ratio beats that
kind's p10 and its alpha beats its p90.

Background: ``docs/research/Random_Baseline_2026-10-03.md``. Gate text:
``docs/mission.md`` (Paper-trading gate).

Usage (never against the shared cache -- clone it first)::

    uv run python scripts/skill-gate.py --config configs/edgar-rolling2.yaml \
        --window dev --cache-dir /tmp/bloasis-cache-clone --out /tmp/gate.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from typing import Any

from rich.console import Console

TRAIN_DAYS, TEST_DAYS, STEP_DAYS = 180, 120, 120
#: name -> (start, end, universe as-of); the windows docs/mission.md names.
WINDOWS = {
    "dev": (date(2022, 1, 1), date(2024, 10, 17), date(2024, 12, 31)),
    "H1": (date(2013, 1, 1), date(2017, 12, 31), date(2017, 12, 31)),
    "H2": (date(2018, 1, 1), date(2021, 12, 31), date(2021, 12, 31)),
}
SEEDS = tuple(range(1, 21))


def _uniform(*parts: object) -> float:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--window", required=True, choices=sorted(WINDOWS))
    ap.add_argument("--cache-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    from bloasis.backtest.engine import Backtester
    from bloasis.backtest.grid import apply_overrides
    from bloasis.backtest.prefetch import prefetch_backtest_data
    from bloasis.backtest.skill_gate import RunMetrics, skill_gate
    from bloasis.config import load_config
    from bloasis.data.universe.sp500_historical import list_sp500_at
    from bloasis.scoring.features import FeatureVector
    from bloasis.scoring.scorer import JTMomentumScorer

    def random_scorer(kind: str, seed: int, top_pct: float) -> type:
        class RandomScorer(JTMomentumScorer):
            """Top-pct selection on a seeded random rank instead of a signal."""

            def __init__(self, cfg: Any) -> None:
                super().__init__(cfg, top_pct=top_pct)

            def _signal(self, fv: FeatureVector) -> float:
                period = fv.timestamp.year if kind == "R2" else fv.timestamp.date().isoformat()
                return _uniform(kind, seed, fv.symbol, period)

        return RandomScorer

    console = Console()
    cache = args.cache_dir.expanduser().resolve()
    cfg = apply_overrides(
        load_config(args.config),
        {"data.cache_dir": str(cache), "data.ohlcv_cache_max_age_hours": 24 * 3650},
    )
    start, end, as_of = WINDOWS[args.window]
    symbols = list_sp500_at(as_of, cache_dir=cache)
    data = prefetch_backtest_data(
        cfg, symbols, start, end, scorer_types={cfg.scorer.type, "jt_momentum"}, console=console
    )

    def metrics(backtester: Backtester) -> RunMetrics:
        r = backtester.run(
            start, end, train_days=TRAIN_DAYS, test_days=TEST_DAYS, step_days=STEP_DAYS
        )
        return RunMetrics(
            dd=r.median_max_dd_ratio_to_spy,
            alpha=r.median_alpha_annualized,
            trades=r.n_trades_total,
        )

    candidate = metrics(Backtester(cfg, data))
    console.print(f"[cyan]candidate {args.config}: {candidate}[/cyan]")
    # The random books keep the candidate's frame; only the signal changes.
    # JTMomentumScorer's top-pct selection stands in for whatever selection
    # depth the candidate's scorer uses.
    top_pct = cfg.scorer.edgar_textdiff_top_pct
    if cfg.scorer.type.startswith("jt"):
        top_pct = cfg.scorer.jt_top_pct
    random_cfg = apply_overrides(cfg, {"scorer.type": "jt_momentum"})
    # A random rank reads no 10-K text; dropping it keeps the frame (prices,
    # universe, sectors) and skips the per-rebalance cosine work.
    price_data = replace(data, risk_factors_history={})
    baselines: dict[str, list[RunMetrics]] = {}
    for kind in ("R1", "R2"):
        baselines[kind] = []
        for seed in SEEDS:
            factory = random_scorer(kind, seed, top_pct)
            m = metrics(Backtester(random_cfg, price_data, scorer_factory=factory))
            baselines[kind].append(m)
            console.print(f"[cyan]{kind} seed {seed}: {m}[/cyan]")
    verdict = skill_gate(candidate, baselines)
    console.print(f"[{'green' if verdict.passed else 'red'}]{verdict}[/]")
    args.out.write_text(
        json.dumps(
            {
                "config": str(args.config),
                "window": args.window,
                "candidate": asdict(candidate),
                "baselines": {k: [asdict(r) for r in v] for k, v in baselines.items()},
                "verdict": asdict(verdict),
            },
            indent=2,
        )
    )
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
