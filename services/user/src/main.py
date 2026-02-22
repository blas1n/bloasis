"""
User Service - gRPC only.

Envoy Gateway handles HTTP-to-gRPC transcoding.
Manages user profiles and trading preferences.
"""

import asyncio
import socket
from typing import Optional

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from shared.generated import user_pb2_grpc
from shared.utils import (
    ConsulClient,
    PostgresClient,
    RedisClient,
    get_local_ip,
    setup_logger,
)

from .clients.executor_client import ExecutorClient
from .config import config
from .repositories import UserRepository
from .repositories.broker_config_repository import BrokerConfigRepository
from .service import UserServicer

logger = setup_logger(__name__)


# Global clients for health check status
redis_client: Optional[RedisClient] = None
postgres_client: Optional[PostgresClient] = None
consul_client: Optional[ConsulClient] = None


async def serve() -> None:
    """Start and run the gRPC server."""
    global redis_client, postgres_client, consul_client

    logger.info(f"Starting {config.service_name} service...")

    # Initialize clients
    redis_client = RedisClient()
    await redis_client.connect()
    logger.info("Redis client connected")

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
            tags=["grpc", "user"],
        )
        if registered:
            logger.info("Consul service registration successful")
        else:
            logger.warning(
                "Consul service registration failed - service will continue without Consul"
            )

    # Initialize repositories
    repository = UserRepository(postgres_client)
    broker_config_repo = BrokerConfigRepository(postgres_client)

    # Initialize Executor client (for broker status checks)
    executor_client = ExecutorClient()
    try:
        await executor_client.connect()
        logger.info("Executor client connected")
    except Exception as e:
        logger.warning(f"Executor client connection failed (non-fatal): {e}")
        executor_client = None

    # Create gRPC server
    server = grpc.aio.server()

    # Add User service
    servicer = UserServicer(
        redis_client=redis_client,
        postgres_client=postgres_client,
        repository=repository,
        broker_config_repository=broker_config_repo,
        executor_client=executor_client,
    )
    user_pb2_grpc.add_UserServiceServicer_to_server(servicer, server)

    # Add health check service
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set(
        "bloasis.user.UserService",
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
        if postgres_client:
            await postgres_client.close()
            logger.info("PostgreSQL client disconnected")
        if executor_client:
            await executor_client.close()
            logger.info("Executor client disconnected")
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
