"""Historical S&P 500 membership via the fja05680/sp500 dataset.

The dataset (CC0-licensed) tracks S&P 500 component changes since 1996.
We download it once on first use into the configured cache directory and
parse it into an in-memory mapping `date -> list[ticker]`.

Source URL pattern:
    https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes(MM-DD-YYYY).csv

The filename in the upstream repo carries the last-updated date, which
changes a few times per year. To stay resilient:

1. `SP500_HISTORICAL_URL` env var, if set, wins outright.
2. Otherwise we ask the GitHub contents API for the master branch and
   pick the latest dated CSV by filename.
3. If the API call fails, we fall back to `DEFAULT_DATASET_URL`.

The cache file on disk is named after the source URL, so a URL change
naturally orphans the old cache instead of silently reusing stale data.
Pass `refresh=True` to force a re-download.

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
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

DEFAULT_DATASET_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes(02-21-2025).csv"
)
GITHUB_CONTENTS_URL = "https://api.github.com/repos/fja05680/sp500/contents/"

# Pattern: "S&P 500 Historical Components & Changes(MM-DD-YYYY).csv"
_DATED_CSV_RE = re.compile(
    r"S&P 500 Historical Components & Changes\((\d{2})-(\d{2})-(\d{4})\)\.csv$"
)


def _resolve_dataset_url() -> str:
    """Pick a source URL.

    Order: env var > GitHub contents API (latest dated CSV) > hardcoded default.
    Network failure on the API call falls back to the default.
    """
    override = os.environ.get("SP500_HISTORICAL_URL")
    if override:
        return override
    try:
        response = httpx.get(GITHUB_CONTENTS_URL, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        entries: Any = response.json()
    except (httpx.HTTPError, ValueError):
        return DEFAULT_DATASET_URL

    best_key: tuple[int, int, int] | None = None
    best_url: str | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        match = _DATED_CSV_RE.search(name)
        if not match:
            continue
        month, day, year = (int(g) for g in match.groups())
        key = (year, month, day)
        if best_key is None or key > best_key:
            best_key = key
            url = entry.get("download_url")
            if isinstance(url, str):
                best_url = url
    return best_url or DEFAULT_DATASET_URL


def _dataset_path(cache_dir: Path, url: str) -> Path:
    """Compute the on-disk cache path for a given source URL.

    Different URLs map to different files, so an upstream filename change
    naturally invalidates the old cache rather than silently reusing it.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = Path(unquote(urlparse(url).path)).name or "sp500_historical.csv"
    return cache_dir / name


def _download_dataset(target: Path, url: str) -> None:
    """Fetch the fja05680 dataset to `target`. Errors propagate."""
    response = httpx.get(url, follow_redirects=True, timeout=30.0)
    response.raise_for_status()
    target.write_bytes(response.content)


def _ensure_dataset(cache_dir: Path, *, refresh: bool = False) -> Path:
    """Return path to the dataset, downloading if missing or `refresh=True`."""
    url = _resolve_dataset_url()
    path = _dataset_path(cache_dir, url)
    if refresh or not path.exists():
        try:
            _download_dataset(path, url)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"failed to download S&P 500 historical dataset from {url!r}: {exc}. "
                "Override the source via `export SP500_HISTORICAL_URL=<url>` or "
                "force a re-download via `bloasis universe show sp500 --refresh`."
            ) from exc
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


def _load(cache_dir: Path, *, refresh: bool = False) -> list[tuple[date, list[str]]]:
    path = _ensure_dataset(cache_dir, refresh=refresh)
    if refresh or path not in _CACHED:
        _CACHED[path] = _parse_dataset(path)
    return _CACHED[path]


def list_sp500_at(
    as_of: date,
    *,
    cache_dir: Path,
    refresh: bool = False,
) -> list[str]:
    """Return the S&P 500 component tickers active on `as_of`.

    Uses the most recent dataset row with `row.date <= as_of`. If `as_of`
    predates the dataset, raises `ValueError`. Pass `refresh=True` to force
    a re-download of the upstream dataset.
    """
    rows = _load(cache_dir, refresh=refresh)
    candidates = [r for r in rows if r[0] <= as_of]
    if not candidates:
        earliest = rows[0][0]
        raise ValueError(f"as_of={as_of} predates dataset (earliest entry {earliest})")
    return list(candidates[-1][1])
