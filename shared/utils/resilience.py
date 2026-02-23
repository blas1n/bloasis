"""Resilience patterns for inter-service communication.

Provides:
- grpc_retry: Retry decorator for gRPC calls with exponential backoff
- is_retryable_grpc_error: Predicate for retryable gRPC status codes
- with_timeout: Timeout wrapper for async coroutines
"""

import asyncio
import logging

import grpc
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# gRPC status codes that indicate transient failures worth retrying
RETRYABLE_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
    grpc.StatusCode.RESOURCE_EXHAUSTED,
    grpc.StatusCode.ABORTED,
}


def is_retryable_grpc_error(exception: BaseException) -> bool:
    """Check if a gRPC error is retryable (transient).

    Args:
        exception: The exception to check

    Returns:
        True if the error is transient and worth retrying
    """
    if isinstance(exception, grpc.aio.AioRpcError):
        return exception.code() in RETRYABLE_CODES
    return isinstance(exception, (ConnectionError, TimeoutError, OSError))


# Decorator for gRPC calls: 3 attempts with exponential backoff (0.5s, 1s, 2s)
grpc_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    retry=retry_if_exception(is_retryable_grpc_error),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


async def with_timeout(coro, timeout_seconds: float = 30.0):
    """Execute an async coroutine with a timeout.

    Args:
        coro: Awaitable coroutine
        timeout_seconds: Maximum execution time in seconds

    Returns:
        Result of the coroutine

    Raises:
        asyncio.TimeoutError: If the coroutine exceeds the timeout
    """
    return await asyncio.wait_for(coro, timeout=timeout_seconds)
