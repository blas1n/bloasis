"""Russell 2000 universe — iShares IWM ETF holdings.

iShares publishes a daily-updated CSV of the Russell 2000 components
(~2000 small-cap US stocks). Cached locally with a 24h TTL.

Spec: ~/Docs/bloasis/Modern_Alpha_Research_2026-05-09.md — small-cap
universe is more academically aligned with Cohen-Malloy "Lazy Prices"
and similar disclosure-change signals (large caps are too stable).
"""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

USER_AGENT = "Mozilla/5.0"
IWM_CSV_URL = (
    "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
    "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
)


def list_russell2000(
    *,
    cache_dir: Path,
    refresh: bool = False,
    max_age_hours: int = 24,
) -> list[str]:
    """Fetch (or load cached) Russell 2000 ticker list.

    Filters to equity holdings with alphabetic 1-5 char tickers (drops
    cash equivalents, swaps, futures placeholders).
    """
    cache_path = Path(cache_dir).expanduser() / "universe" / "russell2000.csv"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if not refresh and cache_path.exists():
        age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        if age < timedelta(hours=max_age_hours):
            return _parse(cache_path.read_text())

    raw = _download()
    cache_path.write_text(raw)
    return _parse(raw)


def _download() -> str:
    req = urllib.request.Request(IWM_CSV_URL, headers={"User-Agent": USER_AGENT})
    try:
        body = urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"failed to fetch IWM holdings: {e}") from e
    return str(body.decode("utf-8", errors="replace"))


def _parse(raw: str) -> list[str]:
    """Find header row, slice to ticker column, filter equity rows."""
    import pandas as pd

    lines = raw.splitlines()
    # iShares CSV has metadata rows above the header; locate the row
    # whose first cell is the literal "Ticker".
    header_idx = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith('"Ticker"') or line.startswith("Ticker")
        ),
        -1,
    )
    if header_idx < 0:
        raise ValueError("IWM CSV missing 'Ticker' header row")
    df = pd.read_csv(StringIO("\n".join(lines[header_idx:])))
    # Drop non-equity holdings and pure-cash placeholders.
    if "Asset Class" in df.columns:
        df = df[df["Asset Class"].astype(str) == "Equity"]
    raw_tickers = df["Ticker"].dropna().astype(str).str.strip().unique()
    out = sorted(t for t in raw_tickers if t.isalpha() and 1 <= len(t) <= 5)
    return out
