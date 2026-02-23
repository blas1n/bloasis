"""Tests for resilience utilities."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest
from shared.utils.resilience import (
    RETRYABLE_CODES,
    grpc_retry,
    is_retryable_grpc_error,
    with_timeout,
)


class TestIsRetryableGrpcError:
    """Tests for is_retryable_grpc_error predicate."""

    def test_retryable_unavailable(self):
        """UNAVAILABLE is retryable."""
        error = MagicMock(spec=grpc.aio.AioRpcError)
        error.code.return_value = grpc.StatusCode.UNAVAILABLE
        assert is_retryable_grpc_error(error) is True

    def test_retryable_deadline_exceeded(self):
        """DEADLINE_EXCEEDED is retryable."""
        error = MagicMock(spec=grpc.aio.AioRpcError)
        error.code.return_value = grpc.StatusCode.DEADLINE_EXCEEDED
        assert is_retryable_grpc_error(error) is True

    def test_retryable_resource_exhausted(self):
        """RESOURCE_EXHAUSTED is retryable."""
        error = MagicMock(spec=grpc.aio.AioRpcError)
        error.code.return_value = grpc.StatusCode.RESOURCE_EXHAUSTED
        assert is_retryable_grpc_error(error) is True

    def test_retryable_aborted(self):
        """ABORTED is retryable."""
        error = MagicMock(spec=grpc.aio.AioRpcError)
        error.code.return_value = grpc.StatusCode.ABORTED
        assert is_retryable_grpc_error(error) is True

    def test_not_retryable_not_found(self):
        """NOT_FOUND is not retryable."""
        error = MagicMock(spec=grpc.aio.AioRpcError)
        error.code.return_value = grpc.StatusCode.NOT_FOUND
        assert is_retryable_grpc_error(error) is False

    def test_not_retryable_invalid_argument(self):
        """INVALID_ARGUMENT is not retryable."""
        error = MagicMock(spec=grpc.aio.AioRpcError)
        error.code.return_value = grpc.StatusCode.INVALID_ARGUMENT
        assert is_retryable_grpc_error(error) is False

    def test_retryable_connection_error(self):
        """ConnectionError is retryable."""
        assert is_retryable_grpc_error(ConnectionError("failed")) is True

    def test_retryable_timeout_error(self):
        """TimeoutError is retryable."""
        assert is_retryable_grpc_error(TimeoutError("timed out")) is True

    def test_retryable_os_error(self):
        """OSError is retryable."""
        assert is_retryable_grpc_error(OSError("network error")) is True

    def test_not_retryable_value_error(self):
        """ValueError is not retryable."""
        assert is_retryable_grpc_error(ValueError("bad value")) is False

    def test_retryable_codes_set(self):
        """Verify the RETRYABLE_CODES set contains expected codes."""
        assert grpc.StatusCode.UNAVAILABLE in RETRYABLE_CODES
        assert grpc.StatusCode.DEADLINE_EXCEEDED in RETRYABLE_CODES
        assert grpc.StatusCode.RESOURCE_EXHAUSTED in RETRYABLE_CODES
        assert grpc.StatusCode.ABORTED in RETRYABLE_CODES
        assert len(RETRYABLE_CODES) == 4


class TestGrpcRetry:
    """Tests for grpc_retry decorator."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_first_try(self):
        """Test function succeeds on first try."""
        mock_fn = AsyncMock(return_value="success")

        @grpc_retry
        async def call():
            return await mock_fn()

        result = await call()

        assert result == "success"
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_transient_error(self):
        """Test function retries and succeeds after ConnectionError."""
        call_count = 0

        @grpc_retry
        async def call():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient")
            return "success"

        result = await call()

        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        """Test function raises after exhausting retries."""

        @grpc_retry
        async def call():
            raise ConnectionError("always failing")

        with pytest.raises(ConnectionError):
            await call()

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_error(self):
        """Test no retry on non-retryable errors."""
        call_count = 0

        @grpc_retry
        async def call():
            nonlocal call_count
            call_count += 1
            raise ValueError("non-retryable")

        with pytest.raises(ValueError):
            await call()

        assert call_count == 1  # No retry


class TestWithTimeout:
    """Tests for with_timeout utility."""

    @pytest.mark.asyncio
    async def test_timeout_success(self):
        """Test coroutine completes within timeout."""

        async def fast():
            return "done"

        result = await with_timeout(fast(), timeout_seconds=5.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_timeout_exceeds(self):
        """Test coroutine exceeds timeout."""

        async def slow():
            await asyncio.sleep(10)

        with pytest.raises(asyncio.TimeoutError):
            await with_timeout(slow(), timeout_seconds=0.01)

    @pytest.mark.asyncio
    async def test_timeout_default(self):
        """Test default timeout value."""

        async def fast():
            return "done"

        result = await with_timeout(fast())
        assert result == "done"
