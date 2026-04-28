"""Historical S&P 500 membership via the fja05680/sp500 dataset.

The dataset (CC0-licensed) tracks S&P 500 component changes since 1996.
We download it once on first use into the configured cache directory and
parse it into an in-memory mapping `date -> list[ticker]`.

Source URL:
    https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes(02-21-2025).csv

The filename in the upstream repo carries the last-updated date, which
changes a few times per year. To stay resilient we accept overrides via
`SP500_HISTORICAL_URL` env var; CLI users can swap to a fresher snapshot
without a code change. Fallback default points at a known good URL.

Format:
    date,tickers
    1996-01-02,"A,AAPL,...,ZTS"   (comma-separated tickers within a quoted field)

Lookup is "membership as of date D" = use the most recent dataset row with
date <= D.

Limitation L001: see `docs/limitations.md`. Even with this dataset, OHLCV
for delisted tickers may be missing from yfinance.
"""

from __future__ import annotations

import csv
import os
from datetime import date, datetime
from pathlib import Path

DEFAULT_DATASET_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes(02-21-2025).csv"
)
DATASET_FILENAME = "sp500_historical.csv"


def _dataset_path(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / DATASET_FILENAME


def _download_dataset(target: Path, url: str) -> None:
    """Fetch the fja05680 dataset to `target`. Errors propagate."""
    import httpx

    response = httpx.get(url, follow_redirects=True, timeout=30.0)
    response.raise_for_status()
    target.write_bytes(response.content)


def _ensure_dataset(cache_dir: Path) -> Path:
    """Return path to the dataset, downloading if missing."""
    path = _dataset_path(cache_dir)
    if not path.exists():
        url = os.environ.get("SP500_HISTORICAL_URL", DEFAULT_DATASET_URL)
        _download_dataset(path, url)
    return path


def _parse_dataset(path: Path) -> list[tuple[date, list[str]]]:
    """Parse the CSV into a list of (date, tickers) sorted ascending by date."""
    rows: list[tuple[date, list[str]]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or header[0].lower() != "date":
            raise ValueError(
                f"unexpected dataset header in {path}: {header!r}. "
                "Set SP500_HISTORICAL_URL to override the source."
            )
        for raw_date, raw_tickers in reader:
            try:
                d = datetime.strptime(raw_date.strip(), "%Y-%m-%d").date()
            except ValueError:
                continue
            tickers = [t.strip() for t in raw_tickers.split(",") if t.strip()]
            rows.append((d, tickers))
    rows.sort(key=lambda r: r[0])
    if not rows:
        raise ValueError(f"dataset {path} parsed to zero rows")
    return rows


# In-process memoization keyed by dataset path. Loading is cheap (~2MB CSV)
# but parsing 30 years of daily snapshots is non-trivial.
_CACHED: dict[Path, list[tuple[date, list[str]]]] = {}


def _load(cache_dir: Path) -> list[tuple[date, list[str]]]:
    path = _ensure_dataset(cache_dir)
    if path not in _CACHED:
        _CACHED[path] = _parse_dataset(path)
    return _CACHED[path]


def list_sp500_at(as_of: date, *, cache_dir: Path) -> list[str]:
    """Return the S&P 500 component tickers active on `as_of`.

    Uses the most recent dataset row with `row.date <= as_of`. If `as_of`
    predates the dataset, raises `ValueError`.
    """
    rows = _load(cache_dir)
    candidates = [r for r in rows if r[0] <= as_of]
    if not candidates:
        earliest = rows[0][0]
        raise ValueError(f"as_of={as_of} predates dataset (earliest entry {earliest})")
    return list(candidates[-1][1])
