"""Pre-registered measurement for issue #99 — registrant-name normalization.

The 10-K risk-factor cosine is a raw TF cosine, and a company's own name is
usually its most frequent token. JPM began writing "JPMorganChase" (one word)
in its FY2024 10-K, so the FY2024-vs-FY2023 cosine fell from ~0.998 to 0.4255
with the language otherwise unchanged. The variant measured here removes each
registrant's *distinctive* name forms before the cosine and leaves generic
words such as "energy" or "financial" in place.

Pre-registration, decision rule and results:
``docs/research/Name_Normalization_2026-10-02.md``.

Usage (never against the shared cache -- clone it first)::

    uv run python scripts/name-norm-99.py \
        --cache-dir /tmp/bloasis-cache-clone --out /tmp/name-norm-99.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console

START = date(2022, 1, 1)
END = date(2024, 10, 17)
TRAIN_DAYS, TEST_DAYS, STEP_DAYS = 180, 120, 120
UNIVERSE_AS_OF = date(2024, 12, 31)
LIVE_AS_OF = date(2026, 10, 2)
BASE_CONFIG = Path("configs/edgar-rolling2.yaml")

#: Words in registrant names that are ordinary English (legal form, industry,
#: geography). They stay in the text. Fixed before measuring.
GENERIC_NAME_WORDS = frozenset(
    """
    corp corporation company companies group holdings holding holdco incorporated
    limited international global worldwide united american america national
    first general state street southern northern eastern western central pacific
    atlantic midland london energy financial finance technologies technology
    services service systems solutions resources industries industrial property
    properties realty real estate equities trust bank banking bancorp bancshares
    capital investors investment investments management partners enterprise
    enterprises brands products stores foods health healthcare care medical
    pharmaceuticals pharmaceutical therapeutics laboratories scientific
    instruments communications networks media entertainment power electric gas
    water utilities petroleum chemical chemicals materials automotive motors
    airlines railway computer software data digital semiconductor devices
    insurance express works dollar platforms home homes
    """.split()  # noqa: SIM905 -- a word list reads better as prose
)
_LEGAL_FORM = frozenset({"inc", "corp", "co", "de", "ltd", "plc", "llc", "lp", "nv", "sa", "ag"})


def name_forms(names: list[str]) -> set[str]:
    """Distinctive tokens of a registrant's names, plus every joined run of
    two or more adjacent name words (``jpmorgan``+``chase`` ->
    ``jpmorganchase``). Only forms the tokenizer can emit (>= 4 letters)."""
    out: set[str] = set()
    for name in names:
        words = [w for w in re.findall(r"[a-z]+", name.lower()) if w not in _LEGAL_FORM]
        out |= {w for w in words if len(w) >= 4 and w not in GENERIC_NAME_WORDS}
        for i in range(len(words)):
            for j in range(i + 2, len(words) + 1):
                joined = "".join(words[i:j])
                if len(joined) >= 4:
                    out.add(joined)
    return out


def strip_forms(text: str, forms: set[str]) -> str:
    if not forms:
        return text
    pattern = re.compile(
        r"(?i)(?<![a-z])("
        + "|".join(sorted(map(re.escape, forms), key=len, reverse=True))
        + r")(?![a-z])"
    )
    return pattern.sub(" ", text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    from bloasis.backtest.engine import Backtester
    from bloasis.backtest.grid import apply_overrides
    from bloasis.backtest.prefetch import prefetch_backtest_data
    from bloasis.backtest.walk_forward import generate_folds
    from bloasis.cli import _current_symbols, _resolve_universe_symbols
    from bloasis.config import load_config
    from bloasis.data.fetchers.sec_edgar import EdgarClient
    from bloasis.data.universe.sp500_historical import list_sp500_at
    from bloasis.scoring.edgar_textdiff import cosine_similarity

    console = Console()
    cache = args.cache_dir.expanduser().resolve()
    cfg = apply_overrides(
        load_config(BASE_CONFIG),
        {"data.cache_dir": str(cache), "data.ohlcv_cache_max_age_hours": 24 * 3650},
    )
    edgar = EdgarClient(
        cache_dir=cache, max_age_hours=10**6, successions=cfg.data.edgar_successions
    )
    predecessor = {s.successor_cik: s.predecessor_cik for s in cfg.data.edgar_successions}

    def names_for(sym: str) -> list[str]:
        cik = edgar.cik(sym)
        out: list[str] = []
        while cik is not None:
            sub = json.loads((cache / "edgar" / "filings" / f"{cik}.json").read_text())
            out += [sub.get("name") or ""] + [
                n.get("name", "") for n in sub.get("formerNames") or []
            ]
            cik = predecessor.get(cik)
        return out

    report: dict[str, Any] = {}

    # --- validity check: JPM FY2024 vs FY2023 --------------------------------
    fs = sorted(edgar.list_10k("JPM", since=date(2022, 6, 1)), key=lambda f: f["filed"])
    by_period = {f["period"].year: edgar.risk_factors("JPM", f) for f in fs}
    jpm_forms = name_forms(names_for("JPM"))
    report["jpm_forms"] = sorted(jpm_forms)
    report["jpm_fy24_vs_fy23"] = {
        "raw": cosine_similarity(by_period[2024] or "", by_period[2023] or ""),
        "normalized": cosine_similarity(
            strip_forms(by_period[2024] or "", jpm_forms),
            strip_forms(by_period[2023] or "", jpm_forms),
        ),
    }
    console.print(f"[cyan]JPM forms {sorted(jpm_forms)} -> {report['jpm_fy24_vs_fy23']}[/cyan]")

    # --- canonical 7-fold backtest, one panel, raw vs normalized texts -------
    n_folds = len(list(generate_folds(START, END, TRAIN_DAYS, TEST_DAYS, STEP_DAYS)))
    if n_folds != 7:
        console.print("[red]protocol does not yield 7 folds -- aborting[/red]")
        return 2
    symbols = list_sp500_at(UNIVERSE_AS_OF, cache_dir=cache)
    data = prefetch_backtest_data(
        cfg, symbols, START, END, scorer_types={cfg.scorer.type}, console=console
    )
    normalized_history = {}
    for sym, hist in data.risk_factors_history.items():
        forms = name_forms(names_for(sym))
        normalized_history[sym] = [(f, p, strip_forms(t, forms)) for f, p, t in hist]
    data_norm = replace(data, risk_factors_history=normalized_history)

    for label, panel in (("raw", data), ("normalized", data_norm)):
        r = Backtester(cfg, panel).run(
            START, END, train_days=TRAIN_DAYS, test_days=TEST_DAYS, step_days=STEP_DAYS
        )
        report[f"backtest_{label}"] = {
            "folds": r.n_folds,
            "dd_ratio": r.median_max_dd_ratio_to_spy,
            "sharpe_vs_spy": r.median_sharpe_vs_spy,
            "alpha_annualized": r.median_alpha_annualized,
            "trades": r.n_trades_total,
            "fold_dd_ratios": [f.max_dd_ratio_to_spy for f in r.fold_results],
        }
        console.print(f"[green]{label}: {report[f'backtest_{label}']}[/green]")
        args.out.write_text(json.dumps(report, indent=2, default=str))

    # --- today's live selection (sp500, same rolling rule as the engine) -----
    lag = timedelta(days=cfg.scorer.edgar_filing_lag_days)
    window = cfg.scorer.edgar_rolling_window
    live_syms = _current_symbols(cfg, _resolve_universe_symbols("sp500", None, cache))
    rolls: dict[str, dict[str, float]] = {}
    for sym in live_syms:
        filings = [
            f
            for f in edgar.list_10k(sym, since=LIVE_AS_OF - timedelta(days=5 * 365))
            if f["filed"] <= LIVE_AS_OF - lag
        ]
        filings.sort(key=lambda f: f["filed"])
        texts = [t for t in (edgar.risk_factors(sym, f) for f in filings) if t]
        if len(texts) < 2:
            continue
        forms = name_forms(names_for(sym))
        out = {}
        for label, prep in (
            ("raw", lambda t: t),
            ("normalized", lambda t, f=forms: strip_forms(t, f)),
        ):
            cs = [
                cosine_similarity(prep(texts[-(k + 1)]), prep(texts[-(k + 2)]))
                for k in range(min(window, len(texts) - 1))
            ]
            cs = [c for c in cs if not math.isnan(c)]
            out[label] = sum(cs) / len(cs) if cs else float("nan")
        rolls[sym] = out

    def selected(label: str) -> tuple[set[str], float]:
        ranked = sorted(
            (s for s in rolls if not math.isnan(rolls[s][label])),
            key=lambda s: rolls[s][label],
            reverse=True,
        )
        n = max(1, round(len(ranked) * cfg.scorer.edgar_textdiff_top_pct))
        return set(ranked[:n]), rolls[ranked[n - 1]][label]

    sel_raw, cut_raw = selected("raw")
    sel_norm, cut_norm = selected("normalized")
    moved = sorted(rolls, key=lambda s: abs(rolls[s]["normalized"] - rolls[s]["raw"]), reverse=True)
    report["live"] = {
        "eligible": len(rolls),
        "cutoff_raw": cut_raw,
        "cutoff_normalized": cut_norm,
        "selected": len(sel_raw),
        "added": sorted(sel_norm - sel_raw),
        "removed": sorted(sel_raw - sel_norm),
        "moved_gt_0.01": sum(
            1 for s in rolls if abs(rolls[s]["normalized"] - rolls[s]["raw"]) > 0.01
        ),
        "top_moves": [(s, rolls[s]["raw"], rolls[s]["normalized"]) for s in moved[:12]],
    }
    console.print(f"[green]live: {report['live']}[/green]")
    args.out.write_text(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
