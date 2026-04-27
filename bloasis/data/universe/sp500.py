"""Current S&P 500 universe.

Defined as `list_sp500_at(today)` from the historical dataset — avoids
maintaining two parallel lists. This means the `sp500` and `sp500_historical`
modes return the same membership when `as_of=today`, by design.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from bloasis.data.universe.sp500_historical import list_sp500_at


def list_sp500(*, cache_dir: Path, as_of: date | None = None) -> list[str]:
    """Return current (or `as_of`) S&P 500 tickers."""
    return list_sp500_at(as_of or datetime.now(tz=UTC).date(), cache_dir=cache_dir)
