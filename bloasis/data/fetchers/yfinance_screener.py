"""Bulk fundamentals fetcher via yfinance Screener.

The Screener returns ~250 results per query with fundamentals already
attached, so a small number of paginated calls covers the entire S&P 500
universe. We pull "US equities sorted by market cap descending" which
captures all large caps in 2-3 calls.

Per-symbol fallback (`fetch_single`) hits `Ticker.info` for stocks the
bulk path missed — slower but unbounded by Screener idiosyncrasies.

Result fields are mapped to `FundamentalRow` with conservative None-handling:
yfinance returns inconsistent types (sometimes None, sometimes 0, sometimes
the string "Infinity"). We coerce to float-or-None and trust downstream
NaN handling in the scoring pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from bloasis.data.fetchers.protocols import FundamentalRow

# yfinance Screener field names (as of 0.2.59) → FundamentalRow fields.
_BULK_FIELD_MAP = {
    "marketCap": "market_cap",
    "trailingPE": "pe_ratio_ttm",
    "priceToBook": "pb_ratio",
    "averageDailyVolume3Month": "_avg_volume",  # combined with price below
    "regularMarketPrice": "_price",
    "profitMargins": "profit_margin",
    "returnOnEquity": "roe",
    "debtToEquity": "debt_to_equity",
    "currentRatio": "current_ratio",
    "sector": "sector",
    "industry": "industry",
}


class YfFundamentalsFetcher:
    """Bulk fundamentals via yfinance.Screener with ticker.info fallback."""

    def fetch_bulk(self, max_count: int = 1000) -> list[FundamentalRow]:
        from yfinance import EquityQuery, Screener

        query = EquityQuery("eq", ["region", "us"])
        screener = Screener()
        screener.set_default_body(
            query,
            sort_field="intradaymarketcap",
            sort_asc=False,
            size=250,
        )

        rows: list[FundamentalRow] = []
        offset = 0
        now = datetime.now(tz=UTC)
        while len(rows) < max_count:
            screener.set_default_body(
                query,
                sort_field="intradaymarketcap",
                sort_asc=False,
                size=250,
                offset=offset,
            )
            result = cast(dict[str, Any], screener.response)
            quotes = result.get("quotes") or []
            if not quotes:
                break
            for q in quotes:
                row = _quote_to_row(q, fetched_at=now)
                if row is not None:
                    rows.append(row)
                if len(rows) >= max_count:
                    break
            if len(quotes) < 250:
                break
            offset += 250

        return rows

    def fetch_single(self, symbol: str) -> FundamentalRow | None:
        import yfinance as yf

        info = yf.Ticker(symbol).info
        if not info:
            return None
        info = dict(info)
        info.setdefault("symbol", symbol)
        return _quote_to_row(info, fetched_at=datetime.now(tz=UTC))


def _quote_to_row(quote: dict[str, Any], *, fetched_at: datetime) -> FundamentalRow | None:
    symbol = quote.get("symbol")
    if not symbol:
        return None

    fields: dict[str, Any] = {}
    for src, dst in _BULK_FIELD_MAP.items():
        fields[dst] = quote.get(src)

    avg_vol = _to_float(fields.pop("_avg_volume", None))
    price = _to_float(fields.pop("_price", None))
    dollar_volume_avg: float | None = None
    if avg_vol is not None and price is not None:
        dollar_volume_avg = avg_vol * price

    return FundamentalRow(
        symbol=str(symbol).upper(),
        fetched_at=fetched_at,
        sector=_to_str(fields.get("sector")),
        industry=_to_str(fields.get("industry")),
        market_cap=_to_float(fields.get("market_cap")),
        pe_ratio_ttm=_to_float(fields.get("pe_ratio_ttm")),
        pb_ratio=_to_float(fields.get("pb_ratio")),
        dollar_volume_avg=dollar_volume_avg,
        profit_margin=_to_float(fields.get("profit_margin")),
        roe=_to_float(fields.get("roe")),
        debt_to_equity=_to_float(fields.get("debt_to_equity")),
        current_ratio=_to_float(fields.get("current_ratio")),
    )


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    if f in (float("inf"), float("-inf")):
        return None
    return f


def _to_str(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None
