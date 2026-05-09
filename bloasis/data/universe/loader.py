"""Dispatch from `UniverseConfig` to the right loader."""

from __future__ import annotations

from datetime import date

from bloasis.config import DataConfig, UniverseConfig
from bloasis.data.universe.custom_csv import list_custom_csv
from bloasis.data.universe.russell2000 import list_russell2000
from bloasis.data.universe.sp500 import list_sp500
from bloasis.data.universe.sp500_historical import list_sp500_at


def load_universe(
    universe_cfg: UniverseConfig,
    data_cfg: DataConfig,
    *,
    as_of: date | None = None,
    refresh: bool = False,
) -> list[str]:
    """Resolve a universe config to a concrete list of tickers.

    `as_of` is honored only by `sp500_historical`; `sp500` always uses
    today's membership; `custom_csv` ignores it. `refresh=True` forces a
    re-download of network-backed sources (sp500/sp500_historical).
    """
    source = universe_cfg.source
    if source == "sp500":
        return list_sp500(cache_dir=data_cfg.cache_dir, as_of=as_of, refresh=refresh)
    if source == "sp500_historical":
        if as_of is None:
            raise ValueError("sp500_historical requires as_of date")
        return list_sp500_at(as_of, cache_dir=data_cfg.cache_dir, refresh=refresh)
    if source == "russell2000":
        return list_russell2000(cache_dir=data_cfg.cache_dir, refresh=refresh)
    if source == "custom_csv":
        if universe_cfg.custom_csv_path is None:
            raise ValueError("custom_csv source requires custom_csv_path")
        return list_custom_csv(universe_cfg.custom_csv_path)
    raise ValueError(f"unknown universe source: {source!r}")
