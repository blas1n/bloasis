"""
Tests for cache_strategy module.

Tests cover:
- CacheTier enum
- CacheConfig dataclass
- CacheManager operations (get, set, invalidate, etc.)
- Cache metrics tracking
- Factory function
"""

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.utils.cache_strategy import (
    CACHE_CONFIGS,
    CacheConfig,
    CacheManager,
    CacheTier,
    DecimalEncoder,
    _deserialize,
    _serialize,
    create_cache_manager,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis_client() -> MagicMock:
    """Create a mock RedisClient."""
    client = MagicMock()
    client.client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.setex = AsyncMock()
    client.delete = AsyncMock()
    client.client.keys = AsyncMock(return_value=[])
    client.client.ttl = AsyncMock(return_value=3600)
    client.client.exists = AsyncMock(return_value=1)
    client.client.expire = AsyncMock(return_value=True)
    return client


@pytest.fixture
def cache_manager(mock_redis_client: MagicMock) -> CacheManager:
    """Create a CacheManager with mocked Redis client."""
    return CacheManager(mock_redis_client)


# =============================================================================
# CacheTier Tests
# =============================================================================


class TestCacheTier:
    """Tests for CacheTier enum."""

    def test_tier_values(self) -> None:
        """Test tier enum values."""
        assert CacheTier.TIER1_SHARED.value == "market"
        assert CacheTier.TIER2_DATA.value == "data"
        assert CacheTier.TIER3_USER.value == "user"

    def test_tier_is_string_enum(self) -> None:
        """Test tier is string enum."""
        assert isinstance(CacheTier.TIER1_SHARED, str)
        assert CacheTier.TIER1_SHARED == "market"


# =============================================================================
# CacheConfig Tests
# =============================================================================


class TestCacheConfig:
    """Tests for CacheConfig dataclass."""

    def test_create_config(self) -> None:
        """Test creating a cache config."""
        config = CacheConfig(
            tier=CacheTier.TIER1_SHARED,
            ttl_seconds=3600,
            key_template="test:{key}",
        )
        assert config.tier == CacheTier.TIER1_SHARED
        assert config.ttl_seconds == 3600
        assert config.key_template == "test:{key}"

    def test_config_is_frozen(self) -> None:
        """Test config is immutable."""
        config = CacheConfig(
            tier=CacheTier.TIER1_SHARED,
            ttl_seconds=3600,
            key_template="test:{key}",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            config.ttl_seconds = 7200  # type: ignore[misc]


# =============================================================================
# Predefined Configs Tests
# =============================================================================


class TestPredefinedConfigs:
    """Tests for predefined CACHE_CONFIGS."""

    def test_regime_config(self) -> None:
        """Test regime cache config."""
        config = CACHE_CONFIGS["regime"]
        assert config.tier == CacheTier.TIER1_SHARED
        assert config.ttl_seconds == 21600  # 6 hours
        assert config.key_template == "market:regime:current"

    def test_sector_config(self) -> None:
        """Test sector cache config."""
        config = CACHE_CONFIGS["sector"]
        assert config.tier == CacheTier.TIER1_SHARED
        assert config.ttl_seconds == 86400  # 24 hours

    def test_ohlcv_config(self) -> None:
        """Test OHLCV cache config."""
        config = CACHE_CONFIGS["ohlcv"]
        assert config.tier == CacheTier.TIER2_DATA
        assert config.ttl_seconds == 300  # 5 minutes

    def test_stock_info_config(self) -> None:
        """Test stock info cache config."""
        config = CACHE_CONFIGS["stock_info"]
        assert config.tier == CacheTier.TIER2_DATA
        assert config.ttl_seconds == 86400  # 24 hours

    def test_sentiment_config(self) -> None:
        """Test sentiment cache config."""
        config = CACHE_CONFIGS["sentiment"]
        assert config.tier == CacheTier.TIER2_DATA
        assert config.ttl_seconds == 3600  # 1 hour

    def test_preferences_config(self) -> None:
        """Test preferences cache config."""
        config = CACHE_CONFIGS["preferences"]
        assert config.tier == CacheTier.TIER3_USER
        assert config.ttl_seconds == 3600  # 1 hour

    def test_portfolio_config(self) -> None:
        """Test portfolio cache config."""
        config = CACHE_CONFIGS["portfolio"]
        assert config.tier == CacheTier.TIER3_USER
        assert config.ttl_seconds == 300  # 5 minutes


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Tests for serialization utilities."""

    def test_serialize_dict(self) -> None:
        """Test serializing a dict."""
        data = {"key": "value", "number": 42}
        result = _serialize(data)
        assert result == '{"key": "value", "number": 42}'

    def test_serialize_list(self) -> None:
        """Test serializing a list."""
        data = [1, 2, 3]
        result = _serialize(data)
        assert result == "[1, 2, 3]"

    def test_serialize_decimal(self) -> None:
        """Test serializing Decimal values."""
        data = {"price": Decimal("150.25")}
        result = _serialize(data)
        assert result == '{"price": "150.25"}'

    def test_serialize_nested_decimal(self) -> None:
        """Test serializing nested Decimal values."""
        data = {
            "portfolio": {
                "value": Decimal("10000.50"),
                "positions": [
                    {"price": Decimal("100.25")},
                ],
            }
        }
        result = _serialize(data)
        parsed = json.loads(result)
        assert parsed["portfolio"]["value"] == "10000.50"
        assert parsed["portfolio"]["positions"][0]["price"] == "100.25"

    def test_deserialize_dict(self) -> None:
        """Test deserializing a dict."""
        data = '{"key": "value"}'
        result = _deserialize(data)
        assert result == {"key": "value"}

    def test_decimal_encoder(self) -> None:
        """Test DecimalEncoder directly."""
        encoder = DecimalEncoder()
        result = encoder.default(Decimal("99.99"))
        assert result == "99.99"


# =============================================================================
# CacheManager Tests
# =============================================================================


class TestCacheManagerKeyGeneration:
    """Tests for CacheManager key generation."""

    def test_get_key_simple(self, cache_manager: CacheManager) -> None:
        """Test key generation for simple template."""
        key = cache_manager._get_key("regime")
        assert key == "market:regime:current"

    def test_get_key_with_params(self, cache_manager: CacheManager) -> None:
        """Test key generation with template parameters."""
        key = cache_manager._get_key("sector", sector="Technology")
        assert key == "market:sector:Technology"

    def test_get_key_user_specific(self, cache_manager: CacheManager) -> None:
        """Test key generation for user-specific data."""
        key = cache_manager._get_key("portfolio", user_id="user-123")
        assert key == "user:user-123:portfolio"

    def test_get_key_missing_param(self, cache_manager: CacheManager) -> None:
        """Test key generation fails with missing parameter."""
        with pytest.raises(ValueError, match="Missing required key parameter"):
            cache_manager._get_key("sector")  # Missing 'sector' param

    def test_get_key_unknown_config(self, cache_manager: CacheManager) -> None:
        """Test key generation fails for unknown config."""
        with pytest.raises(ValueError, match="Unknown cache config"):
            cache_manager._get_key("nonexistent")


class TestCacheManagerGet:
    """Tests for CacheManager.get()."""

    @pytest.mark.asyncio
    async def test_get_cache_hit(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get with cache hit."""
        cached_data = {"regime": "bull", "confidence": 0.95}
        mock_redis_client.get = AsyncMock(return_value=cached_data)

        result = await cache_manager.get("regime")

        assert result == cached_data
        mock_redis_client.get.assert_called_once_with("market:regime:current")

    @pytest.mark.asyncio
    async def test_get_cache_miss(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get with cache miss."""
        mock_redis_client.get = AsyncMock(return_value=None)

        result = await cache_manager.get("regime")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_with_params(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get with template parameters."""
        mock_redis_client.get = AsyncMock(return_value={"price": 150.0})

        result = await cache_manager.get("stock_info", symbol="AAPL")

        assert result == {"price": 150.0}
        mock_redis_client.get.assert_called_once_with("data:AAPL:info")

    @pytest.mark.asyncio
    async def test_get_error_handling(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get handles errors gracefully."""
        mock_redis_client.get = AsyncMock(side_effect=Exception("Redis error"))

        result = await cache_manager.get("regime")

        assert result is None


class TestCacheManagerSet:
    """Tests for CacheManager.set()."""

    @pytest.mark.asyncio
    async def test_set_basic(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test basic set operation."""
        data = {"regime": "bull", "confidence": 0.95}

        await cache_manager.set("regime", data)

        mock_redis_client.setex.assert_called_once()
        call_args = mock_redis_client.setex.call_args
        assert call_args[0][0] == "market:regime:current"
        assert call_args[0][1] == 21600  # 6 hours TTL

    @pytest.mark.asyncio
    async def test_set_with_ttl_override(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test set with TTL override."""
        data = {"regime": "bull"}

        await cache_manager.set("regime", data, ttl_override=3600)

        call_args = mock_redis_client.setex.call_args
        assert call_args[0][1] == 3600  # Overridden TTL

    @pytest.mark.asyncio
    async def test_set_with_params(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test set with template parameters."""
        data = {"value": 10000}

        await cache_manager.set("portfolio", data, user_id="user-123")

        call_args = mock_redis_client.setex.call_args
        assert call_args[0][0] == "user:user-123:portfolio"

    @pytest.mark.asyncio
    async def test_set_serializes_decimal(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test set properly serializes Decimal values."""
        data = {"price": Decimal("150.25")}

        await cache_manager.set("stock_info", data, symbol="AAPL")

        call_args = mock_redis_client.setex.call_args
        serialized = call_args[0][2]
        assert '"150.25"' in serialized

    @pytest.mark.asyncio
    async def test_set_error_raises(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test set raises errors."""
        mock_redis_client.setex = AsyncMock(side_effect=Exception("Redis error"))

        with pytest.raises(Exception, match="Redis error"):
            await cache_manager.set("regime", {"data": "value"})


class TestCacheManagerInvalidate:
    """Tests for CacheManager.invalidate()."""

    @pytest.mark.asyncio
    async def test_invalidate_basic(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test basic invalidate operation."""
        await cache_manager.invalidate("regime")

        mock_redis_client.delete.assert_called_once_with("market:regime:current")

    @pytest.mark.asyncio
    async def test_invalidate_with_params(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test invalidate with template parameters."""
        await cache_manager.invalidate("portfolio", user_id="user-123")

        mock_redis_client.delete.assert_called_once_with("user:user-123:portfolio")


class TestCacheManagerInvalidatePattern:
    """Tests for CacheManager.invalidate_pattern()."""

    @pytest.mark.asyncio
    async def test_invalidate_pattern_with_matches(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test invalidate pattern with matching keys."""
        mock_redis_client.client.keys = AsyncMock(
            return_value=["market:sector:Tech", "market:sector:Health"]
        )
        mock_redis_client.client.delete = AsyncMock(return_value=2)

        result = await cache_manager.invalidate_pattern("market:sector:*")

        assert result == 2
        mock_redis_client.client.keys.assert_called_once_with("market:sector:*")

    @pytest.mark.asyncio
    async def test_invalidate_pattern_no_matches(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test invalidate pattern with no matches."""
        mock_redis_client.client.keys = AsyncMock(return_value=[])

        result = await cache_manager.invalidate_pattern("nonexistent:*")

        assert result == 0

    @pytest.mark.asyncio
    async def test_invalidate_pattern_client_none(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test invalidate pattern with no connection."""
        mock_redis_client.client = None

        with pytest.raises(ConnectionError):
            await cache_manager.invalidate_pattern("market:*")


class TestCacheManagerWarmCache:
    """Tests for CacheManager.warm_cache()."""

    @pytest.mark.asyncio
    async def test_warm_cache(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test cache warming."""

        async def fetch_regime() -> dict:
            return {"regime": "bull", "confidence": 0.95}

        result = await cache_manager.warm_cache("regime", fetch_regime)

        assert result == {"regime": "bull", "confidence": 0.95}
        mock_redis_client.setex.assert_called_once()


class TestCacheManagerGetOrSet:
    """Tests for CacheManager.get_or_set()."""

    @pytest.mark.asyncio
    async def test_get_or_set_cache_hit(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get_or_set with cache hit."""
        cached_data = {"regime": "bull"}
        mock_redis_client.get = AsyncMock(return_value=cached_data)

        fetch_called = False

        async def fetch_regime() -> dict:
            nonlocal fetch_called
            fetch_called = True
            return {"regime": "bear"}

        result = await cache_manager.get_or_set("regime", fetch_regime)

        assert result == cached_data
        assert not fetch_called

    @pytest.mark.asyncio
    async def test_get_or_set_cache_miss(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get_or_set with cache miss."""
        mock_redis_client.get = AsyncMock(return_value=None)

        async def fetch_regime() -> dict:
            return {"regime": "bull", "confidence": 0.95}

        result = await cache_manager.get_or_set("regime", fetch_regime)

        assert result == {"regime": "bull", "confidence": 0.95}
        mock_redis_client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_set_with_params(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get_or_set with template parameters."""
        mock_redis_client.get = AsyncMock(return_value=None)

        async def fetch_portfolio() -> dict:
            return {"value": 10000}

        result = await cache_manager.get_or_set(
            "portfolio",
            fetch_portfolio,
            user_id="user-123",
        )

        assert result == {"value": 10000}
        call_args = mock_redis_client.setex.call_args
        assert call_args[0][0] == "user:user-123:portfolio"


class TestCacheManagerTTL:
    """Tests for CacheManager.get_ttl()."""

    @pytest.mark.asyncio
    async def test_get_ttl_exists(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get_ttl for existing key."""
        mock_redis_client.client.ttl = AsyncMock(return_value=3600)

        result = await cache_manager.get_ttl("regime")

        assert result == 3600

    @pytest.mark.asyncio
    async def test_get_ttl_not_exists(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get_ttl for non-existent key."""
        mock_redis_client.client.ttl = AsyncMock(return_value=-2)

        result = await cache_manager.get_ttl("regime")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_ttl_no_ttl_set(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get_ttl for key with no TTL."""
        mock_redis_client.client.ttl = AsyncMock(return_value=-1)

        result = await cache_manager.get_ttl("regime")

        assert result is None


class TestCacheManagerExists:
    """Tests for CacheManager.exists()."""

    @pytest.mark.asyncio
    async def test_exists_true(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test exists returns True for existing key."""
        mock_redis_client.client.exists = AsyncMock(return_value=1)

        result = await cache_manager.exists("regime")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test exists returns False for non-existent key."""
        mock_redis_client.client.exists = AsyncMock(return_value=0)

        result = await cache_manager.exists("regime")

        assert result is False


class TestCacheManagerRefreshTTL:
    """Tests for CacheManager.refresh_ttl()."""

    @pytest.mark.asyncio
    async def test_refresh_ttl_success(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test refresh_ttl for existing key."""
        mock_redis_client.client.expire = AsyncMock(return_value=True)

        result = await cache_manager.refresh_ttl("regime")

        assert result is True
        mock_redis_client.client.expire.assert_called_once_with(
            "market:regime:current", 21600
        )

    @pytest.mark.asyncio
    async def test_refresh_ttl_not_exists(
        self,
        cache_manager: CacheManager,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test refresh_ttl for non-existent key."""
        mock_redis_client.client.expire = AsyncMock(return_value=False)

        result = await cache_manager.refresh_ttl("regime")

        assert result is False


class TestCacheManagerRegisterConfig:
    """Tests for CacheManager.register_config()."""

    def test_register_custom_config(
        self,
        cache_manager: CacheManager,
    ) -> None:
        """Test registering custom config."""
        custom_config = CacheConfig(
            tier=CacheTier.TIER1_SHARED,
            ttl_seconds=1800,
            key_template="custom:{key}",
        )

        cache_manager.register_config("custom", custom_config)

        assert "custom" in cache_manager._configs
        assert cache_manager._configs["custom"].ttl_seconds == 1800


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateCacheManager:
    """Tests for create_cache_manager factory."""

    @pytest.mark.asyncio
    async def test_create_with_host_port(self) -> None:
        """Test creating cache manager with host:port URL."""
        with patch("shared.utils.cache_strategy.RedisClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock()
            mock_client.return_value = mock_instance

            result = await create_cache_manager("redis://localhost:6379")

            assert isinstance(result, CacheManager)
            mock_client.assert_called_once_with(host="localhost", port=6379)

    @pytest.mark.asyncio
    async def test_create_with_host_only(self) -> None:
        """Test creating cache manager with host only URL."""
        with patch("shared.utils.cache_strategy.RedisClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock()
            mock_client.return_value = mock_instance

            result = await create_cache_manager("redis://myredis")

            assert isinstance(result, CacheManager)
            mock_client.assert_called_once_with(host="myredis", port=6379)

    @pytest.mark.asyncio
    async def test_create_with_default_port(self) -> None:
        """Test creating cache manager uses default port."""
        with patch("shared.utils.cache_strategy.RedisClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.connect = AsyncMock()
            mock_client.return_value = mock_instance

            await create_cache_manager("redis://redis-host")

            mock_client.assert_called_once_with(host="redis-host", port=6379)
