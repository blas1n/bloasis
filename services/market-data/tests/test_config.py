"""Tests for service configuration."""

import os
from unittest.mock import patch

from src.config import ServiceConfig


class TestServiceConfig:
    """Tests for ServiceConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values when no env vars set."""
        # Create a new config with clean environment
        with patch.dict(os.environ, {}, clear=True):
            cfg = ServiceConfig(_env_file=None)  # Ignore .env file
            assert cfg.service_name == "market-data"
            assert cfg.grpc_port == 50053
            assert cfg.redis_host == "redis"
            assert cfg.redis_port == 6379
            assert cfg.cache_ttl == 300
            assert cfg.consul_host == "consul"
            assert cfg.consul_port == 8500
            assert cfg.consul_enabled is True

    def test_config_loads_from_env(self) -> None:
        """Test that config loads values from environment variables."""
        with patch.dict(
            os.environ,
            {
                "SERVICE_NAME": "test-service",
                "GRPC_PORT": "12345",
                "REDIS_HOST": "redis-test",
            },
            clear=True,
        ):
            cfg = ServiceConfig(_env_file=None)
            assert cfg.service_name == "test-service"
            assert cfg.grpc_port == 12345
            assert cfg.redis_host == "redis-test"

    def test_config_is_service_config(self) -> None:
        """Test that config module exports a ServiceConfig instance."""
        from src.config import config

        assert config is not None
        assert isinstance(config, ServiceConfig)
