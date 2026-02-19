"""Backtesting Service - gRPC Server Entry Point.

This service provides backtesting capabilities:
- VectorBT backtesting (MA Crossover, RSI)
- FinRL backtesting (PPO, A2C, SAC)
- Performance metrics calculation
- Strategy comparison

Envoy Gateway handles HTTP-to-gRPC transcoding.
"""

import asyncio
import logging
import sys

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from shared.generated import backtesting_pb2_grpc

from .clients.market_data_client import MarketDataClient
from .config import config
from .service import BacktestingServicer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Global clients for shutdown
market_data_client: MarketDataClient | None = None


async def serve() -> None:
    """Start and run the gRPC server."""
    global market_data_client

    logger.info(f"Starting {config.service_name} service on port {config.grpc_port}...")

    # Initialize Market Data client
    market_data_client = MarketDataClient()

    try:
        await market_data_client.connect()
    except Exception as e:
        logger.error(f"Failed to connect to Market Data Service: {e}")
        raise

    logger.info("Market Data client connected")

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
    servicer = BacktestingServicer(market_data_client=market_data_client)
    backtesting_pb2_grpc.add_BacktestingServiceServicer_to_server(servicer, server)

    # Add gRPC health check service
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        "bloasis.backtesting.BacktestingService",
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

        if market_data_client:
            await market_data_client.close()
            logger.info("Market Data client closed")

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
