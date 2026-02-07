"""
Pytest configuration and fixtures for Market Data Service tests.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def setup_test_env() -> None:
    """Set up test environment variables."""
    os.environ.setdefault("SERVICE_NAME", "market-data-test")
    os.environ.setdefault("GRPC_PORT", "50053")
    os.environ.setdefault("REDIS_HOST", "localhost")
    os.environ.setdefault("REDIS_PORT", "6379")
    os.environ.setdefault("CACHE_TTL", "300")
    os.environ.setdefault("POSTGRES_ENABLED", "false")
    os.environ.setdefault("CONSUL_ENABLED", "false")
    os.environ.setdefault("CONSUL_HOST", "localhost")
    os.environ.setdefault("CONSUL_PORT", "8500")
