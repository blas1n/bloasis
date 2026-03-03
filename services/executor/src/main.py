"""Executor Service - gRPC Server Entry Point.

This service implements order execution through Alpaca paper trading:
- Market, Limit, and Bracket orders
- Risk approval verification
- Order status tracking
- Execution event publishing
- Strategy signal consumption (auto-trading)
- Periodic AI analysis scheduling

Note: Phase 1 supports paper trading only.
"""

import asyncio
import sys

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.generated import executor_pb2_grpc
from shared.utils import setup_logger

from .clients.risk_committee_client import RiskCommitteeClient
from .clients.strategy_client import StrategyClient
from .clients.user_client import UserClient
from .config import config
from .service import ExecutorServicer
from .utils.event_publisher import EventPublisher
from .utils.redis_client import RedisClient

logger = setup_logger(__name__)


async def serve() -> None:
    """Start and run the gRPC server."""
    logger.info(f"Starting {config.service_name} service on port {config.grpc_port}...")

    # Initialize core clients (AlpacaClient is created on-demand from User Service DB)
    event_publisher = EventPublisher()
    redis_client = RedisClient()

    # Connect core clients
    try:
        await event_publisher.connect()
        await redis_client.connect()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        raise

    # Initialize User Service client for dynamic broker config
    user_client = UserClient()
    try:
        await user_client.connect()
        logger.info("User Service client connected")
    except Exception as e:
        logger.warning(f"User Service client connection failed (non-fatal): {e}")
        user_client = None

    # Initialize Risk Committee client for order approval
    risk_committee_client = RiskCommitteeClient()
    try:
        await risk_committee_client.connect()
        logger.info("Risk Committee client connected")
    except Exception as e:
        logger.warning(f"Risk Committee client connection failed (non-fatal): {e}")
        risk_committee_client = None

    # Initialize Strategy Service client for AI analysis trigger
    strategy_client = StrategyClient()
    try:
        await strategy_client.connect()
        logger.info("Strategy Service client connected")
    except Exception as e:
        logger.warning(f"Strategy Service client connection failed (non-fatal): {e}")
        strategy_client = None

    logger.info("All clients connected")

    # Create gRPC server
    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 300000),
            ("grpc.keepalive_timeout_ms", 20000),
        ]
    )

    # Create and register servicer
    servicer = ExecutorServicer(
        alpaca_client=None,
        event_publisher=event_publisher,
        redis_client=redis_client,
        user_client=user_client,
        risk_committee_client=risk_committee_client,
        strategy_client=strategy_client,
    )
    executor_pb2_grpc.add_ExecutorServiceServicer_to_server(servicer, server)

    # Start trading control event consumer
    try:
        await servicer.start_trading_control_consumer(config.redpanda_brokers)
        logger.info("Trading control consumer started")
    except Exception as e:
        logger.error(f"Failed to start trading control consumer: {e}")
        raise

    # Start strategy signal event consumer
    try:
        await servicer.start_strategy_signal_consumer(config.redpanda_brokers)
        logger.info("Strategy signal consumer started")
    except Exception as e:
        logger.error(f"Failed to start strategy signal consumer: {e}")
        raise

    # Add gRPC health check service
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        "bloasis.executor.ExecutorService",
        health_pb2.HealthCheckResponse.SERVING,
    )
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Start server
    listen_addr = f"[::]:{config.grpc_port}"
    server.add_insecure_port(listen_addr)
    await server.start()
    logger.info(f"gRPC server started on {listen_addr}")

    # Recover active trading state from Redis once Strategy Service is ready.
    # Uses gRPC channel_ready() — event-driven wait for connectivity, not polling.
    async def _recovery_when_ready() -> None:
        if strategy_client and strategy_client.channel:
            try:
                await asyncio.wait_for(
                    strategy_client.channel.channel_ready(), timeout=120,
                )
                logger.info("Strategy Service ready, starting trading recovery")
            except asyncio.TimeoutError:
                logger.warning(
                    "Strategy Service not ready after 120s, "
                    "proceeding with recovery (periodic retry will handle)"
                )
        try:
            await servicer.recover_active_trading()
        except Exception as e:
            logger.warning(f"Trading state recovery failed (non-fatal): {e}")

    _recovery_task = asyncio.create_task(_recovery_when_ready())

    # Start periodic fill checker for pending orders
    # (handles orders placed outside market hours, limit orders, etc.)
    await servicer.start_pending_order_monitor()

    # Handle shutdown
    async def shutdown() -> None:
        logger.info("Shutting down...")
        _recovery_task.cancel()
        await server.stop(grace=5)

        # Stop all consumers and scheduled tasks
        await servicer.stop_consumers()

        if event_publisher:
            await event_publisher.close()
            logger.info("Event publisher closed")

        if redis_client:
            await redis_client.close()
            logger.info("Redis client closed")

        if risk_committee_client:
            await risk_committee_client.close()
        if strategy_client:
            await strategy_client.close()

        logger.info("Shutdown complete")

    # Wait for termination
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await shutdown()


def main() -> None:
    """Main entry point."""
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, exiting...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
