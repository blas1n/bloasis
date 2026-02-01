"""
Market Data Service - gRPC only.

Kong Gateway handles HTTP-to-gRPC transcoding.
Uses yfinance for stock market data with Redis caching.
"""

import asyncio
import socket
from typing import Optional

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.generated import market_data_pb2_grpc
from shared.utils import (
    ConsulClient,
    PostgresClient,
    RedisClient,
    get_local_ip,
    setup_logger,
)

from .config import config
from .data_fetcher import MarketDataFetcher
from .repository import MarketDataRepository
from .service import MarketDataServicer

logger = setup_logger(__name__)

# Global clients for health check status
redis_client: Optional[RedisClient] = None
postgres_client: Optional[PostgresClient] = None
consul_client: Optional[ConsulClient] = None


async def serve() -> None:
    """Start and run the gRPC server."""
    global redis_client, postgres_client, consul_client

    logger.info(f"Starting {config.service_name} service...")

    # Initialize Redis client
    redis_client = RedisClient(host=config.redis_host, port=config.redis_port)
    await redis_client.connect()
    logger.info("Redis client connected")

    # Initialize data fetcher
    data_fetcher = MarketDataFetcher()

    # Initialize PostgreSQL client if enabled
    repository: Optional[MarketDataRepository] = None
    if config.postgres_enabled:
        postgres_client = PostgresClient()
        await postgres_client.connect()
        repository = MarketDataRepository(postgres_client)
        logger.info("PostgreSQL client connected")

    # Initialize Consul client if enabled
    if config.consul_enabled:
        consul_client = ConsulClient(
            host=config.consul_host,
            port=config.consul_port,
        )
        service_host = get_local_ip(config.consul_host, config.consul_port)
        registered = await consul_client.register_grpc_service(
            service_name=config.service_name,
            service_id=f"{config.service_name}-{socket.gethostname()}",
            host=service_host,
            port=config.grpc_port,
            tags=["grpc", "tier1"],
        )
        if registered:
            logger.info("Consul service registration successful")
        else:
            logger.warning(
                "Consul service registration failed - service will continue without Consul"
            )

    # Create gRPC server
    server = grpc.aio.server()

    # Add Market Data service
    servicer = MarketDataServicer(
        redis_client=redis_client,
        data_fetcher=data_fetcher,
        repository=repository,
        cache_ttl=config.cache_ttl,
    )
    market_data_pb2_grpc.add_MarketDataServiceServicer_to_server(servicer, server)

    # Add health check service
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        "bloasis.market_data.MarketDataService",
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
        # Deregister from Consul first (so traffic stops coming)
        if consul_client:
            await consul_client.deregister_all()
            logger.info("Consul services deregistered")
        await server.stop(grace=5)
        if postgres_client:
            await postgres_client.close()
            logger.info("PostgreSQL client disconnected")
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
