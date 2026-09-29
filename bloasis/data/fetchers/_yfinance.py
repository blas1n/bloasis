"""Single import point for yfinance (issue #71).

yfinance calls `pd.Timestamp.utcnow()` on every history fetch, which emits a
pandas `Pandas4Warning` per symbol and floods the paper-rotate log. A
PYTHONWARNINGS / -W filter cannot silence it: `import yfinance` runs
`warnings.filterwarnings('default', category=DeprecationWarning,
module='^yfinance')`, which is inserted in front of every startup filter.
So this helper installs the ignore filter *after* that import, scoped to
that one message from yfinance's own modules. Every other warning still shows.
"""

from __future__ import annotations

import warnings
from types import ModuleType
from typing import cast


def import_yfinance() -> ModuleType:
    import yfinance

    warnings.filterwarnings(
        "ignore",
        message=r"Timestamp\.utcnow is deprecated",
        category=DeprecationWarning,
        module=r"yfinance\.",
    )
    return cast(ModuleType, yfinance)
