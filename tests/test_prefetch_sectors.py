"""Issue #92 — prefetch fills `BacktestData.sectors` from EDGAR SIC codes.

Before #92 nothing outside a unit test populated the map, so every holding
was bucketed under `_unknown` and `max_sector_concentration` capped gross
exposure instead of any sector.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd

from bloasis.backtest.prefetch import prefetch_backtest_data
from bloasis.config import StrategyConfig
from tests.market_stub import market_fetcher

_SIC = {"ABT": "2834", "NVDA": "3674", "XOM": "2911"}


def _run(cfg: StrategyConfig, symbols: list[str], **kw: Any) -> tuple[Any, MagicMock]:
    idx = pd.to_datetime(["2026-09-28"])
    ohlcv = MagicMock()
    ohlcv.fetch.return_value = pd.DataFrame({"close": [1.0]}, index=idx)
    edgar = MagicMock()
    edgar.list_10k.return_value = []
    edgar.sic.side_effect = lambda sym: _SIC.get(sym)
    with (
        patch("bloasis.backtest.prefetch.YfOhlcvFetcher", return_value=ohlcv),
        patch("bloasis.backtest.prefetch.YfMarketContextFetcher", return_value=market_fetcher(idx)),
        patch("bloasis.data.fetchers.sec_edgar.EdgarClient", return_value=edgar) as client_cls,
    ):
        data = prefetch_backtest_data(
            cfg, symbols, date(2025, 9, 29), date(2026, 9, 29), console=MagicMock(), **kw
        )
    return data, client_cls


def _cfg(tmp_path: Path, scorer: str, cap: float) -> StrategyConfig:
    return StrategyConfig.model_validate(
        {
            "scorer": {"type": scorer},
            "risk": {"max_sector_concentration": cap},
            "data": {"cache_dir": str(tmp_path)},
        }
    )


def test_sector_cap_below_one_gets_a_sector_per_symbol(tmp_path: Path) -> None:
    data, _ = _run(_cfg(tmp_path, "rule", 0.3), ["ABT", "NVDA", "XOM", "NOSIC"])
    assert data.sectors == {
        "ABT": "Health Care",
        "NVDA": "Information Technology",
        "XOM": "Energy",
        "NOSIC": None,
    }


def test_edgar_scorer_gets_sectors_even_without_a_cap(tmp_path: Path) -> None:
    # The EDGAR scorers already read every registrant's snapshot, so the
    # sector costs nothing extra and keeps the sweep's sector sensor honest.
    data, _ = _run(_cfg(tmp_path, "edgar_textdiff", 1.0), ["ABT", "NVDA"])
    assert data.sectors == {"ABT": "Health Care", "NVDA": "Information Technology"}


def test_no_cap_and_no_edgar_scorer_skips_the_sec_lookup(tmp_path: Path) -> None:
    data, client_cls = _run(_cfg(tmp_path, "rule", 1.0), ["ABT", "NVDA"])
    assert data.sectors == {}
    client_cls.assert_not_called()


def test_caller_can_require_sectors_for_a_grid_whose_combos_lower_the_cap(
    tmp_path: Path,
) -> None:
    # The grid prefetches once on the base config; a combination that lowers
    # the cap must still find sectors in the shared panel.
    data, _ = _run(_cfg(tmp_path, "rule", 1.0), ["ABT"], need_sectors=True)
    assert data.sectors == {"ABT": "Health Care"}


def test_one_failed_sic_lookup_does_not_lose_the_others(tmp_path: Path) -> None:
    idx = pd.to_datetime(["2026-09-28"])
    ohlcv = MagicMock()
    ohlcv.fetch.return_value = pd.DataFrame({"close": [1.0]}, index=idx)
    edgar = MagicMock()

    def sic(sym: str) -> str | None:
        if sym == "BAD":
            raise OSError("SEC unreachable")
        return _SIC.get(sym)

    edgar.sic.side_effect = sic
    with (
        patch("bloasis.backtest.prefetch.YfOhlcvFetcher", return_value=ohlcv),
        patch("bloasis.backtest.prefetch.YfMarketContextFetcher", return_value=market_fetcher(idx)),
        patch("bloasis.data.fetchers.sec_edgar.EdgarClient", return_value=edgar),
    ):
        data = prefetch_backtest_data(
            _cfg(tmp_path, "rule", 0.3),
            ["ABT", "BAD"],
            date(2025, 9, 29),
            date(2026, 9, 29),
            console=MagicMock(),
        )
    assert data.sectors == {"ABT": "Health Care", "BAD": None}
