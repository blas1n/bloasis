"""Issue #72 — the EDGAR tickers map and submissions snapshots must expire.

Cached forever, a snapshot hides every 10-K filed after it was written, and
the tickers map misses renames (BK → BNY). Network-free: `_http_get` is
patched and cache ages are set with `os.utime`.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from bloasis.data.fetchers.sec_edgar import EdgarClient

_HTTP = "bloasis.data.fetchers.sec_edgar._http_get"
_SLEEP = "bloasis.data.fetchers.sec_edgar.time.sleep"


def _age(path: Path, hours: float) -> None:
    ts = time.time() - hours * 3600
    os.utime(path, (ts, ts))


def _tickers(rows: dict[str, int]) -> dict[str, dict[str, Any]]:
    return {
        str(i): {"ticker": t, "cik_str": c, "title": t} for i, (t, c) in enumerate(rows.items())
    }


def _block(forms: list[str], dates: list[str]) -> dict[str, list[str]]:
    return {
        "form": forms,
        "filingDate": dates,
        "reportDate": dates,
        "accessionNumber": [f"acc-{d}" for d in dates],
        "primaryDocument": [f"doc-{d}.htm" for d in dates],
    }


def _snapshot(recent: dict[str, list[str]], files: list[dict[str, str]] | None = None) -> str:
    filings: dict[str, Any] = {"recent": recent}
    if files is not None:
        filings["files"] = files
    return json.dumps({"filings": filings})


def _seed(tmp_path: Path, tickers: dict[str, int], hours: float = 0.0) -> Path:
    edgar = tmp_path / "edgar"
    (edgar / "filings").mkdir(parents=True)
    (edgar / "tickers.json").write_text(json.dumps(_tickers(tickers)))
    _age(edgar / "tickers.json", hours)
    return edgar


def _server(routes: dict[str, Any], served: list[str]) -> Callable[..., bytes]:
    def fake_get(url: str, *, accept: str = "text/html") -> bytes:
        served.append(url)
        for suffix, body in routes.items():
            if url.endswith(suffix):
                if isinstance(body, BaseException):
                    raise body
                return (body if isinstance(body, str) else json.dumps(body)).encode()
        raise AssertionError(f"unexpected fetch {url}")

    return fake_get


# ---------------------------------------------------------------------------
# submissions snapshot max age
# ---------------------------------------------------------------------------


def test_list_10k_refreshes_snapshot_older_than_max_age(tmp_path: Path) -> None:
    edgar = _seed(tmp_path, {"AAPL": 320193})
    snap = edgar / "filings" / "0000320193.json"
    snap.write_text(_snapshot(_block(["10-K"], ["2025-10-31"])))
    _age(snap, 48)
    fresh = _snapshot(_block(["10-K", "10-K"], ["2026-10-30", "2025-10-31"]))
    served: list[str] = []

    with (
        patch(_HTTP, side_effect=_server({"CIK0000320193.json": fresh}, served)),
        patch(_SLEEP),
    ):
        out = EdgarClient(tmp_path).list_10k("AAPL")

    assert [f["filed"] for f in out] == [date(2026, 10, 30), date(2025, 10, 31)]
    # The refreshed snapshot replaces the stale one on disk.
    assert "2026-10-30" in snap.read_text()


def test_list_10k_serves_snapshot_within_max_age_without_network(tmp_path: Path) -> None:
    edgar = _seed(tmp_path, {"AAPL": 320193})
    snap = edgar / "filings" / "0000320193.json"
    snap.write_text(_snapshot(_block(["10-K"], ["2025-10-31"])))
    _age(snap, 2)

    with patch(_HTTP, side_effect=AssertionError("no fetch within max age")):
        out = EdgarClient(tmp_path, max_age_hours=24).list_10k("AAPL")

    assert [f["filed"] for f in out] == [date(2025, 10, 31)]


def test_max_age_is_configurable(tmp_path: Path) -> None:
    edgar = _seed(tmp_path, {"AAPL": 320193})
    snap = edgar / "filings" / "0000320193.json"
    snap.write_text(_snapshot(_block(["10-K"], ["2025-10-31"])))
    _age(snap, 2)
    fresh = _snapshot(_block(["10-K"], ["2026-10-30"]))
    served: list[str] = []

    with (
        patch(_HTTP, side_effect=_server({"CIK0000320193.json": fresh}, served)),
        patch(_SLEEP),
    ):
        out = EdgarClient(tmp_path, max_age_hours=1).list_10k("AAPL")

    assert [f["filed"] for f in out] == [date(2026, 10, 30)]


def test_list_filings_reads_the_refreshed_snapshot(tmp_path: Path) -> None:
    # Form 4 / 8-K counts come from the same snapshot as the 10-K list.
    edgar = _seed(tmp_path, {"AAPL": 320193})
    snap = edgar / "filings" / "0000320193.json"
    snap.write_text(_snapshot(_block(["4"], ["2026-05-01"])))
    _age(snap, 48)
    fresh = _snapshot(_block(["4", "4"], ["2026-09-01", "2026-05-01"]))
    served: list[str] = []

    with (
        patch(_HTTP, side_effect=_server({"CIK0000320193.json": fresh}, served)),
        patch(_SLEEP),
    ):
        out = EdgarClient(tmp_path).list_filings("AAPL", form_type="4")

    assert [f["filed"] for f in out] == [date(2026, 9, 1), date(2026, 5, 1)]


# ---------------------------------------------------------------------------
# tickers.json max age — renames
# ---------------------------------------------------------------------------


def test_stale_tickers_map_is_refreshed_and_resolves_bny(tmp_path: Path) -> None:
    # The SP500 constituent is BNY; a map cached before the rename lists BK.
    _seed(tmp_path, {"BK": 1390777}, hours=48)
    served: list[str] = []
    fresh = _tickers({"BNY": 1390777})

    with (
        patch(_HTTP, side_effect=_server({"company_tickers.json": fresh}, served)),
        patch(_SLEEP),
    ):
        cik = EdgarClient(tmp_path).cik("BNY")

    assert cik == "0001390777"


# ---------------------------------------------------------------------------
# paginated `filings.files` pages refresh with their snapshot
# ---------------------------------------------------------------------------


def test_pages_older_than_the_snapshot_are_refetched(tmp_path: Path) -> None:
    # A new filing pushes the oldest `recent` rows into page 001. The stale
    # page ends before those rows, so a fresh snapshot + stale page drops the
    # 2025 10-K — the rolling cosine would pair 2026 with 2024.
    edgar = _seed(tmp_path, {"JPM": 19617})
    page_name = "CIK0000019617-submissions-001.json"
    snap = edgar / "filings" / "0000019617.json"
    page = edgar / "filings" / page_name
    snap.write_text(
        _snapshot(
            _block(["10-K"], ["2025-02-14"]),
            [{"name": page_name, "filingTo": "2024-12-31"}],
        )
    )
    page.write_text(json.dumps(_block(["10-K"], ["2024-02-16"])))
    # The page is still within max age on its own; it is stale only relative
    # to the snapshot that replaces the 48h-old one.
    _age(snap, 48)
    _age(page, 23)

    fresh_snap = _snapshot(
        _block(["10-K"], ["2026-02-13"]),
        [{"name": page_name, "filingTo": "2025-12-31"}],
    )
    fresh_page = _block(["10-K", "10-K"], ["2025-02-14", "2024-02-16"])
    served: list[str] = []
    routes = {"CIK0000019617.json": fresh_snap, page_name: fresh_page}

    with patch(_HTTP, side_effect=_server(routes, served)), patch(_SLEEP):
        out = EdgarClient(tmp_path).list_10k("JPM", since=date(2020, 1, 1))

    assert [f["filed"] for f in out] == [date(2026, 2, 13), date(2025, 2, 14), date(2024, 2, 16)]


def test_page_fetched_after_its_snapshot_is_served_from_cache(tmp_path: Path) -> None:
    edgar = _seed(tmp_path, {"JPM": 19617})
    page_name = "CIK0000019617-submissions-001.json"
    snap = edgar / "filings" / "0000019617.json"
    page = edgar / "filings" / page_name
    snap.write_text(
        _snapshot(
            _block(["10-K"], ["2026-02-13"]),
            [{"name": page_name, "filingTo": "2025-12-31"}],
        )
    )
    page.write_text(json.dumps(_block(["10-K"], ["2025-02-14"])))
    _age(snap, 2)
    _age(page, 1)

    with patch(_HTTP, side_effect=AssertionError("page is consistent with its snapshot")):
        out = EdgarClient(tmp_path).list_10k("JPM", since=date(2020, 1, 1))

    assert [f["filed"] for f in out] == [date(2026, 2, 13), date(2025, 2, 14)]


# ---------------------------------------------------------------------------
# a failed refresh falls back to the stale cache, loudly
# ---------------------------------------------------------------------------


def test_failed_snapshot_refresh_serves_stale_cache_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    edgar = _seed(tmp_path, {"AAPL": 320193})
    snap = edgar / "filings" / "0000320193.json"
    snap.write_text(_snapshot(_block(["10-K"], ["2025-10-31"])))
    _age(snap, 48)
    served: list[str] = []
    boom = urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)  # type: ignore[arg-type]

    with (
        caplog.at_level(logging.WARNING, logger="bloasis.data.fetchers.sec_edgar"),
        patch(_HTTP, side_effect=_server({"CIK0000320193.json": boom}, served)),
        patch(_SLEEP),
    ):
        out = EdgarClient(tmp_path).list_10k("AAPL")

    assert [f["filed"] for f in out] == [date(2025, 10, 31)]
    assert served, "a stale snapshot must be refetched"
    warnings = [r for r in caplog.records if r.getMessage().startswith("edgar_refresh_failed")]
    assert len(warnings) == 1
    # One 5xx is per-name; it must not stop refreshing the other names.
    assert not any(r.getMessage().startswith("edgar_refresh_disabled") for r in caplog.records)
    assert warnings[0].edgar_kind == "submissions"  # type: ignore[attr-defined]
    assert warnings[0].edgar_path == str(snap)  # type: ignore[attr-defined]


def test_failed_tickers_refresh_serves_stale_map_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _seed(tmp_path, {"BK": 1390777}, hours=48)
    served: list[str] = []
    down = urllib.error.URLError("nodename nor servname provided")

    with (
        caplog.at_level(logging.WARNING, logger="bloasis.data.fetchers.sec_edgar"),
        patch(_HTTP, side_effect=_server({"company_tickers.json": down}, served)),
        patch(_SLEEP),
    ):
        cik = EdgarClient(tmp_path).cik("BK")

    assert cik == "0001390777"
    assert any(r.getMessage().startswith("edgar_refresh_failed") for r in caplog.records)


def test_network_failure_stops_refresh_attempts_for_the_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # With the network down every stale name would wait out its own timeout
    # (30s x ~500 names) and stall the 08:00 cron for hours.
    edgar = _seed(tmp_path, {"AAPL": 320193, "MSFT": 789019})
    for cik, day in (("0000320193", "2025-10-31"), ("0000789019", "2025-07-30")):
        path = edgar / "filings" / f"{cik}.json"
        path.write_text(_snapshot(_block(["10-K"], [day])))
        _age(path, 48)
    served: list[str] = []
    down = urllib.error.URLError(TimeoutError("timed out"))

    client = EdgarClient(tmp_path)
    with (
        caplog.at_level(logging.WARNING, logger="bloasis.data.fetchers.sec_edgar"),
        patch(_HTTP, side_effect=_server({".json": down}, served)),
        patch(_SLEEP),
    ):
        aapl = client.list_10k("AAPL")
        msft = client.list_10k("MSFT")

    assert [f["filed"] for f in aapl] == [date(2025, 10, 31)]
    assert [f["filed"] for f in msft] == [date(2025, 7, 30)]
    assert len(served) == 1
    assert any(r.getMessage().startswith("edgar_refresh_disabled") for r in caplog.records)


def test_failed_fetch_without_any_cache_still_raises(tmp_path: Path) -> None:
    # Nothing stale to fall back to: the caller must see the failure rather
    # than an empty filing list that reads as "this company files no 10-Ks".
    _seed(tmp_path, {"AAPL": 320193})
    served: list[str] = []
    down = urllib.error.URLError("down")

    with (
        patch(_HTTP, side_effect=_server({"CIK0000320193.json": down}, served)),
        patch(_SLEEP),
        pytest.raises(urllib.error.URLError),
    ):
        EdgarClient(tmp_path).list_10k("AAPL")


def test_refresh_keeps_the_fair_access_delay(tmp_path: Path) -> None:
    edgar = _seed(tmp_path, {"AAPL": 320193})
    snap = edgar / "filings" / "0000320193.json"
    snap.write_text(_snapshot(_block(["10-K"], ["2025-10-31"])))
    _age(snap, 48)
    fresh = _snapshot(_block(["10-K"], ["2026-10-30"]))
    served: list[str] = []

    with (
        patch(_HTTP, side_effect=_server({"CIK0000320193.json": fresh}, served)),
        patch(_SLEEP) as sleep,
    ):
        EdgarClient(tmp_path).list_10k("AAPL")

    assert len(served) == 1
    assert sleep.call_count == 1
