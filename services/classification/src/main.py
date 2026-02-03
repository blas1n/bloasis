"""
Classification Service - gRPC only.

Kong Gateway handles HTTP-to-gRPC transcoding.
Implements Stock Selection Pipeline Stage 1-2.
"""

import asyncio
from typing import Optional

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.generated import classification_pb2_grpc
from shared.utils import setup_logger

from .clients.fingpt_client import FinGPTClient, MockFinGPTClient
from .clients.market_regime_client import MarketRegimeClient
from .config import config
from .service import ClassificationService, ClassificationServicer
from .utils.cache import CacheManager

logger = setup_logger(__name__)

# Global clients for shutdown
cache_manager: Optional[CacheManager] = None
regime_client: Optional[MarketRegimeClient] = None
fingpt_client: Optional[FinGPTClient | MockFinGPTClient] = None


async def serve() -> None:
    """Start and run the gRPC server."""
    global cache_manager, regime_client, fingpt_client

    logger.info(f"Starting {config.service_name} service...")

    # Initialize Redis cache
    cache_manager = CacheManager()
    await cache_manager.connect()
    logger.info("Redis cache connected")

    # Initialize Market Regime client
    regime_client = MarketRegimeClient()
    await regime_client.connect()
    logger.info("Market Regime client connected")

    # Initialize FinGPT client (mock or real based on config)
    if config.use_mock_fingpt or not config.huggingface_token:
        fingpt_client = MockFinGPTClient()
        logger.warning(
            "Using mock FinGPT client (set USE_MOCK_FINGPT=false and HUGGINGFACE_TOKEN to use real API)"
        )
    else:
        fingpt_client = FinGPTClient(
            api_key=config.huggingface_token,
            model=config.fingpt_model,
            timeout=config.fingpt_timeout,
        )
        logger.info(f"FinGPT client initialized (model: {config.fingpt_model})")

    # Initialize classification service
    classification_service = ClassificationService(
        fingpt_client=fingpt_client,
        regime_client=regime_client,
        cache_manager=cache_manager,
    )

    # Create gRPC server
    server = grpc.aio.server()

    # Add Classification service
    servicer = ClassificationServicer(classification_service)
    classification_pb2_grpc.add_ClassificationServiceServicer_to_server(servicer, server)

    # Add gRPC health check service
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        "bloasis.classification.ClassificationService",
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

        if fingpt_client:
            await fingpt_client.close()
            logger.info("FinGPT client closed")

        if regime_client:
            await regime_client.close()
            logger.info("Market Regime client closed")

        if cache_manager:
            await cache_manager.close()
            logger.info("Redis cache closed")

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
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
