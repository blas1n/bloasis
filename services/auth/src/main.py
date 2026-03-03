"""
Auth Service - gRPC only.

Envoy Gateway handles HTTP-to-gRPC transcoding.
Manages JWT authentication, token validation, and refresh.
"""

import asyncio
import socket
import sys
from pathlib import Path
from typing import Optional

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.generated import auth_pb2_grpc
from shared.utils import (
    ConsulClient,
    RedisClient,
    get_local_ip,
    setup_logger,
)

from .clients.user_client import UserClient
from .config import config
from .jwt_handler import JWTHandler
from .service import AuthServicer

logger = setup_logger(__name__)

# Global clients for health check status
redis_client: Optional[RedisClient] = None
user_client: Optional[UserClient] = None
consul_client: Optional[ConsulClient] = None


def _resolve_key_path(path: str) -> str:
    """Resolve a key path to absolute, anchored at workspace root if relative."""
    if not path:
        return path
    p = Path(path)
    if p.is_absolute():
        return path
    # Relative path: resolve against workspace root (4 levels up from this file)
    workspace_root = Path(__file__).resolve().parent.parent.parent.parent
    return str(workspace_root / path)


def create_jwt_handler() -> JWTHandler:
    """Create JWT handler using RS256 configuration.

    Returns:
        Configured JWTHandler instance.

    Raises:
        ValueError: If key paths are not configured.
        FileNotFoundError: If key files do not exist.
    """
    logger.info("Initializing JWT handler with RS256 algorithm")
    return JWTHandler(
        private_key_path=_resolve_key_path(config.jwt_private_key_path),
        public_key_path=_resolve_key_path(config.jwt_public_key_path),
        access_token_expire_minutes=config.access_token_expire_minutes,
        refresh_token_expire_days=config.refresh_token_expire_days,
    )


async def serve() -> None:
    """Start and run the gRPC server."""
    global redis_client, user_client, consul_client

    logger.info(f"Starting {config.service_name} service...")

    # Initialize Redis client
    redis_client = RedisClient()
    await redis_client.connect()
    logger.info("Redis client connected")

    # Initialize User Service client
    user_client = UserClient()
    await user_client.connect()
    logger.info("User Service client connected")

    # Initialize JWT handler
    jwt_handler = create_jwt_handler()
    logger.info("JWT handler initialized with RS256 algorithm")

    # Log public key availability for Envoy Gateway configuration
    if jwt_handler.get_public_key():
        logger.info("RS256 public key available for Envoy Gateway configuration")

    # Create gRPC server
    server = grpc.aio.server(
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 300000),
            ("grpc.keepalive_timeout_ms", 20000),
        ]
    )

    # Add Auth service
    servicer = AuthServicer(
        jwt_handler=jwt_handler,
        redis_client=redis_client,
        user_client=user_client,
    )
    auth_pb2_grpc.add_AuthServiceServicer_to_server(servicer, server)

    # Add health check service
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        "bloasis.auth.AuthService",
        health_pb2.HealthCheckResponse.SERVING,
    )
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Start server
    listen_addr = f"[::]:{config.grpc_port}"
    bound_port = server.add_insecure_port(listen_addr)
    if bound_port == 0:
        raise RuntimeError(
            f"Failed to bind gRPC port {listen_addr} "
            f"(port may be in use by another process)"
        )
    await server.start()
    logger.info(f"gRPC server started on {listen_addr}")

    # Register with Consul AFTER server is ready to accept connections
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
            tags=["grpc", "auth"],
        )
        if registered:
            logger.info("Consul service registration successful")
        else:
            logger.warning(
                "Consul service registration failed - service will continue without Consul"
            )

    # Handle shutdown
    async def shutdown() -> None:
        logger.info("Shutting down...")
        # Deregister from Consul first (so traffic stops coming)
        if consul_client:
            await consul_client.deregister_all()
            logger.info("Consul services deregistered")
        await server.stop(grace=5)
        if user_client:
            await user_client.close()
            logger.info("User Service client disconnected")
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
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, exiting...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
