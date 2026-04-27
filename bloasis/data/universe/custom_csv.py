"""Universe loaded from a user-supplied CSV.

Format expected: one column named `symbol` (case-insensitive). Additional
columns are ignored. Empty lines and `#`-prefixed comments are skipped.

The CSV path is resolved relative to the current working directory unless
absolute. Symbols are upper-cased and de-duplicated, preserving order.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from pathlib import Path


def list_custom_csv(path: Path) -> list[str]:
    """Read symbols from a CSV file."""
    if not path.exists():
        raise FileNotFoundError(f"custom universe CSV not found: {path}")

    seen: set[str] = set()
    out: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(_strip_comments(f))
        if reader.fieldnames is None:
            raise ValueError(f"empty CSV: {path}")
        col = _find_symbol_column(reader.fieldnames)
        for row in reader:
            sym = (row.get(col) or "").strip().upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            out.append(sym)

    if not out:
        raise ValueError(f"no symbols found in {path}")
    return out


def _strip_comments(lines: Iterable[str]) -> Iterator[str]:
    """Filter out `#`-prefixed lines and blank lines from a text iterable."""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            yield line


def _find_symbol_column(fieldnames: Iterable[str]) -> str:
    """Return the column name that maps to ticker symbols."""
    names = list(fieldnames)
    for name in names:
        if name and name.strip().lower() == "symbol":
            return name
    raise ValueError(
        "CSV must have a 'symbol' column (case-insensitive). "
        f"Got columns: {names!r}"
    )
