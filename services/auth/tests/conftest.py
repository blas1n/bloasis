"""
Pytest configuration and fixtures for Auth Service tests.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def setup_test_env() -> None:
    """Set up test environment variables."""
    os.environ.setdefault("SERVICE_NAME", "auth-test")
    os.environ.setdefault("GRPC_PORT", "50059")
    os.environ.setdefault("REDIS_HOST", "localhost")
    os.environ.setdefault("REDIS_PORT", "6379")
    os.environ.setdefault("USER_SERVICE_HOST", "localhost")
    os.environ.setdefault("USER_SERVICE_PORT", "50058")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only-32bytes!")
    os.environ.setdefault("JWT_ALGORITHM", "HS256")
    os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
    os.environ.setdefault("CONSUL_ENABLED", "false")
