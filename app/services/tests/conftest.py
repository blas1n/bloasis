"""Shared fixtures for service-layer tests."""

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def mock_postgres():
    return AsyncMock()


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.analyze = AsyncMock(return_value={})
    return llm


@pytest.fixture
def mock_user_repo():
    return AsyncMock()
