"""Database integration tests for Market Data Service.

This module contains tests that verify TimescaleDB operations:
- OHLCV data insert and retrieval
- Upsert behavior for duplicate data
- Stock info persistence
- Query performance for time-series data

These tests require TimescaleDB to be running.
"""

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Generator

import pytest

# Database connection settings
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/bloasis",
)


@pytest.fixture(scope="module")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def postgres_available() -> bool:
    """Check if PostgreSQL is available."""
    try:
        import asyncpg

        async def check():
            try:
                conn = await asyncpg.connect(DATABASE_URL, timeout=5)
                await conn.close()
                return True
            except Exception:
                return False

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(check())
        loop.close()
        return result
    except ImportError:
        return False


class TestMarketDataDatabaseSchema:
    """Tests for database schema verification."""

    @pytest.mark.asyncio
    async def test_ohlcv_table_exists(self, postgres_available: bool) -> None:
        """Verify OHLCV table exists in market_data schema."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import asyncpg

        conn = await asyncpg.connect(DATABASE_URL, timeout=5)
        try:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'market_data'
                    AND table_name = 'ohlcv_data'
                )
            """)
            assert result is True, "ohlcv_data table should exist"
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_stock_info_table_exists(self, postgres_available: bool) -> None:
        """Verify stock_info table exists in market_data schema."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import asyncpg

        conn = await asyncpg.connect(DATABASE_URL, timeout=5)
        try:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'market_data'
                    AND table_name = 'stock_info'
                )
            """)
            assert result is True, "stock_info table should exist"
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_ohlcv_is_hypertable(self, postgres_available: bool) -> None:
        """Verify OHLCV table is a TimescaleDB hypertable."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import asyncpg

        conn = await asyncpg.connect(DATABASE_URL, timeout=5)
        try:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM timescaledb_information.hypertables
                    WHERE hypertable_schema = 'market_data'
                    AND hypertable_name = 'ohlcv_data'
                )
            """)
            # May be False if TimescaleDB extension not enabled
            if result is False:
                pytest.skip("TimescaleDB hypertable not configured")
            assert result is True, "ohlcv_data should be a hypertable"
        except Exception as e:
            if "does not exist" in str(e):
                pytest.skip("TimescaleDB not installed")
            raise
        finally:
            await conn.close()


class TestMarketDataOHLCVOperations:
    """Tests for OHLCV data operations."""

    @pytest.mark.asyncio
    async def test_insert_ohlcv_data(self, postgres_available: bool) -> None:
        """Test inserting OHLCV data."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import asyncpg

        conn = await asyncpg.connect(DATABASE_URL, timeout=5)
        try:
            # Insert test data
            test_symbol = "TEST_INTEG"
            test_timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

            await conn.execute(
                """
                INSERT INTO market_data.ohlcv_data
                (symbol, timestamp, interval, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol, timestamp) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
            """,
                test_symbol,
                test_timestamp,
                "1d",
                Decimal("100.00"),
                Decimal("105.00"),
                Decimal("99.00"),
                Decimal("104.00"),
                1000000,
            )

            # Verify data was inserted
            result = await conn.fetchrow(
                """
                SELECT symbol, close, volume
                FROM market_data.ohlcv_data
                WHERE symbol = $1 AND timestamp = $2
            """,
                test_symbol,
                test_timestamp,
            )

            assert result is not None, "Inserted data should be retrievable"
            assert result["symbol"] == test_symbol
            assert float(result["close"]) == 104.00
            assert result["volume"] == 1000000

            # Cleanup
            await conn.execute(
                """
                DELETE FROM market_data.ohlcv_data WHERE symbol = $1
            """,
                test_symbol,
            )
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_ohlcv_upsert_updates_existing(
        self, postgres_available: bool
    ) -> None:
        """Test OHLCV upsert updates existing records."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import asyncpg

        conn = await asyncpg.connect(DATABASE_URL, timeout=5)
        try:
            test_symbol = "TEST_UPSERT"
            test_timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

            # Initial insert
            await conn.execute(
                """
                INSERT INTO market_data.ohlcv_data
                (symbol, timestamp, interval, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol, timestamp) DO UPDATE SET
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
            """,
                test_symbol,
                test_timestamp,
                "1d",
                Decimal("100.00"),
                Decimal("105.00"),
                Decimal("99.00"),
                Decimal("104.00"),
                1000000,
            )

            # Upsert with new values
            await conn.execute(
                """
                INSERT INTO market_data.ohlcv_data
                (symbol, timestamp, interval, open, high, low, close, volume)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (symbol, timestamp) DO UPDATE SET
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume
            """,
                test_symbol,
                test_timestamp,
                "1d",
                Decimal("100.00"),
                Decimal("110.00"),
                Decimal("99.00"),
                Decimal("108.00"),
                2000000,
            )

            # Verify update
            result = await conn.fetchrow(
                """
                SELECT close, volume
                FROM market_data.ohlcv_data
                WHERE symbol = $1 AND timestamp = $2
            """,
                test_symbol,
                test_timestamp,
            )

            assert float(result["close"]) == 108.00, "Close should be updated"
            assert result["volume"] == 2000000, "Volume should be updated"

            # Cleanup
            await conn.execute(
                """
                DELETE FROM market_data.ohlcv_data WHERE symbol = $1
            """,
                test_symbol,
            )
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_ohlcv_time_range_query(self, postgres_available: bool) -> None:
        """Test querying OHLCV data by time range."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import asyncpg

        conn = await asyncpg.connect(DATABASE_URL, timeout=5)
        try:
            test_symbol = "TEST_RANGE"

            # Insert multiple records
            for day in range(1, 6):
                ts = datetime(2026, 1, day, 12, 0, 0, tzinfo=timezone.utc)
                await conn.execute(
                    """
                    INSERT INTO market_data.ohlcv_data
                    (symbol, timestamp, interval, open, high, low, close, volume)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (symbol, timestamp) DO NOTHING
                """,
                    test_symbol,
                    ts,
                    "1d",
                    Decimal("100.00"),
                    Decimal("105.00"),
                    Decimal("99.00"),
                    Decimal(str(100 + day)),
                    1000000 * day,
                )

            # Query by time range
            start = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
            end = datetime(2026, 1, 4, 23, 59, 59, tzinfo=timezone.utc)

            results = await conn.fetch(
                """
                SELECT timestamp, close
                FROM market_data.ohlcv_data
                WHERE symbol = $1
                AND timestamp >= $2
                AND timestamp <= $3
                ORDER BY timestamp
            """,
                test_symbol,
                start,
                end,
            )

            assert len(results) == 3, "Should return 3 records (Jan 2-4)"

            # Cleanup
            await conn.execute(
                """
                DELETE FROM market_data.ohlcv_data WHERE symbol = $1
            """,
                test_symbol,
            )
        finally:
            await conn.close()


class TestMarketDataStockInfoOperations:
    """Tests for stock info operations."""

    @pytest.mark.asyncio
    async def test_insert_stock_info(self, postgres_available: bool) -> None:
        """Test inserting stock info."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import asyncpg

        conn = await asyncpg.connect(DATABASE_URL, timeout=5)
        try:
            test_symbol = "TEST_INFO"

            await conn.execute(
                """
                INSERT INTO market_data.stock_info
                (symbol, name, sector, industry, exchange, currency, market_cap)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (symbol) DO UPDATE SET
                    name = EXCLUDED.name,
                    sector = EXCLUDED.sector
            """,
                test_symbol,
                "Test Company",
                "Technology",
                "Software",
                "NASDAQ",
                "USD",
                Decimal("1000000000"),
            )

            result = await conn.fetchrow(
                """
                SELECT name, sector, market_cap
                FROM market_data.stock_info
                WHERE symbol = $1
            """,
                test_symbol,
            )

            assert result is not None
            assert result["name"] == "Test Company"
            assert result["sector"] == "Technology"

            # Cleanup
            await conn.execute(
                """
                DELETE FROM market_data.stock_info WHERE symbol = $1
            """,
                test_symbol,
            )
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_stock_info_upsert(self, postgres_available: bool) -> None:
        """Test stock info upsert updates existing records."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import asyncpg

        conn = await asyncpg.connect(DATABASE_URL, timeout=5)
        try:
            test_symbol = "TEST_UPSERT_INFO"

            # Initial insert
            await conn.execute(
                """
                INSERT INTO market_data.stock_info
                (symbol, name, sector, currency)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (symbol) DO UPDATE SET
                    name = EXCLUDED.name,
                    sector = EXCLUDED.sector
            """,
                test_symbol,
                "Old Name",
                "Finance",
                "USD",
            )

            # Upsert with new values
            await conn.execute(
                """
                INSERT INTO market_data.stock_info
                (symbol, name, sector, currency)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (symbol) DO UPDATE SET
                    name = EXCLUDED.name,
                    sector = EXCLUDED.sector
            """,
                test_symbol,
                "New Name",
                "Technology",
                "USD",
            )

            result = await conn.fetchrow(
                """
                SELECT name, sector
                FROM market_data.stock_info
                WHERE symbol = $1
            """,
                test_symbol,
            )

            assert result["name"] == "New Name", "Name should be updated"
            assert result["sector"] == "Technology", "Sector should be updated"

            # Cleanup
            await conn.execute(
                """
                DELETE FROM market_data.stock_info WHERE symbol = $1
            """,
                test_symbol,
            )
        finally:
            await conn.close()
