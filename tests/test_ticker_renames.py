"""Issue #80 — a constituent the index source still lists under its old ticker.

The fja05680 S&P 500 list still prints EchoStar as ``SATS``; the company
trades as ``ECHO`` (Nasdaq), Yahoo 404s ``SATS`` and SEC's
company_tickers.json lists only ``ECHO`` (CIK 1415404). The source carries
no CIK, so the link comes from an explicit table citing an SEC filing, and
it is followed only while SEC's current ticker map says the new symbol
belongs to the cited CIK. Nothing is guessed from company names.

Network-free: the SEC ticker map is seeded on disk and `_http_get` is patched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import select
from typer.testing import CliRunner

from bloasis.config import StrategyConfig
from bloasis.data.fetchers.sec_edgar import (
    DEFAULT_TICKER_RENAMES,
    TickerRename,
    resolve_current_symbols,
)
from tests.market_stub import market_fetcher

_HTTP = "bloasis.data.fetchers.sec_edgar._http_get"
_SLEEP = "bloasis.data.fetchers.sec_edgar.time.sleep"

ECHOSTAR = "0001415404"
SATS_TO_ECHO = TickerRename(
    listed="SATS", current="ECHO", cik="1415404", evidence_accession="0001415404-26-000030"
)


def _cik_map(mapping: dict[str, str]) -> Any:
    calls: list[str] = []

    def lookup(ticker: str) -> str | None:
        calls.append(ticker)
        return mapping.get(ticker)

    lookup.calls = calls  # type: ignore[attr-defined]
    return lookup


# ---------------------------------------------------------------------------
# resolver
# ---------------------------------------------------------------------------


def test_listed_ticker_resolves_to_current_when_sec_confirms_the_cik() -> None:
    lookup = _cik_map({"ECHO": ECHOSTAR, "AAPL": "0000320193"})
    out = resolve_current_symbols(["AAPL", "SATS", "MSFT"], [SATS_TO_ECHO], lookup)
    assert out == ["AAPL", "ECHO", "MSFT"]


def test_symbols_outside_the_table_never_touch_the_sec_map() -> None:
    lookup = _cik_map({})
    out = resolve_current_symbols(["AAPL", "MSFT"], [SATS_TO_ECHO], lookup)
    assert out == ["AAPL", "MSFT"]
    assert lookup.calls == []


def test_rename_refused_when_new_symbol_belongs_to_another_cik() -> None:
    # The table is stale or wrong: ECHO now maps to some other registrant.
    lookup = _cik_map({"ECHO": "0000000001"})
    assert resolve_current_symbols(["SATS"], [SATS_TO_ECHO], lookup) == ["SATS"]


def test_rename_refused_when_new_symbol_is_unknown_to_sec() -> None:
    assert resolve_current_symbols(["SATS"], [SATS_TO_ECHO], _cik_map({})) == ["SATS"]


def test_rename_refused_when_listed_ticker_now_names_another_company() -> None:
    # SATS reused by a different registrant: the listing may mean either.
    lookup = _cik_map({"ECHO": ECHOSTAR, "SATS": "0000000002"})
    assert resolve_current_symbols(["SATS"], [SATS_TO_ECHO], lookup) == ["SATS"]


def test_rename_applies_while_sec_lists_both_symbols_for_the_same_cik() -> None:
    lookup = _cik_map({"ECHO": ECHOSTAR, "SATS": ECHOSTAR})
    assert resolve_current_symbols(["SATS"], [SATS_TO_ECHO], lookup) == ["ECHO"]


def test_sec_map_failure_keeps_listed_symbols() -> None:
    def broken(_ticker: str) -> str | None:
        raise OSError("sec down")

    assert resolve_current_symbols(["SATS", "AAPL"], [SATS_TO_ECHO], broken) == ["SATS", "AAPL"]


def test_source_listing_both_old_and_new_ticker_yields_one_symbol() -> None:
    lookup = _cik_map({"ECHO": ECHOSTAR})
    out = resolve_current_symbols(["SATS", "AAPL", "ECHO"], [SATS_TO_ECHO], lookup)
    assert out == ["ECHO", "AAPL"]


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def test_default_config_carries_the_echostar_rename() -> None:
    renames = StrategyConfig().data.ticker_renames
    assert SATS_TO_ECHO in renames
    assert list(DEFAULT_TICKER_RENAMES) == renames
    assert SATS_TO_ECHO.cik == ECHOSTAR


def test_yaml_rename_table_accepts_bare_number_cik(tmp_path: Path) -> None:
    raw = yaml.safe_load(
        "data:\n  ticker_renames:\n"
        "    - {listed: sats, current: echo, cik: 1415404,"
        " evidence_accession: 0001415404-26-000030}\n"
    )
    cfg = StrategyConfig.model_validate(raw)
    assert cfg.data.ticker_renames == [SATS_TO_ECHO]


def test_rename_table_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(
            {"data": {"ticker_renames": [{"listed": "SATS", "current": "ECHO", "cik": "1"}]}}
        )


# ---------------------------------------------------------------------------
# call site: `trade paper --universe sp500` → data fetch → orders → DB
# ---------------------------------------------------------------------------


def _seed_sec_map(cache_dir: Path, rows: dict[str, int]) -> None:
    edgar = cache_dir / "edgar"
    (edgar / "filings").mkdir(parents=True, exist_ok=True)
    body = {
        str(i): {"ticker": t, "cik_str": c, "title": t} for i, (t, c) in enumerate(rows.items())
    }
    (edgar / "tickers.json").write_text(json.dumps(body))


def _paper_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, constituents: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Run `trade paper --universe sp500 --session s` through the real
    candidate builder and prefetch. Returns (yahoo requests, order symbols,
    persisted paper_orders symbols)."""
    from bloasis.broker import BrokerAdapter
    from bloasis.cli import app
    from bloasis.storage import create_all, get_engine, paper_orders

    db = tmp_path / "paper.db"
    monkeypatch.setenv("BLOASIS_DB_PATH", str(db))
    create_all(get_engine(db))
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"scorer": {"type": "rule"}, "data": {"cache_dir": str(tmp_path / "cache")}})
    )
    monkeypatch.setattr(
        "bloasis.data.universe.sp500.list_sp500", lambda cache_dir: list(constituents)
    )

    today = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
    requested: list[str] = []

    def fetch(symbol: str, _start: Any, _end: Any) -> pd.DataFrame:
        requested.append(symbol)
        if symbol == "SATS":  # what Yahoo does today
            raise ValueError("HTTP Error 404: SATS")
        return pd.DataFrame({"close": [200.0]}, index=[today])

    ohlcv = MagicMock()
    ohlcv.fetch.side_effect = fetch

    def fake_backtester(_cfg: StrategyConfig, data: Any) -> MagicMock:
        cands = []
        for sym in data.bars:
            c = MagicMock(symbol=sym, last_close=200.0)
            c.feature_vector.symbol = sym
            cands.append(c)
        bt = MagicMock()
        bt._build_candidates.return_value = (cands, [])
        return bt

    def signal(sym: str) -> MagicMock:
        sig = MagicMock(action="BUY", symbol=sym, entry_price=200.0, target_size_pct=0.02)
        sig.timestamp = pd.Timestamp("2026-09-30", tz="UTC")
        sig.reason = f"buy-{sym}"
        return sig

    sig_gen = MagicMock()
    sig_gen.return_value.generate.side_effect = lambda cands, held: [
        signal(c.symbol) for c in cands
    ]
    monkeypatch.setattr("bloasis.signal.SignalGenerator", sig_gen)

    broker = MagicMock(mode="paper")
    broker.get_account.return_value = MagicMock(cash=100_000.0, equity=100_000.0)
    broker.get_positions.return_value = []
    broker.place_market_order.return_value = MagicMock(
        status="accepted", filled_qty=0.0, filled_avg_price=0.0, reason=None
    )
    BrokerAdapter.register(MagicMock)
    monkeypatch.setattr("bloasis.broker.AlpacaBrokerAdapter", lambda mode="paper": broker)

    with (
        patch("bloasis.backtest.prefetch.YfOhlcvFetcher", return_value=ohlcv),
        patch(
            "bloasis.backtest.prefetch.YfMarketContextFetcher",
            return_value=market_fetcher([today]),
        ),
        patch("bloasis.backtest.engine.Backtester", side_effect=fake_backtester),
        patch(_HTTP, side_effect=AssertionError("no SEC network in tests")),
        patch(_SLEEP),
    ):
        res = CliRunner().invoke(
            app,
            ["trade", "paper", "--universe", "sp500", "--session", "s", "-c", str(cfg_path)],
        )
    assert res.exit_code == 0, res.output

    ordered = [c.args[0].symbol for c in broker.place_market_order.call_args_list]
    with get_engine(db).connect() as conn:
        stored = [r.symbol for r in conn.execute(select(paper_orders))]
    return requested, ordered, stored


def test_paper_run_fetches_orders_and_stores_the_current_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_sec_map(tmp_path / "cache", {"ECHO": 1415404, "AAPL": 320193})

    requested, ordered, stored = _paper_run(tmp_path, monkeypatch, ["AAPL", "SATS"])

    assert "SATS" not in requested and "ECHO" in requested
    assert sorted(ordered) == ["AAPL", "ECHO"]
    assert sorted(stored) == ["AAPL", "ECHO"]


def test_paper_run_keeps_listed_symbol_when_sec_disagrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # SEC says ECHO is someone else: no rename, SATS is fetched (and skipped).
    _seed_sec_map(tmp_path / "cache", {"ECHO": 999, "AAPL": 320193})

    requested, ordered, _stored = _paper_run(tmp_path, monkeypatch, ["AAPL", "SATS"])

    assert "SATS" in requested and "ECHO" not in requested
    assert ordered == ["AAPL"]
