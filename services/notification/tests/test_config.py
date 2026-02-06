"""Tests for configuration."""

import pytest

from src.config import Settings, config


class TestSettings:
    """Test cases for Settings class."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        settings = Settings()

        assert settings.service_name == "notification"
        assert settings.ws_host == "0.0.0.0"
        assert settings.ws_port == 8000
        assert settings.redpanda_brokers == "redpanda:9092"
        assert settings.log_level == "INFO"

    def test_config_singleton(self) -> None:
        """Test that config is instantiated."""
        assert config is not None
        assert isinstance(config, Settings)

    def test_custom_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test custom configuration from environment."""
        monkeypatch.setenv("SERVICE_NAME", "custom-notification")
        monkeypatch.setenv("WS_HOST", "127.0.0.1")
        monkeypatch.setenv("WS_PORT", "9000")
        monkeypatch.setenv("REDPANDA_BROKERS", "broker1:9092,broker2:9092")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        settings = Settings()

        assert settings.service_name == "custom-notification"
        assert settings.ws_host == "127.0.0.1"
        assert settings.ws_port == 9000
        assert settings.redpanda_brokers == "broker1:9092,broker2:9092"
        assert settings.log_level == "DEBUG"
