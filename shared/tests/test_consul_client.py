"""
Unit tests for ConsulClient.

All external dependencies (Consul) are mocked.
"""

from unittest.mock import MagicMock, patch

import pytest

from shared.utils.consul_client import ConsulClient


class TestConsulClientInit:
    """Tests for ConsulClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Should use environment variable defaults."""
        with patch.dict("os.environ", {}, clear=True):
            client = ConsulClient()
            assert client.host == "consul"
            assert client.port == 8500
            assert client.token is None
            assert client._consul is None
            assert client.registered_services == []

    def test_init_with_env_vars(self) -> None:
        """Should read from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "CONSUL_HOST": "custom-consul",
                "CONSUL_PORT": "8501",
                "CONSUL_TOKEN": "test-token",
            },
        ):
            client = ConsulClient()
            assert client.host == "custom-consul"
            assert client.port == 8501
            assert client.token == "test-token"

    def test_init_with_explicit_params(self) -> None:
        """Should use explicit parameters over env vars."""
        with patch.dict(
            "os.environ",
            {"CONSUL_HOST": "env-consul", "CONSUL_PORT": "8501"},
        ):
            client = ConsulClient(host="explicit-consul", port=9999, token="my-token")
            assert client.host == "explicit-consul"
            assert client.port == 9999
            assert client.token == "my-token"


class TestConsulClientConsulProperty:
    """Tests for ConsulClient.consul property."""

    def test_consul_property_creates_instance(self) -> None:
        """Should create Consul instance on first access."""
        with patch("shared.utils.consul_client.consul.Consul") as mock_consul_class:
            mock_instance = MagicMock()
            mock_consul_class.return_value = mock_instance

            client = ConsulClient(host="test-host", port=8500, token="test-token")
            result = client.consul

            mock_consul_class.assert_called_once_with(
                host="test-host",
                port=8500,
                token="test-token",
            )
            assert result is mock_instance

    def test_consul_property_returns_cached_instance(self) -> None:
        """Should return cached instance on subsequent calls."""
        with patch("shared.utils.consul_client.consul.Consul") as mock_consul_class:
            mock_instance = MagicMock()
            mock_consul_class.return_value = mock_instance

            client = ConsulClient()
            result1 = client.consul
            result2 = client.consul

            # Should only create one instance
            mock_consul_class.assert_called_once()
            assert result1 is result2


class TestConsulClientRegisterGrpcService:
    """Tests for ConsulClient.register_grpc_service()."""

    @pytest.mark.asyncio
    async def test_register_success(self) -> None:
        """Should register service successfully."""
        mock_consul = MagicMock()
        mock_consul.agent.service.register = MagicMock()

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            result = await client.register_grpc_service(
                service_name="test-service",
                service_id="test-service-1",
                host="test-host",
                port=50051,
                tags=["grpc", "test"],
            )

            assert result is True
            assert "test-service-1" in client.registered_services

            mock_consul.agent.service.register.assert_called_once()
            call_kwargs = mock_consul.agent.service.register.call_args[1]
            assert call_kwargs["name"] == "test-service"
            assert call_kwargs["service_id"] == "test-service-1"
            assert call_kwargs["address"] == "test-host"
            assert call_kwargs["port"] == 50051
            assert call_kwargs["tags"] == ["grpc", "test"]
            # Verify check dictionary is passed correctly
            assert call_kwargs["check"]["grpc"] == "test-host:50051"
            assert call_kwargs["check"]["interval"] == "10s"
            assert call_kwargs["check"]["timeout"] == "5s"
            assert call_kwargs["check"]["grpc_use_tls"] is False

    @pytest.mark.asyncio
    async def test_register_with_custom_intervals(self) -> None:
        """Should use custom check intervals."""
        mock_consul = MagicMock()
        mock_consul.agent.service.register = MagicMock()

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            await client.register_grpc_service(
                service_name="test-service",
                service_id="test-service-1",
                host="test-host",
                port=50051,
                check_interval="30s",
                check_timeout="10s",
            )

            mock_consul.agent.service.register.assert_called_once()
            call_kwargs = mock_consul.agent.service.register.call_args[1]
            # Verify custom check intervals are used
            assert call_kwargs["check"]["grpc"] == "test-host:50051"
            assert call_kwargs["check"]["interval"] == "30s"
            assert call_kwargs["check"]["timeout"] == "10s"
            assert call_kwargs["check"]["grpc_use_tls"] is False

    @pytest.mark.asyncio
    async def test_register_with_meta(self) -> None:
        """Should pass metadata to registration."""
        mock_consul = MagicMock()
        mock_consul.agent.service.register = MagicMock()

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            await client.register_grpc_service(
                service_name="test-service",
                service_id="test-service-1",
                host="test-host",
                port=50051,
                meta={"version": "1.0.0", "env": "test"},
            )

            call_kwargs = mock_consul.agent.service.register.call_args[1]
            assert call_kwargs["meta"] == {"version": "1.0.0", "env": "test"}

    @pytest.mark.asyncio
    async def test_register_failure_consul_exception(self) -> None:
        """Should return False on Consul exception."""
        import consul as consul_lib

        mock_consul = MagicMock()
        mock_consul.agent.service.register.side_effect = consul_lib.ConsulException(
            "Connection refused"
        )

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            with patch("shared.utils.consul_client.consul.Check") as mock_check:
                mock_check.grpc.return_value = {}

                client = ConsulClient()
                result = await client.register_grpc_service(
                    service_name="test-service",
                    service_id="test-service-1",
                    host="test-host",
                    port=50051,
                )

                assert result is False
                assert "test-service-1" not in client.registered_services

    @pytest.mark.asyncio
    async def test_register_failure_unexpected_exception(self) -> None:
        """Should return False on unexpected exception."""
        mock_consul = MagicMock()
        mock_consul.agent.service.register.side_effect = RuntimeError("Unexpected error")

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            with patch("shared.utils.consul_client.consul.Check") as mock_check:
                mock_check.grpc.return_value = {}

                client = ConsulClient()
                result = await client.register_grpc_service(
                    service_name="test-service",
                    service_id="test-service-1",
                    host="test-host",
                    port=50051,
                )

                assert result is False


class TestConsulClientDeregisterService:
    """Tests for ConsulClient.deregister_service()."""

    @pytest.mark.asyncio
    async def test_deregister_success(self) -> None:
        """Should deregister service successfully."""
        mock_consul = MagicMock()
        mock_consul.agent.service.deregister = MagicMock()

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            client.registered_services = ["test-service-1", "test-service-2"]

            result = await client.deregister_service("test-service-1")

            assert result is True
            assert "test-service-1" not in client.registered_services
            assert "test-service-2" in client.registered_services
            mock_consul.agent.service.deregister.assert_called_once_with("test-service-1")

    @pytest.mark.asyncio
    async def test_deregister_not_in_list(self) -> None:
        """Should succeed even if service not in registered list."""
        mock_consul = MagicMock()
        mock_consul.agent.service.deregister = MagicMock()

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            client.registered_services = []

            result = await client.deregister_service("unknown-service")

            assert result is True
            mock_consul.agent.service.deregister.assert_called_once_with("unknown-service")

    @pytest.mark.asyncio
    async def test_deregister_failure_consul_exception(self) -> None:
        """Should return False on Consul exception."""
        import consul as consul_lib

        mock_consul = MagicMock()
        mock_consul.agent.service.deregister.side_effect = consul_lib.ConsulException(
            "Service not found"
        )

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            client.registered_services = ["test-service-1"]

            result = await client.deregister_service("test-service-1")

            assert result is False
            # Service should still be in list since deregistration failed
            assert "test-service-1" in client.registered_services

    @pytest.mark.asyncio
    async def test_deregister_failure_unexpected_exception(self) -> None:
        """Should return False on unexpected exception."""
        mock_consul = MagicMock()
        mock_consul.agent.service.deregister.side_effect = RuntimeError("Unexpected")

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()

            result = await client.deregister_service("test-service-1")

            assert result is False


class TestConsulClientDeregisterAll:
    """Tests for ConsulClient.deregister_all()."""

    @pytest.mark.asyncio
    async def test_deregister_all_success(self) -> None:
        """Should deregister all services."""
        mock_consul = MagicMock()
        mock_consul.agent.service.deregister = MagicMock()

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            client.registered_services = ["service-1", "service-2", "service-3"]

            await client.deregister_all()

            assert client.registered_services == []
            assert mock_consul.agent.service.deregister.call_count == 3

    @pytest.mark.asyncio
    async def test_deregister_all_empty_list(self) -> None:
        """Should handle empty registered services list."""
        mock_consul = MagicMock()

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            client.registered_services = []

            await client.deregister_all()

            assert client.registered_services == []
            mock_consul.agent.service.deregister.assert_not_called()

    @pytest.mark.asyncio
    async def test_deregister_all_partial_failure(self) -> None:
        """Should continue deregistering even if some fail."""
        import consul as consul_lib

        mock_consul = MagicMock()
        # First call succeeds, second fails, third succeeds
        mock_consul.agent.service.deregister.side_effect = [
            None,
            consul_lib.ConsulException("Failed"),
            None,
        ]

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            client.registered_services = ["service-1", "service-2", "service-3"]

            await client.deregister_all()

            # All three should have been attempted
            assert mock_consul.agent.service.deregister.call_count == 3
            # service-2 should still be in list (failed to deregister)
            assert "service-2" in client.registered_services
            assert "service-1" not in client.registered_services
            assert "service-3" not in client.registered_services


class TestConsulClientGetServiceHealth:
    """Tests for ConsulClient.get_service_health()."""

    @pytest.mark.asyncio
    async def test_get_service_health_success(self) -> None:
        """Should return health data for service."""
        mock_consul = MagicMock()
        mock_consul.health.service.return_value = (
            None,
            [
                {
                    "Service": {
                        "ID": "test-service-1",
                        "Service": "test-service",
                        "Address": "10.0.0.1",
                        "Port": 50051,
                        "Tags": ["grpc", "tier1"],
                    },
                    "Checks": [
                        {
                            "CheckID": "service:test-service-1",
                            "Name": "Service 'test-service' check",
                            "Status": "passing",
                            "Output": "gRPC health check passed",
                        }
                    ],
                }
            ],
        )

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            result = await client.get_service_health("test-service")

            assert len(result) == 1
            assert result[0]["service_id"] == "test-service-1"
            assert result[0]["service_name"] == "test-service"
            assert result[0]["address"] == "10.0.0.1"
            assert result[0]["port"] == 50051
            assert result[0]["tags"] == ["grpc", "tier1"]
            assert result[0]["status"] == "healthy"
            assert len(result[0]["checks"]) == 1

    @pytest.mark.asyncio
    async def test_get_service_health_unhealthy(self) -> None:
        """Should return unhealthy status when check is critical."""
        mock_consul = MagicMock()
        mock_consul.health.service.return_value = (
            None,
            [
                {
                    "Service": {
                        "ID": "test-service-1",
                        "Service": "test-service",
                        "Address": "10.0.0.1",
                        "Port": 50051,
                        "Tags": [],
                    },
                    "Checks": [
                        {
                            "CheckID": "service:test-service-1",
                            "Name": "gRPC health check",
                            "Status": "critical",
                            "Output": "Connection refused",
                        }
                    ],
                }
            ],
        )

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            result = await client.get_service_health("test-service")

            assert len(result) == 1
            assert result[0]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_get_service_health_warning(self) -> None:
        """Should return warning status when check is warning."""
        mock_consul = MagicMock()
        mock_consul.health.service.return_value = (
            None,
            [
                {
                    "Service": {
                        "ID": "test-service-1",
                        "Service": "test-service",
                        "Address": "10.0.0.1",
                        "Port": 50051,
                        "Tags": [],
                    },
                    "Checks": [
                        {
                            "CheckID": "service:test-service-1",
                            "Name": "gRPC health check",
                            "Status": "warning",
                            "Output": "High latency",
                        }
                    ],
                }
            ],
        )

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            result = await client.get_service_health("test-service")

            assert len(result) == 1
            assert result[0]["status"] == "warning"

    @pytest.mark.asyncio
    async def test_get_service_health_empty(self) -> None:
        """Should return empty list when no services found."""
        mock_consul = MagicMock()
        mock_consul.health.service.return_value = (None, [])

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            result = await client.get_service_health("nonexistent-service")

            assert result == []

    @pytest.mark.asyncio
    async def test_get_service_health_consul_exception(self) -> None:
        """Should return empty list on Consul exception."""
        import consul as consul_lib

        mock_consul = MagicMock()
        mock_consul.health.service.side_effect = consul_lib.ConsulException("Error")

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            result = await client.get_service_health("test-service")

            assert result == []


class TestConsulClientGetHealthyServices:
    """Tests for ConsulClient.get_healthy_services()."""

    @pytest.mark.asyncio
    async def test_get_healthy_services_success(self) -> None:
        """Should return only healthy services."""
        mock_consul = MagicMock()
        mock_consul.health.service.return_value = (
            None,
            [
                {
                    "Service": {
                        "ID": "test-service-1",
                        "Address": "10.0.0.1",
                        "Port": 50051,
                        "Tags": ["grpc"],
                    }
                },
                {
                    "Service": {
                        "ID": "test-service-2",
                        "Address": "10.0.0.2",
                        "Port": 50051,
                        "Tags": ["grpc"],
                    }
                },
            ],
        )

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            result = await client.get_healthy_services("test-service")

            mock_consul.health.service.assert_called_once_with(
                service="test-service",
                passing=True,
            )
            assert len(result) == 2
            assert result[0]["service_id"] == "test-service-1"
            assert result[0]["address"] == "10.0.0.1"
            assert result[1]["service_id"] == "test-service-2"
            assert result[1]["address"] == "10.0.0.2"

    @pytest.mark.asyncio
    async def test_get_healthy_services_empty(self) -> None:
        """Should return empty list when no healthy services."""
        mock_consul = MagicMock()
        mock_consul.health.service.return_value = (None, [])

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            result = await client.get_healthy_services("test-service")

            assert result == []

    @pytest.mark.asyncio
    async def test_get_healthy_services_consul_exception(self) -> None:
        """Should return empty list on Consul exception."""
        import consul as consul_lib

        mock_consul = MagicMock()
        mock_consul.health.service.side_effect = consul_lib.ConsulException("Error")

        with patch("shared.utils.consul_client.consul.Consul", return_value=mock_consul):
            client = ConsulClient()
            result = await client.get_healthy_services("test-service")

            assert result == []
