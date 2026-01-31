"""
Market Regime Service - gRPC only.

Kong Gateway handles HTTP-to-gRPC transcoding.
"""

import asyncio
from typing import Optional

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.generated import market_regime_pb2_grpc
from shared.utils import PostgresClient, RedisClient, RedpandaClient, setup_logger

from .config import config
from .service import MarketRegimeServicer

logger = setup_logger(__name__)

# Global clients for health check status
redis_client: Optional[RedisClient] = None
redpanda_client: Optional[RedpandaClient] = None
postgres_client: Optional[PostgresClient] = None


async def serve() -> None:
    """Start and run the gRPC server."""
    global redis_client, redpanda_client, postgres_client

    logger.info(f"Starting {config.service_name} service...")

    # Initialize clients
    redis_client = RedisClient()
    await redis_client.connect()
    logger.info("Redis client connected")

    redpanda_client = RedpandaClient()
    await redpanda_client.start()
    logger.info("Redpanda client connected")

    postgres_client = PostgresClient()
    await postgres_client.connect()
    logger.info("PostgreSQL client connected")

    # Create gRPC server
    server = grpc.aio.server()

    # Add Market Regime service
    servicer = MarketRegimeServicer(
        redis_client=redis_client,
        redpanda_client=redpanda_client,
        postgres_client=postgres_client,
    )
    market_regime_pb2_grpc.add_MarketRegimeServiceServicer_to_server(servicer, server)

    # Add health check service
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        "bloasis.market_regime.MarketRegimeService",
        health_pb2.HealthCheckResponse.SERVING
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
        if postgres_client:
            await postgres_client.close()
            logger.info("PostgreSQL client disconnected")
        if redpanda_client:
            await redpanda_client.stop()
            logger.info("Redpanda client disconnected")
        if redis_client:
            await redis_client.close()
            logger.info("Redis client disconnected")
        logger.info("Shutdown complete")

    # Wait for termination
    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await shutdown()


def main() -> None:
    """Main entry point."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
