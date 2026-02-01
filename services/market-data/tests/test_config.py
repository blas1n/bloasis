"""Tests for service configuration."""


from src.config import ServiceConfig, config


class TestServiceConfig:
    """Tests for ServiceConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        cfg = ServiceConfig()
        assert cfg.service_name == "market-data"
        assert cfg.grpc_port == 50053
        assert cfg.redis_host == "redis"
        assert cfg.redis_port == 6379
        assert cfg.cache_ttl == 300
        assert cfg.consul_host == "consul"
        assert cfg.consul_port == 8500
        assert cfg.consul_enabled is True

    def test_config_singleton(self) -> None:
        """Test that config module exports a config instance."""
        assert config is not None
        assert isinstance(config, ServiceConfig)
        assert config.service_name == "market-data"
