"""Executor Service - gRPC Server Entry Point.

This service implements order execution through Alpaca paper trading:
- Market, Limit, and Bracket orders
- Risk approval verification
- Order status tracking
- Execution event publishing

Note: Phase 1 supports paper trading only.
"""

import asyncio
import logging
import sys

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.generated import executor_pb2_grpc
from shared.utils.event_consumer import EventConsumer

from .alpaca_client import AlpacaClient
from .config import config
from .service import ExecutorServicer
from .utils.event_publisher import EventPublisher
from .utils.redis_client import RedisClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Global clients for shutdown
alpaca_client: AlpacaClient | None = None
event_publisher: EventPublisher | None = None
redis_client: RedisClient | None = None
trading_control_consumer: EventConsumer | None = None


async def serve() -> None:
    """Start and run the gRPC server."""
    global alpaca_client, event_publisher, redis_client, trading_control_consumer

    logger.info(f"Starting {config.service_name} service on port {config.grpc_port}...")

    # Initialize clients
    alpaca_client = AlpacaClient(
        api_key=config.alpaca_api_key,
        secret_key=config.alpaca_secret_key,
        paper=config.alpaca_paper,
    )
    event_publisher = EventPublisher()
    redis_client = RedisClient()

    # Connect clients
    try:
        await event_publisher.connect()
        await redis_client.connect()
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        raise

    logger.info("All clients connected")

    # Create gRPC server
    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 10000),
            ("grpc.keepalive_timeout_ms", 5000),
        ]
    )

    # Create and register servicer
    servicer = ExecutorServicer(
        alpaca_client=alpaca_client,
        event_publisher=event_publisher,
        redis_client=redis_client,
    )
    executor_pb2_grpc.add_ExecutorServiceServicer_to_server(servicer, server)

    # Start trading control event consumer
    try:
        await servicer.start_trading_control_consumer(config.redpanda_brokers)
        logger.info("Trading control consumer started")
    except Exception as e:
        logger.error(f"Failed to start trading control consumer: {e}")
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

    # Handle shutdown
    async def shutdown() -> None:
        logger.info("Shutting down...")
        await server.stop(grace=5)

        # Stop trading control consumer
        if servicer and hasattr(servicer, 'stop_trading_control_consumer'):
            await servicer.stop_trading_control_consumer()
            logger.info("Trading control consumer stopped")

        if event_publisher:
            await event_publisher.close()
            logger.info("Event publisher closed")

        if redis_client:
            await redis_client.close()
            logger.info("Redis client closed")

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
