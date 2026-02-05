"""Risk Committee Service - gRPC Server Entry Point.

This service implements multi-agent risk assessment before order execution:
- Position Risk Agent: Checks position sizing limits
- Concentration Risk Agent: Checks portfolio concentration
- Market Risk Agent: Checks market conditions (VIX, liquidity)

Uses voting/consensus mechanism for approval/rejection decisions.
"""

import asyncio
import logging
import sys

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.generated import risk_committee_pb2_grpc

from .clients.market_data_client import MarketDataClient
from .clients.portfolio_client import PortfolioClient
from .config import config
from .service import RiskCommitteeServicer
from .utils.event_publisher import EventPublisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Global clients for shutdown
portfolio_client: PortfolioClient | None = None
market_data_client: MarketDataClient | None = None
event_publisher: EventPublisher | None = None


async def serve() -> None:
    """Start and run the gRPC server."""
    global portfolio_client, market_data_client, event_publisher

    logger.info(f"Starting {config.service_name} service on port {config.grpc_port}...")

    # Initialize clients
    portfolio_client = PortfolioClient()
    market_data_client = MarketDataClient()
    event_publisher = EventPublisher()

    # Connect clients
    try:
        await portfolio_client.connect()
        await market_data_client.connect()
        await event_publisher.connect()
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
    servicer = RiskCommitteeServicer(
        portfolio_client=portfolio_client,
        market_data_client=market_data_client,
        event_publisher=event_publisher,
    )
    risk_committee_pb2_grpc.add_RiskCommitteeServiceServicer_to_server(servicer, server)

    # Add gRPC health check service
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        "bloasis.risk.RiskCommitteeService",
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

        if portfolio_client:
            await portfolio_client.close()
            logger.info("Portfolio client closed")

        if market_data_client:
            await market_data_client.close()
            logger.info("Market Data client closed")

        if event_publisher:
            await event_publisher.close()
            logger.info("Event publisher closed")

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
