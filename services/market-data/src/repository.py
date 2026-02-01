"""Market Data repository for TimescaleDB storage."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pandas as pd
from shared.utils import PostgresClient
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from .models import OHLCVRecord, StockInfoRecord

logger = logging.getLogger(__name__)


class MarketDataRepository:
    """Repository for market data storage and retrieval."""

    def __init__(self, postgres_client: PostgresClient) -> None:
        """Initialize the repository.

        Args:
            postgres_client: PostgresClient instance for database operations
        """
        self.postgres = postgres_client

    async def save_ohlcv(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame,
    ) -> int:
        """
        Save OHLCV data to TimescaleDB.

        Args:
            symbol: Stock ticker symbol
            interval: Data interval ("1d", "1h", etc.)
            df: DataFrame with OHLCV data (must have timestamp column)

        Returns:
            Number of rows inserted/updated
        """
        if df.empty:
            return 0

        rows_affected = 0
        symbol_upper = symbol.upper()

        async with self.postgres.get_session() as session:
            for _, row in df.iterrows():
                # Extract timestamp - handle different column names
                ts = row.get("timestamp") or row.get("date") or row.get("time")
                if ts is None:
                    continue

                # Convert to datetime if needed
                if isinstance(ts, str):
                    ts = pd.to_datetime(ts)

                # Ensure timezone-aware
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                # Use PostgreSQL upsert
                stmt = insert(OHLCVRecord).values(
                    symbol=symbol_upper,
                    timestamp=ts,
                    interval=interval,
                    open=Decimal(str(row.get("open", 0))),
                    high=Decimal(str(row.get("high", 0))),
                    low=Decimal(str(row.get("low", 0))),
                    close=Decimal(str(row.get("close", 0))),
                    volume=int(row.get("volume", 0)),
                    adj_close=(
                        Decimal(str(row["adj_close"]))
                        if pd.notna(row.get("adj_close"))
                        else None
                    ),
                )

                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "timestamp"],
                    set_={
                        "interval": stmt.excluded.interval,
                        "open": stmt.excluded.open,
                        "high": stmt.excluded.high,
                        "low": stmt.excluded.low,
                        "close": stmt.excluded.close,
                        "volume": stmt.excluded.volume,
                        "adj_close": stmt.excluded.adj_close,
                    },
                )

                await session.execute(stmt)
                rows_affected += 1

        logger.info(f"Saved {rows_affected} OHLCV bars for {symbol}")
        return rows_affected

    async def get_ohlcv(
        self,
        symbol: str,
        interval: str = "1d",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Retrieve OHLCV data from TimescaleDB.

        Args:
            symbol: Stock ticker symbol
            interval: Data interval
            start_time: Start timestamp (inclusive)
            end_time: End timestamp (inclusive)
            limit: Maximum rows to return

        Returns:
            DataFrame with OHLCV data
        """
        if not self.postgres:
            return pd.DataFrame()

        async with self.postgres.get_session() as session:
            stmt = select(OHLCVRecord).where(
                OHLCVRecord.symbol == symbol.upper(),
                OHLCVRecord.interval == interval,
            )

            if start_time:
                stmt = stmt.where(OHLCVRecord.timestamp >= start_time)
            if end_time:
                stmt = stmt.where(OHLCVRecord.timestamp <= end_time)

            stmt = stmt.order_by(OHLCVRecord.timestamp.desc()).limit(limit)

            result = await session.execute(stmt)
            records = result.scalars().all()

        if not records:
            return pd.DataFrame()

        data = [
            {
                "timestamp": r.timestamp,
                "symbol": r.symbol,
                "interval": r.interval,
                "open": float(r.open) if r.open else None,
                "high": float(r.high) if r.high else None,
                "low": float(r.low) if r.low else None,
                "close": float(r.close) if r.close else None,
                "volume": r.volume,
                "adj_close": float(r.adj_close) if r.adj_close else None,
            }
            for r in records
        ]

        logger.debug(f"Retrieved {len(data)} OHLCV bars for {symbol}")
        return pd.DataFrame(data)

    async def get_latest_ohlcv_time(
        self,
        symbol: str,
        interval: str = "1d",
    ) -> Optional[datetime]:
        """
        Get the timestamp of the latest OHLCV record.

        Useful for incremental data fetching.

        Args:
            symbol: Stock ticker symbol
            interval: Data interval

        Returns:
            Latest timestamp or None if no data exists
        """
        if not self.postgres:
            return None

        async with self.postgres.get_session() as session:
            stmt = select(func.max(OHLCVRecord.timestamp)).where(
                OHLCVRecord.symbol == symbol.upper(),
                OHLCVRecord.interval == interval,
            )
            result = await session.execute(stmt)
            return result.scalar()

    async def save_stock_info(
        self,
        symbol: str,
        info: dict,
    ) -> bool:
        """
        Save or update stock info.

        Args:
            symbol: Stock ticker symbol
            info: Stock info dictionary

        Returns:
            True if successful
        """
        if not self.postgres:
            return False

        symbol_upper = symbol.upper()

        async with self.postgres.get_session() as session:
            stmt = insert(StockInfoRecord).values(
                symbol=symbol_upper,
                name=info.get("name", ""),
                sector=info.get("sector", ""),
                industry=info.get("industry", ""),
                exchange=info.get("exchange", ""),
                currency=info.get("currency", "USD"),
                market_cap=(
                    Decimal(str(info["market_cap"])) if info.get("market_cap") else None
                ),
                pe_ratio=(
                    Decimal(str(info["pe_ratio"])) if info.get("pe_ratio") else None
                ),
                dividend_yield=(
                    Decimal(str(info["dividend_yield"]))
                    if info.get("dividend_yield")
                    else None
                ),
                fifty_two_week_high=(
                    Decimal(str(info["fifty_two_week_high"]))
                    if info.get("fifty_two_week_high")
                    else None
                ),
                fifty_two_week_low=(
                    Decimal(str(info["fifty_two_week_low"]))
                    if info.get("fifty_two_week_low")
                    else None
                ),
                updated_at=datetime.now(timezone.utc),
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={
                    "name": stmt.excluded.name,
                    "sector": stmt.excluded.sector,
                    "industry": stmt.excluded.industry,
                    "exchange": stmt.excluded.exchange,
                    "currency": stmt.excluded.currency,
                    "market_cap": stmt.excluded.market_cap,
                    "pe_ratio": stmt.excluded.pe_ratio,
                    "dividend_yield": stmt.excluded.dividend_yield,
                    "fifty_two_week_high": stmt.excluded.fifty_two_week_high,
                    "fifty_two_week_low": stmt.excluded.fifty_two_week_low,
                    "updated_at": stmt.excluded.updated_at,
                },
            )

            await session.execute(stmt)

        logger.info(f"Saved stock info for {symbol}")
        return True

    async def get_stock_info(self, symbol: str) -> Optional[dict]:
        """
        Retrieve stock info from database.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Stock info dictionary or None if not found
        """
        if not self.postgres:
            return None

        async with self.postgres.get_session() as session:
            stmt = select(StockInfoRecord).where(
                StockInfoRecord.symbol == symbol.upper()
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

        if not record:
            return None

        return {
            "symbol": record.symbol,
            "name": record.name,
            "sector": record.sector,
            "industry": record.industry,
            "exchange": record.exchange,
            "currency": record.currency,
            "market_cap": float(record.market_cap) if record.market_cap else None,
            "pe_ratio": float(record.pe_ratio) if record.pe_ratio else None,
            "dividend_yield": (
                float(record.dividend_yield) if record.dividend_yield else None
            ),
            "fifty_two_week_high": (
                float(record.fifty_two_week_high)
                if record.fifty_two_week_high
                else None
            ),
            "fifty_two_week_low": (
                float(record.fifty_two_week_low) if record.fifty_two_week_low else None
            ),
            "updated_at": (
                record.updated_at.isoformat() if record.updated_at else None
            ),
        }

    async def get_symbols_by_sector(self, sector: str) -> list[str]:
        """
        Get all symbols in a sector.

        Args:
            sector: Business sector name

        Returns:
            List of symbols in the sector
        """
        if not self.postgres:
            return []

        async with self.postgres.get_session() as session:
            stmt = (
                select(StockInfoRecord.symbol)
                .where(StockInfoRecord.sector == sector)
                .order_by(StockInfoRecord.symbol)
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]

    async def list_symbols(
        self,
        sector: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[list[str], int]:
        """
        List stored symbols with optional sector filter.

        Args:
            sector: Optional sector to filter by
            limit: Maximum symbols to return

        Returns:
            Tuple of (list of symbols, total count)
        """
        if not self.postgres:
            return [], 0

        async with self.postgres.get_session() as session:
            # Get total count
            count_stmt = select(func.count(StockInfoRecord.symbol))
            if sector:
                count_stmt = count_stmt.where(StockInfoRecord.sector == sector)
            count_result = await session.execute(count_stmt)
            total = count_result.scalar() or 0

            # Get symbols
            symbols_stmt = select(StockInfoRecord.symbol)
            if sector:
                symbols_stmt = symbols_stmt.where(StockInfoRecord.sector == sector)
            symbols_stmt = symbols_stmt.order_by(StockInfoRecord.symbol).limit(limit)

            symbols_result = await session.execute(symbols_stmt)
            symbols = [row[0] for row in symbols_result.all()]

        return symbols, total
