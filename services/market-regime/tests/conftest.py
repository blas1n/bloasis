"""
Pytest configuration and fixtures for Market Regime Service tests.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def setup_test_env() -> None:
    """Set up test environment variables."""
    os.environ.setdefault("SERVICE_NAME", "market-regime-test")
    os.environ.setdefault("GRPC_PORT", "50051")
    os.environ.setdefault("REDIS_HOST", "localhost")
    os.environ.setdefault("REDIS_PORT", "6379")
    os.environ.setdefault("REDPANDA_BROKERS", "localhost:9092")
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/bloasis_test"
    )
    os.environ.setdefault("ANTHROPIC_API_KEY", "test_anthropic_key_for_unit_tests")
