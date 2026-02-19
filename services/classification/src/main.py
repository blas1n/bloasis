"""
Classification Service - gRPC only.

Envoy Gateway handles HTTP-to-gRPC transcoding.
Implements Stock Selection Pipeline Stage 1-2.
"""

import asyncio
from typing import Optional

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.ai_clients import ClaudeClient
from shared.generated import classification_pb2_grpc
from shared.utils import setup_logger

from .clients.market_regime_client import MarketRegimeClient
from .config import config
from .service import ClassificationService, ClassificationServicer
from .utils.cache import CacheManager

logger = setup_logger(__name__)

# Global clients for shutdown
cache_manager: Optional[CacheManager] = None
regime_client: Optional[MarketRegimeClient] = None
analyst: Optional[ClaudeClient] = None


async def serve() -> None:
    """Start and run the gRPC server."""
    global cache_manager, regime_client, analyst

    logger.info(f"Starting {config.service_name} service...")

    # Initialize Redis cache
    cache_manager = CacheManager()
    await cache_manager.connect()
    logger.info("Redis cache connected")

    # Initialize Market Regime client
    regime_client = MarketRegimeClient()
    await regime_client.connect()
    logger.info("Market Regime client connected")

    # Initialize Claude analyst (optional — falls back to rule-based if not set)
    if config.anthropic_api_key:
        analyst = ClaudeClient(api_key=config.anthropic_api_key)
        logger.info(f"Claude analyst initialized (model: {config.claude_model})")
    else:
        logger.warning(
            "No ANTHROPIC_API_KEY set — sector/theme analysis uses rule-based fallback"
        )

    # Initialize classification service
    classification_service = ClassificationService(
        analyst=analyst,
        claude_model=config.claude_model,
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
