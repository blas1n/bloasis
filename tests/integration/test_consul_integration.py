"""E2E integration tests for Consul service registration.

This module contains integration tests that verify:
- Consul is running and accessible
- Services are registered correctly
- gRPC health checks are configured and passing
- Service tags are correct

These tests are designed to be idempotent and handle Consul unavailability
gracefully by skipping rather than failing.
"""

import consul


class TestConsulServiceRegistration:
    """Test service registration with Consul."""

    def test_consul_is_running(self, consul_client: consul.Consul) -> None:
        """Verify Consul is accessible and has elected a leader."""
        leader = consul_client.status.leader()
        assert leader is not None, "Consul should have an elected leader"
        assert len(leader) > 0, "Leader address should not be empty"

    def test_market_regime_registered(self, consul_client: consul.Consul) -> None:
        """Verify Market Regime service is registered with Consul."""
        services = consul_client.agent.services()

        # Check if market-regime service is registered
        # Service ID may be "market-regime-1" or similar
        service_names = [s.get("Service") for s in services.values()]
        service_ids = list(services.keys())

        is_registered = "market-regime" in service_names or any(
            "market-regime" in sid for sid in service_ids
        )

        assert is_registered, (
            f"Market Regime service should be registered. "
            f"Found services: {service_names}"
        )

    def test_portfolio_registered(self, consul_client: consul.Consul) -> None:
        """Verify Portfolio service is registered with Consul."""
        services = consul_client.agent.services()

        # Check if portfolio service is registered
        service_names = [s.get("Service") for s in services.values()]
        service_ids = list(services.keys())

        is_registered = "portfolio" in service_names or any(
            "portfolio" in sid for sid in service_ids
        )

        assert (
            is_registered
        ), f"Portfolio service should be registered. Found services: {service_names}"

    def test_market_regime_health_check(self, consul_client: consul.Consul) -> None:
        """Verify Market Regime gRPC health check is passing."""
        _, health_data = consul_client.health.service("market-regime", passing=True)

        assert len(health_data) > 0, (
            "Market Regime service should be healthy. "
            "Check if the service is running and gRPC health check is implemented."
        )

    def test_portfolio_health_check(self, consul_client: consul.Consul) -> None:
        """Verify Portfolio gRPC health check is passing."""
        _, health_data = consul_client.health.service("portfolio", passing=True)

        assert len(health_data) > 0, (
            "Portfolio service should be healthy. "
            "Check if the service is running and gRPC health check is implemented."
        )

class TestConsulHealthMonitoring:
    """Test Consul health monitoring capabilities."""

    def test_health_check_type_is_grpc(self, consul_client: consul.Consul) -> None:
        """Verify health checks use gRPC protocol.

        This is critical - we must use gRPC health checks, not HTTP.
        Services implement grpc.health.v1.Health/Check.
        """
        checks = consul_client.agent.checks()

        # Find gRPC health checks
        grpc_checks = []
        for check_id, check in checks.items():
            check_type = check.get("Type", "")
            check_definition = check.get("Definition", {})
            grpc_endpoint = check_definition.get("GRPC", "") if check_definition else ""

            # Check if it's a gRPC type or has gRPC endpoint configured
            is_grpc = (
                check_type.lower() == "grpc"
                or "grpc" in check_id.lower()
                or len(grpc_endpoint) > 0
            )

            if is_grpc:
                grpc_checks.append(
                    {
                        "check_id": check_id,
                        "type": check_type,
                        "status": check.get("Status", "unknown"),
                    }
                )

        assert len(grpc_checks) > 0, (
            f"Should have gRPC health checks configured. "
            f"Found checks: {list(checks.keys())}"
        )

    def test_service_tags(self, consul_client: consul.Consul) -> None:
        """Verify services have correct tags for discovery."""
        services = consul_client.agent.services()

        for service_id, service in services.items():
            service_name = service.get("Service", "")

            if service_name in ["market-regime", "portfolio"]:
                tags = service.get("Tags", [])

                # Services should have 'grpc' tag for identification
                assert (
                    "grpc" in tags
                ), f"Service {service_id} should have 'grpc' tag. Found tags: {tags}"

    def test_all_services_healthy(self, consul_client: consul.Consul) -> None:
        """Verify all registered BLOASIS services are healthy."""
        services = consul_client.agent.services()

        bloasis_services = ["market-regime", "portfolio"]
        unhealthy_services = []

        for _, service in services.items():
            service_name = service.get("Service", "")

            if service_name in bloasis_services:
                # Check health
                _, health_data = consul_client.health.service(
                    service_name, passing=True
                )

                if len(health_data) == 0:
                    unhealthy_services.append(service_name)

        assert (
            len(unhealthy_services) == 0
        ), f"All services should be healthy. Unhealthy services: {unhealthy_services}"

    def test_service_addresses_configured(self, consul_client: consul.Consul) -> None:
        """Verify services have addresses configured for service discovery."""
        services = consul_client.agent.services()

        for _, service in services.items():
            service_name = service.get("Service", "")

            if service_name in ["market-regime", "portfolio"]:
                address = service.get("Address", "")
                port = service.get("Port", 0)

                assert (
                    address
                ), f"Service {service_name} should have an address configured"
                assert (
                    port > 0
                ), f"Service {service_name} should have a valid port configured"


class TestConsulServiceDiscovery:
    """Test Consul service discovery capabilities."""

    def test_get_healthy_market_regime_instances(
        self, consul_client: consul.Consul
    ) -> None:
        """Verify we can discover healthy Market Regime instances."""
        _, health_data = consul_client.health.service("market-regime", passing=True)

        assert len(health_data) > 0, "Should have at least one healthy instance"

        # Verify instance has required fields for service discovery
        instance = health_data[0]
        service_info = instance.get("Service", {})

        assert (
            "Address" in service_info or "ID" in service_info
        ), "Service instance should have address information"
        assert "Port" in service_info, "Service instance should have port information"

    def test_get_healthy_portfolio_instances(
        self, consul_client: consul.Consul
    ) -> None:
        """Verify we can discover healthy Portfolio instances."""
        _, health_data = consul_client.health.service("portfolio", passing=True)

        assert len(health_data) > 0, "Should have at least one healthy instance"

        # Verify instance has required fields for service discovery
        instance = health_data[0]
        service_info = instance.get("Service", {})

        assert (
            "Address" in service_info or "ID" in service_info
        ), "Service instance should have address information"
        assert "Port" in service_info, "Service instance should have port information"

    def test_service_metadata(self, consul_client: consul.Consul) -> None:
        """Verify services have metadata for enhanced discovery."""
        services = consul_client.agent.services()

        for _, service in services.items():
            service_name = service.get("Service", "")

            if service_name in ["market-regime", "portfolio"]:
                # Check for service identification
                assert "ID" in service, f"Service {service_name} should have an ID"
                assert (
                    "Service" in service
                ), f"Service {service_name} should have a Service name"

                # Tags should exist for filtering
                tags = service.get("Tags", [])
                assert isinstance(
                    tags, list
                ), f"Service {service_name} tags should be a list"
