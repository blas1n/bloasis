"""
Unit tests for main.py module.

Tests server startup and shutdown behavior.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestServeFunction:
    """Tests for the serve() function."""

    @pytest.mark.asyncio
    async def test_serve_initializes_all_clients(self) -> None:
        """Should initialize Redis, PostgreSQL, and Consul clients."""
        import src.main as main_module

        with (
            patch.object(main_module, "RedisClient") as mock_redis_cls,
            patch.object(main_module, "PostgresClient") as mock_postgres_cls,
            patch.object(main_module, "ConsulClient") as mock_consul_cls,
            patch.object(main_module, "get_local_ip") as mock_get_ip,
            patch.object(main_module, "grpc") as mock_grpc,
            patch.object(main_module, "health") as mock_health_module,
            patch.object(main_module, "health_pb2") as mock_health_pb2,
            patch.object(main_module, "health_pb2_grpc"),
            patch.object(main_module, "market_data_pb2_grpc"),
            patch.object(main_module, "config") as mock_config,
        ):
            # Setup config
            mock_config.service_name = "market-data"
            mock_config.grpc_port = 50053
            mock_config.redis_host = "redis"
            mock_config.redis_port = 6379
            mock_config.cache_ttl = 300
            mock_config.postgres_enabled = True
            mock_config.consul_enabled = True
            mock_config.consul_host = "consul"
            mock_config.consul_port = 8500

            # Setup Redis mock
            mock_redis = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            # Setup PostgreSQL mock
            mock_postgres = AsyncMock()
            mock_postgres_cls.return_value = mock_postgres

            # Setup Consul mock
            mock_consul = AsyncMock()
            mock_consul.register_grpc_service = AsyncMock(return_value=True)
            mock_consul_cls.return_value = mock_consul

            mock_get_ip.return_value = "127.0.0.1"

            # Setup gRPC server mock
            mock_server = MagicMock()
            mock_server.add_insecure_port = MagicMock()
            mock_server.start = AsyncMock()
            mock_server.wait_for_termination = AsyncMock(
                side_effect=asyncio.CancelledError()
            )
            mock_server.stop = AsyncMock()
            mock_grpc.aio.server.return_value = mock_server

            # Setup health check mock
            mock_health_servicer = MagicMock()
            mock_health_module.HealthServicer.return_value = mock_health_servicer
            mock_health_pb2.HealthCheckResponse.SERVING = 1

            # Run serve (will be cancelled)
            try:
                await main_module.serve()
            except asyncio.CancelledError:
                pass

            # Verify clients were initialized
            mock_redis.connect.assert_called_once()
            mock_postgres.connect.assert_called_once()
            mock_consul.register_grpc_service.assert_called_once()

            # Verify gRPC server was started
            mock_grpc.aio.server.assert_called_once()
            mock_server.start.assert_called_once()

            # Verify health check was set up
            mock_health_servicer.set.assert_called()

    @pytest.mark.asyncio
    async def test_serve_without_postgres(self) -> None:
        """Should work when postgres_enabled is False."""
        import src.main as main_module

        with (
            patch.object(main_module, "RedisClient") as mock_redis_cls,
            patch.object(main_module, "PostgresClient") as mock_postgres_cls,
            patch.object(main_module, "grpc") as mock_grpc,
            patch.object(main_module, "health") as mock_health_module,
            patch.object(main_module, "health_pb2") as mock_health_pb2,
            patch.object(main_module, "health_pb2_grpc"),
            patch.object(main_module, "market_data_pb2_grpc"),
            patch.object(main_module, "config") as mock_config,
        ):
            mock_config.service_name = "market-data"
            mock_config.grpc_port = 50053
            mock_config.redis_host = "redis"
            mock_config.redis_port = 6379
            mock_config.cache_ttl = 300
            mock_config.postgres_enabled = False
            mock_config.consul_enabled = False

            mock_redis = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            mock_server = MagicMock()
            mock_server.add_insecure_port = MagicMock()
            mock_server.start = AsyncMock()
            mock_server.wait_for_termination = AsyncMock(
                side_effect=asyncio.CancelledError()
            )
            mock_server.stop = AsyncMock()
            mock_grpc.aio.server.return_value = mock_server

            mock_health_servicer = MagicMock()
            mock_health_module.HealthServicer.return_value = mock_health_servicer
            mock_health_pb2.HealthCheckResponse.SERVING = 1

            try:
                await main_module.serve()
            except asyncio.CancelledError:
                pass

            mock_redis.connect.assert_called_once()
            mock_postgres_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_serve_consul_registration_failure(self) -> None:
        """Should continue when Consul registration fails."""
        import src.main as main_module

        with (
            patch.object(main_module, "RedisClient") as mock_redis_cls,
            patch.object(main_module, "ConsulClient") as mock_consul_cls,
            patch.object(main_module, "get_local_ip") as mock_get_ip,
            patch.object(main_module, "grpc") as mock_grpc,
            patch.object(main_module, "health") as mock_health_module,
            patch.object(main_module, "health_pb2") as mock_health_pb2,
            patch.object(main_module, "health_pb2_grpc"),
            patch.object(main_module, "market_data_pb2_grpc"),
            patch.object(main_module, "config") as mock_config,
        ):
            mock_config.service_name = "market-data"
            mock_config.grpc_port = 50053
            mock_config.redis_host = "redis"
            mock_config.redis_port = 6379
            mock_config.cache_ttl = 300
            mock_config.postgres_enabled = False
            mock_config.consul_enabled = True
            mock_config.consul_host = "consul"
            mock_config.consul_port = 8500

            mock_redis = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            mock_consul = AsyncMock()
            mock_consul.register_grpc_service = AsyncMock(return_value=False)
            mock_consul_cls.return_value = mock_consul

            mock_get_ip.return_value = "127.0.0.1"

            mock_server = MagicMock()
            mock_server.add_insecure_port = MagicMock()
            mock_server.start = AsyncMock()
            mock_server.wait_for_termination = AsyncMock(
                side_effect=asyncio.CancelledError()
            )
            mock_server.stop = AsyncMock()
            mock_grpc.aio.server.return_value = mock_server

            mock_health_servicer = MagicMock()
            mock_health_module.HealthServicer.return_value = mock_health_servicer
            mock_health_pb2.HealthCheckResponse.SERVING = 1

            # Should not raise even if Consul registration fails
            try:
                await main_module.serve()
            except asyncio.CancelledError:
                pass

            mock_server.start.assert_called_once()


class TestMainFunction:
    """Tests for the main() function."""

    def test_main_runs_asyncio(self) -> None:
        """Should run serve() with asyncio.run()."""
        import src.main as main_module

        with (
            patch.object(main_module, "asyncio") as mock_asyncio,
            patch.object(main_module, "serve") as mock_serve,
        ):
            mock_serve.return_value = AsyncMock()()
            main_module.main()

            mock_asyncio.run.assert_called_once()
