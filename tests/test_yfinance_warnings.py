"""Issue #71 — silence yfinance's `Timestamp.utcnow` Pandas4Warning, only that one.

yfinance calls `pd.Timestamp.utcnow()` on every history fetch (~100 lines per
SP500 paper run). A PYTHONWARNINGS / -W filter cannot silence it: importing
yfinance runs `warnings.filterwarnings('default', category=DeprecationWarning,
module='^yfinance')`, which lands in front of every startup filter. So the
ignore filter is installed right after that import, by `import_yfinance()`.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

from pandas.errors import Pandas4Warning

from bloasis.data.fetchers._yfinance import import_yfinance

_UTCNOW = (
    "Timestamp.utcnow is deprecated and will be removed in a future version. "
    "Use Timestamp.now('UTC') instead."
)
_YF_MODULE = "yfinance.scrapers.history"


def _emit_from_yfinance(message: str, category: type[Warning]) -> None:
    warnings.warn_explicit(message, category, "history.py", 173, module=_YF_MODULE, registry={})


def test_utcnow_warning_from_yfinance_is_silenced() -> None:
    with warnings.catch_warnings(record=True) as seen:
        # What `import yfinance` does on first import (pytest restores the
        # filter list between tests, so re-install it explicitly).
        warnings.filterwarnings("default", category=DeprecationWarning, module="^yfinance")
        import_yfinance()
        _emit_from_yfinance(_UTCNOW, Pandas4Warning)
    assert [str(w.message) for w in seen] == []


def test_other_yfinance_warnings_still_show() -> None:
    with warnings.catch_warnings(record=True) as seen:
        warnings.filterwarnings("default", category=DeprecationWarning, module="^yfinance")
        import_yfinance()
        _emit_from_yfinance("some other yfinance deprecation", DeprecationWarning)
        warnings.warn_explicit(
            _UTCNOW, Pandas4Warning, "ours.py", 1, module="bloasis.x", registry={}
        )
    assert len(seen) == 2  # a different message, and utcnow from outside yfinance


def test_every_yfinance_import_goes_through_the_helper() -> None:
    root = Path(__file__).resolve().parents[1] / "bloasis"
    pattern = re.compile(r"^\s*(import yfinance|from yfinance import)", re.MULTILINE)
    importers = {
        str(p.relative_to(root)) for p in root.rglob("*.py") if pattern.search(p.read_text())
    }
    assert importers == {"data/fetchers/_yfinance.py"}
