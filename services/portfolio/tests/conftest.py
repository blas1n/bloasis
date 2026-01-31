"""
Pytest configuration and fixtures for Portfolio Service tests.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def setup_test_env() -> None:
    """Set up test environment variables."""
    os.environ.setdefault("SERVICE_NAME", "portfolio-test")
    os.environ.setdefault("GRPC_PORT", "50057")
    os.environ.setdefault("REDIS_HOST", "localhost")
    os.environ.setdefault("REDIS_PORT", "6379")
    os.environ.setdefault("REDPANDA_BROKERS", "localhost:9092")
    os.environ.setdefault(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/bloasis_test"
    )
