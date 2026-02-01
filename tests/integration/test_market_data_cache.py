"""Redis caching tests for Market Data Service.

This module contains tests that verify Redis caching behavior:
- Cache set and get operations
- Cache TTL expiration
- Cache key format consistency

These tests require Redis to be running.
"""

import json
import os
import time

import pytest

# Redis connection settings
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


@pytest.fixture(scope="module")
def redis_client():
    """Create Redis client for tests."""
    try:
        import redis

        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
        )
        client.ping()
        yield client

        # Cleanup test keys
        for key in client.scan_iter("test:market-data:*"):
            client.delete(key)
    except Exception:
        pytest.skip("Redis not available")


class TestMarketDataCacheOperations:
    """Tests for basic cache operations."""

    def test_cache_set_and_get(self, redis_client) -> None:
        """Test basic cache set and get operations."""
        cache_key = "test:market-data:basic:AAPL"
        test_data = {"symbol": "AAPL", "price": 150.0}

        # Set cache
        redis_client.setex(cache_key, 300, json.dumps(test_data))

        # Get cache
        cached = redis_client.get(cache_key)
        assert cached is not None
        assert json.loads(cached) == test_data

        # Cleanup
        redis_client.delete(cache_key)

    def test_ohlcv_cache_format(self, redis_client) -> None:
        """Test OHLCV cache format matches service expectations."""
        cache_key = "test:market-data:ohlcv:AAPL:1d:1mo"
        test_data = {
            "bars": [
                {
                    "timestamp": "2026-01-15T00:00:00",
                    "open": 150.0,
                    "high": 155.0,
                    "low": 149.0,
                    "close": 154.0,
                    "volume": 1000000,
                }
            ],
            "total_bars": 1,
        }

        # Set cache
        redis_client.setex(cache_key, 300, json.dumps(test_data))

        # Get and verify
        cached = redis_client.get(cache_key)
        parsed = json.loads(cached)

        assert "bars" in parsed
        assert "total_bars" in parsed
        assert len(parsed["bars"]) == 1
        assert parsed["bars"][0]["close"] == 154.0

        # Cleanup
        redis_client.delete(cache_key)

    def test_stock_info_cache_format(self, redis_client) -> None:
        """Test stock info cache format matches service expectations."""
        cache_key = "test:market-data:info:AAPL"
        test_data = {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exchange": "NASDAQ",
            "currency": "USD",
            "market_cap": 3000000000000,
            "pe_ratio": 28.5,
            "dividend_yield": 0.005,
            "fifty_two_week_high": 200.0,
            "fifty_two_week_low": 150.0,
        }

        # Set cache
        redis_client.setex(cache_key, 300, json.dumps(test_data))

        # Get and verify
        cached = redis_client.get(cache_key)
        parsed = json.loads(cached)

        assert parsed["symbol"] == "AAPL"
        assert parsed["name"] == "Apple Inc."
        assert parsed["sector"] == "Technology"
        assert parsed["market_cap"] == 3000000000000

        # Cleanup
        redis_client.delete(cache_key)


class TestMarketDataCacheTTL:
    """Tests for cache TTL behavior."""

    def test_cache_ttl_is_set(self, redis_client) -> None:
        """Test cache TTL is properly set."""
        cache_key = "test:market-data:ttl:check"
        ttl_seconds = 300

        redis_client.setex(cache_key, ttl_seconds, "test_value")

        actual_ttl = redis_client.ttl(cache_key)
        assert actual_ttl > 0, "TTL should be positive"
        assert actual_ttl <= ttl_seconds, "TTL should not exceed set value"

        # Cleanup
        redis_client.delete(cache_key)

    def test_cache_expires(self, redis_client) -> None:
        """Test cache expires after TTL."""
        cache_key = "test:market-data:expire:test"
        short_ttl = 1  # 1 second

        redis_client.setex(cache_key, short_ttl, "test_value")

        # Verify it exists
        assert redis_client.exists(cache_key) == 1

        # Wait for expiration
        time.sleep(1.5)

        # Verify it's gone
        assert redis_client.exists(cache_key) == 0

    def test_different_ttl_for_different_data_types(self, redis_client) -> None:
        """Test that different data types could have different TTLs."""
        ohlcv_key = "test:market-data:ohlcv:ttl"
        info_key = "test:market-data:info:ttl"

        # OHLCV might have shorter TTL (5 min = 300s)
        ohlcv_ttl = 300
        # Stock info might have longer TTL (1 hour = 3600s)
        info_ttl = 3600

        redis_client.setex(ohlcv_key, ohlcv_ttl, "ohlcv_data")
        redis_client.setex(info_key, info_ttl, "info_data")

        assert redis_client.ttl(ohlcv_key) <= ohlcv_ttl
        assert redis_client.ttl(info_key) <= info_ttl

        # Info TTL should be longer than OHLCV TTL
        assert redis_client.ttl(info_key) > redis_client.ttl(ohlcv_key)

        # Cleanup
        redis_client.delete(ohlcv_key)
        redis_client.delete(info_key)


class TestMarketDataCacheKeyFormat:
    """Tests for cache key format consistency."""

    def test_ohlcv_cache_key_format(self, redis_client) -> None:
        """Test OHLCV cache key follows expected format."""
        # Expected format: market-data:ohlcv:{symbol}:{interval}:{period}
        # Set a test key following the pattern
        test_key = "test:market-data:ohlcv:AAPL:1d:1mo"
        redis_client.setex(test_key, 10, "test")

        # Verify we can scan for it
        found = list(redis_client.scan_iter("test:market-data:ohlcv:*"))
        assert test_key in found

        # Cleanup
        redis_client.delete(test_key)

    def test_stock_info_cache_key_format(self, redis_client) -> None:
        """Test stock info cache key follows expected format."""
        # Expected format: market-data:info:{symbol}
        test_key = "test:market-data:info:AAPL"
        redis_client.setex(test_key, 10, "test")

        # Verify we can scan for it
        found = list(redis_client.scan_iter("test:market-data:info:*"))
        assert test_key in found

        # Cleanup
        redis_client.delete(test_key)

    def test_cache_keys_are_case_sensitive(self, redis_client) -> None:
        """Test that cache keys are case-sensitive (symbols should be uppercase)."""
        lower_key = "test:market-data:case:aapl"
        upper_key = "test:market-data:case:AAPL"

        redis_client.setex(lower_key, 10, "lower")
        redis_client.setex(upper_key, 10, "upper")

        assert redis_client.get(lower_key) == "lower"
        assert redis_client.get(upper_key) == "upper"
        assert redis_client.get(lower_key) != redis_client.get(upper_key)

        # Cleanup
        redis_client.delete(lower_key)
        redis_client.delete(upper_key)


class TestMarketDataCacheInvalidation:
    """Tests for cache invalidation scenarios."""

    def test_cache_overwrite(self, redis_client) -> None:
        """Test cache can be overwritten with new data."""
        cache_key = "test:market-data:overwrite"

        # Set initial value
        redis_client.setex(cache_key, 300, json.dumps({"price": 100.0}))

        # Overwrite with new value
        redis_client.setex(cache_key, 300, json.dumps({"price": 150.0}))

        # Verify new value
        cached = json.loads(redis_client.get(cache_key))
        assert cached["price"] == 150.0

        # Cleanup
        redis_client.delete(cache_key)

    def test_cache_delete(self, redis_client) -> None:
        """Test cache can be explicitly deleted."""
        cache_key = "test:market-data:delete"

        redis_client.setex(cache_key, 300, "test_value")
        assert redis_client.exists(cache_key) == 1

        redis_client.delete(cache_key)
        assert redis_client.exists(cache_key) == 0
