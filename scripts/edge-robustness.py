"""Pre-registered out-of-window check: is edgar-rolling2's edge the language or the name?

#99 found that removing each registrant's distinctive name forms from the 10-K
risk-factor texts took the canonical backtest's alpha from +3.74% to +0.01%.
This driver repeats raw-vs-normalized on two walk-forward windows that do not
overlap the canonical test periods, and checks whether selected names say
their own name more often than the rest.

Pre-registration, decision rule and results:
``docs/research/Edge_Robustness_2026-10-02.md``.

Usage (never against the shared cache -- clone it first)::

    uv run python scripts/edge-robustness.py --window A \
        --cache-dir /tmp/bloasis-cache-clone --out /tmp/edge-A.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console

TRAIN_DAYS, TEST_DAYS, STEP_DAYS = 180, 120, 120
BASE_CONFIG = Path("configs/edgar-rolling2.yaml")

#: name -> (start, end, universe as-of, as-of dates for the selection check)
WINDOWS: dict[str, tuple[date, date, date, tuple[date, ...]]] = {
    # Every test period before the canonical protocol's first one.
    "A": (
        date(2018, 1, 1),
        date(2021, 12, 31),
        date(2021, 12, 31),
        (date(2019, 6, 30), date(2021, 6, 30)),
    ),
    # Every test period after the canonical protocol's last one (2024-10-17);
    # the edgar scorer fits nothing, so the train span is warm-up only.
    "B": (
        date(2024, 4, 21),
        date(2026, 9, 30),
        date(2026, 9, 30),
        (date(2025, 6, 30), date(2026, 9, 30)),
    ),
}
MIN_FOLDS = 5


def _load_name_tools() -> Any:
    spec = importlib.util.spec_from_file_location("name_norm_99", Path("scripts/name-norm-99.py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window", required=True, choices=sorted(WINDOWS))
    ap.add_argument("--cache-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    from bloasis.backtest.engine import Backtester
    from bloasis.backtest.grid import apply_overrides
    from bloasis.backtest.prefetch import prefetch_backtest_data
    from bloasis.backtest.walk_forward import generate_folds
    from bloasis.config import load_config
    from bloasis.data.fetchers.sec_edgar import EdgarClient
    from bloasis.data.universe.sp500_historical import list_sp500_at
    from bloasis.scoring.edgar_textdiff import cosine_similarity, tokenize

    tools = _load_name_tools()
    console = Console()
    start, end, universe_as_of, check_dates = WINDOWS[args.window]
    cache = args.cache_dir.expanduser().resolve()
    cfg = apply_overrides(
        load_config(BASE_CONFIG),
        {"data.cache_dir": str(cache), "data.ohlcv_cache_max_age_hours": 24 * 3650},
    )
    n_folds = len(list(generate_folds(start, end, TRAIN_DAYS, TEST_DAYS, STEP_DAYS)))
    console.print(f"[cyan]window {args.window}: {start}..{end} -> {n_folds} folds[/cyan]")
    if n_folds < MIN_FOLDS:
        console.print("[red]fewer than 5 folds -- aborting[/red]")
        return 2

    edgar = EdgarClient(
        cache_dir=cache, max_age_hours=10**6, successions=cfg.data.edgar_successions
    )
    predecessor = {s.successor_cik: s.predecessor_cik for s in cfg.data.edgar_successions}

    def names_for(sym: str) -> list[str]:
        cik = edgar.cik(sym)
        out: list[str] = []
        while cik is not None:
            path = cache / "edgar" / "filings" / f"{cik}.json"
            if not path.exists():
                break
            sub = json.loads(path.read_text())
            out += [sub.get("name") or ""]
            out += [n.get("name", "") for n in sub.get("formerNames") or []]
            cik = predecessor.get(cik)
        return out

    report: dict[str, Any] = {"window": args.window, "start": start, "end": end, "folds": n_folds}
    symbols = list_sp500_at(universe_as_of, cache_dir=cache)
    data = prefetch_backtest_data(
        cfg, symbols, start, end, scorer_types={cfg.scorer.type}, console=console
    )
    forms = {sym: tools.name_forms(names_for(sym)) for sym in data.risk_factors_history}
    norm = {
        sym: [(f, p, tools.strip_forms(t, forms[sym])) for f, p, t in hist]
        for sym, hist in data.risk_factors_history.items()
    }
    report["with_10k_history"] = len(data.risk_factors_history)

    for label, panel in (("raw", data), ("normalized", replace(data, risk_factors_history=norm))):
        r = Backtester(cfg, panel).run(
            start, end, train_days=TRAIN_DAYS, test_days=TEST_DAYS, step_days=STEP_DAYS
        )
        report[f"backtest_{label}"] = {
            "folds": r.n_folds,
            "dd_ratio": r.median_max_dd_ratio_to_spy,
            "sharpe_vs_spy": r.median_sharpe_vs_spy,
            "alpha_annualized": r.median_alpha_annualized,
            "trades": r.n_trades_total,
            "fold_alpha": [f.annualized_alpha for f in r.fold_results],
        }
        console.print(f"[green]{label}: {report[f'backtest_{label}']}[/green]")
        args.out.write_text(json.dumps(report, indent=2, default=str))

    # Mechanism: do selected names say their own name more than the rest?
    lag = timedelta(days=cfg.scorer.edgar_filing_lag_days)
    w = cfg.scorer.edgar_rolling_window
    checks = []
    for as_of in check_dates:
        rolls: dict[str, float] = {}
        share: dict[str, float] = {}
        for sym, hist in data.risk_factors_history.items():
            texts = [t for f, _p, t in sorted(hist) if f <= as_of - lag]
            if len(texts) < 2:
                continue
            cs = [
                cosine_similarity(texts[-(k + 1)], texts[-(k + 2)])
                for k in range(min(w, len(texts) - 1))
            ]
            cs = [c for c in cs if not math.isnan(c)]
            if not cs:
                continue
            rolls[sym] = sum(cs) / len(cs)
            toks = Counter(tokenize(texts[-1]))
            share[sym] = sum(toks[t] for t in forms[sym]) / max(1, sum(toks.values()))
        ranked = sorted(rolls, key=lambda s: rolls[s], reverse=True)
        n = max(1, round(len(ranked) * cfg.scorer.edgar_textdiff_top_pct))
        sel, rest = ranked[:n], ranked[n:]
        checks.append(
            {
                "as_of": as_of,
                "eligible": len(ranked),
                "selected": n,
                "median_name_share_selected": statistics.median(share[s] for s in sel),
                "median_name_share_rest": statistics.median(share[s] for s in rest),
                "share_selected_above_rest_median": sum(
                    1 for s in sel if share[s] > statistics.median(share[x] for x in rest)
                )
                / n,
            }
        )
        console.print(f"[green]mechanism {checks[-1]}[/green]")
    report["mechanism"] = checks
    args.out.write_text(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
