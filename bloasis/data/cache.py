"""Local parquet cache for OHLCV and other tabular data.

Cache layout:
    {cache_dir}/parquet/{namespace}/{key}.parquet

Each entry stores a pandas DataFrame plus metadata: the parquet file's
filesystem mtime is the cache timestamp, compared against `max_age` on
read. No separate index database — keeping the cache rebuildable from
scratch is more important than fast lookup.

Stale entries are not auto-deleted; they're simply ignored on read and
overwritten on write. A periodic `bloasis cache prune` (PR6) handles GC.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class ParquetCache:
    """File-backed cache keyed by (namespace, key).

    Threading is not a concern (single-process CLI). Concurrent processes
    may race on writes; last write wins, no corruption since parquet is
    written atomically via tempfile + rename.
    """

    def __init__(self, cache_dir: Path, namespace: str) -> None:
        self.root = cache_dir / "parquet" / namespace
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Sanitize key for filesystem — replace path separators and uppercase
        # symbols are preserved (yfinance ticker convention).
        safe = key.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe}.parquet"

    def get(self, key: str, max_age: timedelta) -> pd.DataFrame | None:
        """Return cached DataFrame if present and fresh, else None."""
        path = self._path(key)
        if not path.exists():
            return None
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        if datetime.now(tz=UTC) - mtime > max_age:
            return None
        import pandas as pd

        return pd.read_parquet(path)

    def put(self, key: str, df: pd.DataFrame) -> None:
        """Atomically write DataFrame to cache."""
        path = self._path(key)
        tmp = path.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, index=True)
        tmp.replace(path)

    def invalidate(self, key: str) -> None:
        """Remove a single entry. No-op if absent."""
        self._path(key).unlink(missing_ok=True)
