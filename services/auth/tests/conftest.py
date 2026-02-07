"""
Pytest configuration and fixtures for Auth Service tests.
"""

import os

import pytest

from src.jwt_handler import JWTHandler

# Use a 32+ byte secret key for JWT tests to avoid InsecureKeyLengthWarning
JWT_TEST_SECRET = "test-secret-key-for-jwt-testing-minimum-32-bytes-required"


@pytest.fixture
def jwt_secret() -> str:
    """Provide a secure-length JWT secret for testing."""
    return JWT_TEST_SECRET


@pytest.fixture
def jwt_handler(jwt_secret: str) -> JWTHandler:
    """Create a JWTHandler with secure test secret."""
    return JWTHandler(secret_key=jwt_secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def setup_test_env() -> None:
    """Set up test environment variables."""
    os.environ.setdefault("SERVICE_NAME", "auth-test")
    os.environ.setdefault("GRPC_PORT", "50059")
    os.environ.setdefault("REDIS_HOST", "localhost")
    os.environ.setdefault("REDIS_PORT", "6379")
    os.environ.setdefault("USER_SERVICE_HOST", "localhost")
    os.environ.setdefault("USER_SERVICE_PORT", "50058")
    os.environ.setdefault("JWT_SECRET_KEY", JWT_TEST_SECRET)
    os.environ.setdefault("JWT_ALGORITHM", "HS256")
    os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")
    os.environ.setdefault("CONSUL_ENABLED", "false")
