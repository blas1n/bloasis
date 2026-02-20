"""Pytest fixtures for E2E integration tests.

This module provides comprehensive fixtures for integration testing including:
- Docker Compose setup utilities
- gRPC channel fixtures (session-scoped)
- Service stub fixtures
- Mock data generators
- Cleanup utilities
- Redpanda consumer fixture for event testing
"""

import asyncio
import json
import os
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, AsyncGenerator, Callable, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import consul
import grpc
import grpc.aio
import pytest
import pytest_asyncio
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient

# ============================================================================
# Environment Configuration
# ============================================================================

# Infrastructure hosts
CONSUL_HOST = os.getenv("CONSUL_HOST", "consul")
CONSUL_PORT = int(os.getenv("CONSUL_PORT", "8500"))
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDPANDA_BROKERS = os.getenv("REDPANDA_BROKERS", "redpanda:9092")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/bloasis_test",
)

# Service hosts and ports
SERVICE_PORTS = {
    "market-regime": (os.getenv("MARKET_REGIME_HOST", "market-regime"), 50051),
    "market-data": (os.getenv("MARKET_DATA_HOST", "market-data"), 50052),
    "classification": (os.getenv("CLASSIFICATION_HOST", "classification"), 50053),
    "strategy": (os.getenv("STRATEGY_HOST", "strategy"), 50054),
    "backtesting": (os.getenv("BACKTESTING_HOST", "backtesting"), 50055),
    "risk-committee": (os.getenv("RISK_COMMITTEE_HOST", "risk-committee"), 50057),
    "executor": (os.getenv("EXECUTOR_HOST", "executor"), 50058),
    "portfolio": (os.getenv("PORTFOLIO_HOST", "portfolio"), 50059),
    "user": (os.getenv("USER_HOST", "user"), 50061),
    "auth": (os.getenv("AUTH_HOST", "auth"), 50062),
}


# ============================================================================
# Infrastructure Wait Functions
# ============================================================================


def wait_for_consul(timeout: int = 30) -> bool:
    """Wait for Consul to be ready.

    Args:
        timeout: Maximum time to wait in seconds.

    Returns:
        True if Consul is ready, False otherwise.
    """
    client = consul.Consul(host=CONSUL_HOST, port=CONSUL_PORT)
    start = time.time()

    while time.time() - start < timeout:
        try:
            leader = client.status.leader()
            if leader:
                return True
        except Exception:
            pass
        time.sleep(1)

    return False


def wait_for_services(timeout: int = 60) -> bool:
    """Wait for services to register with Consul.

    Args:
        timeout: Maximum time to wait in seconds.

    Returns:
        True if all required services are registered, False otherwise.
    """
    client = consul.Consul(host=CONSUL_HOST, port=CONSUL_PORT)
    start = time.time()

    required_services = ["market-regime", "portfolio", "market-data"]

    while time.time() - start < timeout:
        try:
            services = client.agent.services()
            registered = [s.get("Service") for s in services.values()]

            if all(svc in registered for svc in required_services):
                return True
        except Exception:
            pass
        time.sleep(2)

    return False


def wait_for_redpanda(timeout: int = 30) -> bool:
    """Wait for Redpanda to be ready.

    Args:
        timeout: Maximum time to wait in seconds.

    Returns:
        True if Redpanda is ready, False otherwise.
    """

    async def check() -> bool:
        try:
            admin = AIOKafkaAdminClient(bootstrap_servers=REDPANDA_BROKERS)
            await asyncio.wait_for(admin.start(), timeout=timeout)
            await admin.close()
            return True
        except Exception:
            return False

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(check())


def wait_for_grpc_service(host: str, port: int, timeout: int = 30) -> bool:
    """Wait for a gRPC service to be ready.

    Args:
        host: Service host.
        port: Service port.
        timeout: Maximum time to wait in seconds.

    Returns:
        True if service is ready, False otherwise.
    """
    channel = grpc.insecure_channel(f"{host}:{port}")
    try:
        grpc.channel_ready_future(channel).result(timeout=timeout)
        return True
    except grpc.FutureTimeoutError:
        return False
    finally:
        channel.close()


# ============================================================================
# Consul Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def consul_available() -> Generator[bool, None, None]:
    """Check if Consul is available.

    Yields:
        True if Consul is available, False otherwise.
    """
    available = wait_for_consul(timeout=5)
    yield available


@pytest.fixture(scope="session")
def consul_client(consul_available: bool) -> Generator[consul.Consul, None, None]:
    """Create Consul client for testing.

    Args:
        consul_available: Whether Consul is available.

    Yields:
        Consul client instance.
    """
    if not consul_available:
        pytest.skip("Consul not available")

    client = consul.Consul(host=CONSUL_HOST, port=CONSUL_PORT)
    yield client


@pytest.fixture(scope="session")
def services_registered(consul_available: bool) -> Generator[bool, None, None]:
    """Check if required services are registered with Consul.

    Args:
        consul_available: Whether Consul is available.

    Yields:
        True if all required services are registered, False otherwise.
    """
    if not consul_available:
        yield False
        return

    registered = wait_for_services(timeout=10)
    yield registered


# ============================================================================
# Redpanda Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def redpanda_available() -> Generator[bool, None, None]:
    """Check if Redpanda is available.

    Yields:
        True if Redpanda is available, False otherwise.
    """
    available = wait_for_redpanda(timeout=10)
    yield available


@pytest_asyncio.fixture
async def redpanda_producer(
    redpanda_available: bool,
) -> AsyncGenerator[AIOKafkaProducer, None]:
    """Create Kafka producer for testing.

    Args:
        redpanda_available: Whether Redpanda is available.

    Yields:
        AIOKafkaProducer instance.
    """
    if not redpanda_available:
        pytest.skip("Redpanda not available")

    producer = AIOKafkaProducer(
        bootstrap_servers=REDPANDA_BROKERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    await producer.start()
    yield producer
    await producer.stop()


@pytest_asyncio.fixture
async def redpanda_consumer_factory(
    redpanda_available: bool,
) -> AsyncGenerator[Callable[..., AIOKafkaConsumer], None]:
    """Factory for creating Redpanda consumers with specific topics.

    Args:
        redpanda_available: Whether Redpanda is available.

    Yields:
        Factory function for creating consumers.
    """
    if not redpanda_available:
        pytest.skip("Redpanda not available")

    consumers: list[AIOKafkaConsumer] = []

    async def create_consumer(
        topics: list[str],
        group_id: str,
    ) -> AIOKafkaConsumer:
        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=REDPANDA_BROKERS,
            group_id=group_id,
            auto_offset_reset="latest",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            consumer_timeout_ms=5000,
        )
        await consumer.start()
        consumers.append(consumer)
        return consumer

    yield create_consumer

    # Cleanup all consumers
    for consumer in consumers:
        await consumer.stop()


# ============================================================================
# gRPC Channel Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def grpc_channel_factory() -> Generator[Callable[[str, int], grpc.Channel], None, None]:
    """Factory for creating gRPC channels.

    Yields:
        Factory function for creating gRPC channels.
    """
    channels: list[grpc.Channel] = []

    def create_channel(host: str, port: int, timeout: int = 10) -> grpc.Channel:
        channel = grpc.insecure_channel(f"{host}:{port}")
        try:
            grpc.channel_ready_future(channel).result(timeout=timeout)
        except grpc.FutureTimeoutError:
            channel.close()
            raise ConnectionError(f"Failed to connect to {host}:{port}")
        channels.append(channel)
        return channel

    yield create_channel

    # Cleanup
    for channel in channels:
        channel.close()


@pytest_asyncio.fixture
async def async_grpc_channel_factory() -> AsyncGenerator[
    Callable[[str, int], grpc.aio.Channel], None
]:
    """Factory for creating async gRPC channels.

    Yields:
        Factory function for creating async gRPC channels.
    """
    channels: list[grpc.aio.Channel] = []

    async def create_channel(host: str, port: int) -> grpc.aio.Channel:
        channel = grpc.aio.insecure_channel(
            f"{host}:{port}",
            options=[
                ("grpc.max_send_message_length", 50 * 1024 * 1024),
                ("grpc.max_receive_message_length", 50 * 1024 * 1024),
                ("grpc.keepalive_time_ms", 10000),
            ],
        )
        channels.append(channel)
        return channel

    yield create_channel

    # Cleanup
    for channel in channels:
        await channel.close()


# ============================================================================
# Service Stub Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def market_regime_channel() -> Generator[grpc.Channel, None, None]:
    """Create gRPC channel to Market Regime service.

    Yields:
        gRPC channel to Market Regime service.
    """
    host, port = SERVICE_PORTS["market-regime"]
    channel = grpc.insecure_channel(f"{host}:{port}")

    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        pytest.skip("Market Regime gRPC service not available")

    yield channel
    channel.close()


@pytest.fixture(scope="module")
def market_regime_stub(market_regime_channel: grpc.Channel) -> Any:
    """Create Market Regime service stub.

    Args:
        market_regime_channel: gRPC channel to Market Regime service.

    Returns:
        Market Regime service stub.
    """
    try:
        from shared.generated import market_regime_pb2_grpc

        return market_regime_pb2_grpc.MarketRegimeServiceStub(market_regime_channel)
    except ImportError:
        pytest.skip("Proto files not generated - run 'buf generate'")


@pytest.fixture(scope="module")
def strategy_channel() -> Generator[grpc.Channel, None, None]:
    """Create gRPC channel to Strategy service.

    Yields:
        gRPC channel to Strategy service.
    """
    host, port = SERVICE_PORTS["strategy"]
    channel = grpc.insecure_channel(f"{host}:{port}")

    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        pytest.skip("Strategy gRPC service not available")

    yield channel
    channel.close()


@pytest.fixture(scope="module")
def strategy_stub(strategy_channel: grpc.Channel) -> Any:
    """Create Strategy service stub.

    Args:
        strategy_channel: gRPC channel to Strategy service.

    Returns:
        Strategy service stub.
    """
    try:
        from shared.generated import strategy_pb2_grpc

        return strategy_pb2_grpc.StrategyServiceStub(strategy_channel)
    except ImportError:
        pytest.skip("Proto files not generated - run 'buf generate'")


@pytest.fixture(scope="module")
def backtesting_channel() -> Generator[grpc.Channel, None, None]:
    """Create gRPC channel to Backtesting service.

    Yields:
        gRPC channel to Backtesting service.
    """
    host, port = SERVICE_PORTS["backtesting"]
    channel = grpc.insecure_channel(f"{host}:{port}")

    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        pytest.skip("Backtesting gRPC service not available")

    yield channel
    channel.close()


@pytest.fixture(scope="module")
def backtesting_stub(backtesting_channel: grpc.Channel) -> Any:
    """Create Backtesting service stub.

    Args:
        backtesting_channel: gRPC channel to Backtesting service.

    Returns:
        Backtesting service stub.
    """
    try:
        from shared.generated import backtesting_pb2_grpc

        return backtesting_pb2_grpc.BacktestingServiceStub(backtesting_channel)
    except ImportError:
        pytest.skip("Proto files not generated - run 'buf generate'")


@pytest.fixture(scope="module")
def risk_committee_channel() -> Generator[grpc.Channel, None, None]:
    """Create gRPC channel to Risk Committee service.

    Yields:
        gRPC channel to Risk Committee service.
    """
    host, port = SERVICE_PORTS["risk-committee"]
    channel = grpc.insecure_channel(f"{host}:{port}")

    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        pytest.skip("Risk Committee gRPC service not available")

    yield channel
    channel.close()


@pytest.fixture(scope="module")
def risk_committee_stub(risk_committee_channel: grpc.Channel) -> Any:
    """Create Risk Committee service stub.

    Args:
        risk_committee_channel: gRPC channel to Risk Committee service.

    Returns:
        Risk Committee service stub.
    """
    try:
        from shared.generated import risk_committee_pb2_grpc

        return risk_committee_pb2_grpc.RiskCommitteeServiceStub(risk_committee_channel)
    except ImportError:
        pytest.skip("Proto files not generated - run 'buf generate'")


@pytest.fixture(scope="module")
def executor_channel() -> Generator[grpc.Channel, None, None]:
    """Create gRPC channel to Executor service.

    Yields:
        gRPC channel to Executor service.
    """
    host, port = SERVICE_PORTS["executor"]
    channel = grpc.insecure_channel(f"{host}:{port}")

    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        pytest.skip("Executor gRPC service not available")

    yield channel
    channel.close()


@pytest.fixture(scope="module")
def executor_stub(executor_channel: grpc.Channel) -> Any:
    """Create Executor service stub.

    Args:
        executor_channel: gRPC channel to Executor service.

    Returns:
        Executor service stub.
    """
    try:
        from shared.generated import executor_pb2_grpc

        return executor_pb2_grpc.ExecutorServiceStub(executor_channel)
    except ImportError:
        pytest.skip("Proto files not generated - run 'buf generate'")


@pytest.fixture(scope="module")
def portfolio_channel() -> Generator[grpc.Channel, None, None]:
    """Create gRPC channel to Portfolio service.

    Yields:
        gRPC channel to Portfolio service.
    """
    host, port = SERVICE_PORTS["portfolio"]
    channel = grpc.insecure_channel(f"{host}:{port}")

    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        pytest.skip("Portfolio gRPC service not available")

    yield channel
    channel.close()


@pytest.fixture(scope="module")
def portfolio_stub(portfolio_channel: grpc.Channel) -> Any:
    """Create Portfolio service stub.

    Args:
        portfolio_channel: gRPC channel to Portfolio service.

    Returns:
        Portfolio service stub.
    """
    try:
        from shared.generated import portfolio_pb2_grpc

        return portfolio_pb2_grpc.PortfolioServiceStub(portfolio_channel)
    except ImportError:
        pytest.skip("Proto files not generated - run 'buf generate'")


@pytest.fixture(scope="module")
def auth_channel() -> Generator[grpc.Channel, None, None]:
    """Create gRPC channel to Auth service.

    Yields:
        gRPC channel to Auth service.
    """
    host, port = SERVICE_PORTS["auth"]
    channel = grpc.insecure_channel(f"{host}:{port}")

    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        pytest.skip("Auth gRPC service not available")

    yield channel
    channel.close()


@pytest.fixture(scope="module")
def auth_stub(auth_channel: grpc.Channel) -> Any:
    """Create Auth service stub.

    Args:
        auth_channel: gRPC channel to Auth service.

    Returns:
        Auth service stub.
    """
    try:
        from shared.generated import auth_pb2_grpc

        return auth_pb2_grpc.AuthServiceStub(auth_channel)
    except ImportError:
        pytest.skip("Proto files not generated - run 'buf generate'")


# ============================================================================
# Mock Data Generators
# ============================================================================


@pytest.fixture
def mock_user_data() -> dict[str, Any]:
    """Generate mock user data for testing.

    Returns:
        Mock user data dictionary.
    """
    return {
        "user_id": "test-user-001",
        "email": "test@example.com",
        "password": "test_password_123",
        "profile_type": "moderate",
        "risk_tolerance": 0.5,
    }


@pytest.fixture
def mock_market_regime_data() -> dict[str, Any]:
    """Generate mock market regime data.

    Returns:
        Mock market regime data dictionary.
    """
    return {
        "regime": "bull",
        "confidence": 0.85,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "trigger": "baseline",
    }


@pytest.fixture
def mock_strategy_data() -> dict[str, Any]:
    """Generate mock strategy data.

    Returns:
        Mock strategy data dictionary.
    """
    return {
        "user_id": "test-user-001",
        "strategy_id": "strategy_test_001",
        "symbols": ["AAPL", "MSFT", "GOOGL"],
        "regime": "bull",
        "stock_picks": [
            {
                "symbol": "AAPL",
                "sector": "Technology",
                "final_score": 85.5,
                "rank": 1,
            },
            {
                "symbol": "MSFT",
                "sector": "Technology",
                "final_score": 82.3,
                "rank": 2,
            },
        ],
    }


@pytest.fixture
def mock_backtest_metrics() -> dict[str, Any]:
    """Generate mock backtest metrics.

    Returns:
        Mock backtest metrics dictionary.
    """
    return {
        "sharpe_ratio": 1.5,
        "max_drawdown": 0.15,
        "win_rate": 0.58,
        "total_return": 0.25,
        "sortino_ratio": 1.8,
        "profit_factor": 1.6,
    }


@pytest.fixture
def mock_order_data() -> dict[str, Any]:
    """Generate mock order data.

    Returns:
        Mock order data dictionary.
    """
    return {
        "user_id": "test-user-001",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 10.0,
        "order_type": "market",
        "risk_approval_id": "approval_001",
    }


@pytest.fixture
def mock_portfolio_data() -> dict[str, Any]:
    """Generate mock portfolio data.

    Returns:
        Mock portfolio data dictionary.
    """
    return {
        "user_id": "test-user-001",
        "total_value": "100000.00",
        "cash_balance": "50000.00",
        "invested_value": "50000.00",
        "total_return": 5.5,
        "positions": [
            {
                "symbol": "AAPL",
                "quantity": 50,
                "avg_cost": "150.00",
                "current_price": "165.00",
                "unrealized_pnl": "750.00",
            },
        ],
    }


# ============================================================================
# Event Fixtures
# ============================================================================


@pytest.fixture
def mock_regime_change_event() -> dict[str, Any]:
    """Generate mock regime change event.

    Returns:
        Mock regime change event dictionary.
    """
    return {
        "event_id": "event-test-001",
        "event_type": "regime_change",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "previous_regime": "sideways",
        "new_regime": "bull",
        "confidence": 0.90,
        "priority": 3,  # HIGH
    }


@pytest.fixture
def mock_trade_execution_event() -> dict[str, Any]:
    """Generate mock trade execution event.

    Returns:
        Mock trade execution event dictionary.
    """
    return {
        "event_id": "event-test-002",
        "event_type": "trade_executed",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_id": "test-user-001",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 10.0,
        "price": 165.50,
        "order_id": "order-test-001",
    }


# ============================================================================
# Cleanup Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def cleanup_redis() -> AsyncGenerator[Callable[[str], None], None]:
    """Fixture for cleaning up Redis test data.

    Yields:
        Cleanup function that accepts key patterns.
    """
    keys_to_delete: list[str] = []

    def register_key(key: str) -> None:
        keys_to_delete.append(key)

    yield register_key

    # Cleanup: Delete registered keys
    try:
        from shared.utils import RedisClient

        redis_client = RedisClient(host=REDIS_HOST, port=REDIS_PORT)
        await redis_client.connect()
        for key in keys_to_delete:
            await redis_client.delete(key)
        await redis_client.close()
    except Exception:
        pass  # Cleanup is best-effort


@pytest.fixture(scope="session", autouse=True)
def setup_integration_environment(
    consul_available: bool,
    services_registered: bool,
) -> Generator[None, None, None]:
    """Setup integration test environment.

    This fixture runs automatically for all integration tests.
    It skips tests if Consul or services are not available.

    Args:
        consul_available: Whether Consul is available.
        services_registered: Whether required services are registered.
    """
    if not consul_available:
        pytest.skip("Consul not available - skipping integration tests")

    if not services_registered:
        pytest.skip("Services not registered with Consul - skipping integration tests")

    yield


# ============================================================================
# External API Mocks
# ============================================================================


@pytest.fixture
def mock_yfinance() -> Generator[MagicMock, None, None]:
    """Mock yfinance library for market data tests.

    Yields:
        Mock yfinance module.
    """
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.history.return_value = MagicMock()
        mock_instance.info = {
            "symbol": "AAPL",
            "shortName": "Apple Inc.",
            "sector": "Technology",
            "marketCap": 3000000000000,
        }
        mock_ticker.return_value = mock_instance
        yield mock_ticker


@pytest.fixture
def mock_alpaca_client() -> Generator[MagicMock, None, None]:
    """Mock Alpaca trading client.

    Yields:
        Mock Alpaca client.
    """
    with patch("alpaca.trading.TradingClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.submit_order = AsyncMock(
            return_value=MagicMock(
                id="order-123",
                client_order_id="bloasis-test-001",
                status="submitted",
            )
        )
        mock_instance.get_account = AsyncMock(
            return_value=MagicMock(
                cash=Decimal("100000.00"),
                buying_power=Decimal("200000.00"),
                portfolio_value=Decimal("150000.00"),
                equity=Decimal("150000.00"),
            )
        )
        mock_client.return_value = mock_instance
        yield mock_client


@pytest.fixture
def mock_claude_client() -> Generator[MagicMock, None, None]:
    """Mock Claude client for complex reasoning.

    Yields:
        Mock Claude client.
    """
    with patch("anthropic.Anthropic") as mock_claude:
        mock_instance = MagicMock()
        mock_instance.messages.create = AsyncMock(
            return_value=MagicMock(
                content=[
                    MagicMock(
                        text='{"decision": "approve", "risk_score": 25, "reasoning": "Low risk strategy"}'
                    )
                ]
            )
        )
        mock_claude.return_value = mock_instance
        yield mock_claude
