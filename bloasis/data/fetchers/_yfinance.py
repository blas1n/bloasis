"""Single import point for yfinance (issue #71).

yfinance calls `pd.Timestamp.utcnow()` on every history fetch, which emits a
pandas `Pandas4Warning` per symbol and floods the paper-rotate log. A
PYTHONWARNINGS / -W filter cannot silence it: `import yfinance` runs
`warnings.filterwarnings('default', category=DeprecationWarning,
module='^yfinance')`, which is inserted in front of every startup filter.
So this helper installs the ignore filter *after* that import, scoped to
that one message from yfinance's own modules. Every other warning still shows.

It is also the one place a symbol crosses into Yahoo's spelling (issue #78):
index constituents and Alpaca write class shares with a dot (``BRK.B``),
Yahoo with a dash (``BRK-B``) and returns no data for the dotted form. Every
fetcher builds its handle through `ticker()`, so only the request is
translated and callers keep the canonical dotted symbol everywhere else.
"""

from __future__ import annotations

import warnings
from types import ModuleType
from typing import Any, cast


def import_yfinance() -> ModuleType:
    import yfinance

    warnings.filterwarnings(
        "ignore",
        message=r"Timestamp\.utcnow is deprecated",
        category=DeprecationWarning,
        module=r"yfinance\.",
    )
    return cast(ModuleType, yfinance)


def yahoo_symbol(symbol: str) -> str:
    """Yahoo's spelling of a canonical symbol: ``BRK.B`` -> ``BRK-B``."""
    return symbol.replace(".", "-")


def ticker(symbol: str) -> Any:
    """`yfinance.Ticker` for a canonical symbol, requested in Yahoo's spelling."""
    return import_yfinance().Ticker(yahoo_symbol(symbol))
