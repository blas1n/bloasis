"""
Market Regime Service - gRPC only.

Kong Gateway handles HTTP-to-gRPC transcoding.
Integrates FinGPT for AI-powered market regime classification.
"""

import asyncio
import socket
from typing import Optional

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.generated import market_regime_pb2_grpc
from shared.utils import (
    ConsulClient,
    EventPublisher,
    PostgresClient,
    RedisClient,
    RedpandaClient,
    get_local_ip,
    setup_logger,
)

from .clients.fingpt_client import FinGPTClient, MockFinGPTClient
from .config import config
from .macro_data import MacroDataFetcher
from .models import RegimeClassifier
from .service import MarketRegimeServicer

logger = setup_logger(__name__)

# Global clients for health check status
redis_client: Optional[RedisClient] = None
redpanda_client: Optional[RedpandaClient] = None
postgres_client: Optional[PostgresClient] = None
consul_client: Optional[ConsulClient] = None


async def serve() -> None:
    """Start and run the gRPC server."""
    global redis_client, redpanda_client, postgres_client, consul_client

    logger.info(f"Starting {config.service_name} service...")

    # Initialize clients
    redis_client = RedisClient()
    await redis_client.connect()
    logger.info("Redis client connected")

    redpanda_client = RedpandaClient()
    await redpanda_client.start()
    logger.info("Redpanda client connected")

    # Initialize EventPublisher for typed event publishing
    event_publisher = EventPublisher(redpanda_client)
    logger.info("Event publisher initialized")

    postgres_client = PostgresClient()
    await postgres_client.connect()
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

    # Initialize FinGPT client (via Hugging Face)
    if config.use_mock_fingpt or not config.huggingface_token:
        fingpt_client = MockFinGPTClient()
        logger.warning("Using mock FinGPT client (set HUGGINGFACE_TOKEN to use real API)")
    else:
        fingpt_client = FinGPTClient(
            api_key=config.huggingface_token,
            model=config.fingpt_model,
            timeout=config.fingpt_timeout,
        )
        await fingpt_client.connect()
        logger.info(f"FinGPT client connected (model: {config.fingpt_model})")

    # Initialize macro data fetcher
    macro_fetcher = MacroDataFetcher(fred_api_key=config.fred_api_key or None)
    logger.info("Macro data fetcher initialized")

    # Initialize regime classifier with FinGPT integration
    classifier = RegimeClassifier(
        fingpt_client=fingpt_client,
        macro_fetcher=macro_fetcher,
    )

    # Create gRPC server
    server = grpc.aio.server()

    # Add Market Regime service
    servicer = MarketRegimeServicer(
        redis_client=redis_client,
        redpanda_client=redpanda_client,
        postgres_client=postgres_client,
        classifier=classifier,
        event_publisher=event_publisher,
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
        # Deregister from Consul first (so traffic stops coming)
        if consul_client:
            await consul_client.deregister_all()
            logger.info("Consul services deregistered")
        await server.stop(grace=5)
        # Close FinGPT client
        if fingpt_client:
            await fingpt_client.close()
            logger.info("FinGPT client disconnected")
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
