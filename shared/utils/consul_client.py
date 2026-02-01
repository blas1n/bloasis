"""Consul service registration client.

This module provides a reusable Consul client for service registration
and discovery. It supports gRPC health checks using the grpc.health.v1 protocol.
"""

import logging
import os
import socket
from typing import Any, Optional

import consul

logger = logging.getLogger(__name__)


def get_local_ip(target_host: str = "consul", target_port: int = 8500) -> str:
    """Get the local IP address that can reach the target host.

    This is useful for Consul service registration where Consul needs to
    perform health checks on the service. Returns the IP address of the
    network interface that can reach Consul.

    Args:
        target_host: Target hostname to determine route (default: "consul").
        target_port: Target port (default: 8500).

    Returns:
        Local IP address string. Falls back to "localhost" on error.

    Example:
        ```python
        ip = get_local_ip()
        await consul_client.register_grpc_service(
            service_name="market-regime",
            service_id="market-regime-1",
            host=ip,  # Use detected IP
            port=50051,
        )
        ```
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((target_host, target_port))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


class ConsulClient:
    """Client for Consul service registration and discovery.

    This client handles registration and deregistration of gRPC services
    with Consul. It uses Consul's native gRPC health check support.

    Example:
        ```python
        client = ConsulClient(host="consul", port=8500)
        await client.register_grpc_service(
            service_name="market-regime",
            service_id="market-regime-1",
            host="market-regime",
            port=50051,
            tags=["grpc", "tier1"],
        )
        ```
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        token: Optional[str] = None,
    ) -> None:
        """Initialize Consul client.

        Args:
            host: Consul host. Defaults to CONSUL_HOST env var or "consul".
            port: Consul port. Defaults to CONSUL_PORT env var or 8500.
            token: Optional ACL token for authentication.
        """
        self.host = host or os.getenv("CONSUL_HOST", "consul")
        self.port = port or int(os.getenv("CONSUL_PORT", "8500"))
        self.token = token or os.getenv("CONSUL_TOKEN")
        self._consul: Optional[consul.Consul] = None
        self.registered_services: list[str] = []

    @property
    def consul(self) -> consul.Consul:
        """Get or create Consul client instance.

        Returns:
            Consul client instance.
        """
        if self._consul is None:
            self._consul = consul.Consul(
                host=self.host,
                port=self.port,
                token=self.token,
            )
        return self._consul

    async def register_grpc_service(
        self,
        service_name: str,
        service_id: str,
        host: str,
        port: int,
        tags: Optional[list[str]] = None,
        check_interval: str = "10s",
        check_timeout: str = "5s",
    ) -> bool:
        """Register a gRPC service with Consul.

        Consul will perform gRPC health checks using the grpc.health.v1 protocol.
        The service must implement the gRPC health checking protocol.

        Args:
            service_name: Name of the service (e.g., "market-regime").
            service_id: Unique ID for this service instance (e.g., "market-regime-1").
            host: Hostname or IP where the service is running.
            port: gRPC port the service is listening on.
            tags: Optional list of tags for service discovery.
            check_interval: How often Consul performs health checks (e.g., "10s").
            check_timeout: Timeout for health check (e.g., "5s").

        Returns:
            True if registration succeeded, False otherwise.
        """
        try:
            # Create gRPC health check configuration
            # Consul calls grpc.health.v1.Health/Check on the specified address
            check = {
                "grpc": f"{host}:{port}",
                "interval": check_interval,
                "timeout": check_timeout,
                "grpc_use_tls": False,  # TLS should be enabled in production
            }

            # Register service with Consul
            self.consul.agent.service.register(
                name=service_name,
                service_id=service_id,
                address=host,
                port=port,
                tags=tags or [],
                check=check,
            )

            self.registered_services.append(service_id)
            logger.info(
                f"Registered service with Consul: {service_name} "
                f"(id={service_id}, address={host}:{port})"
            )
            return True

        except consul.ConsulException as e:
            logger.error(f"Failed to register service with Consul: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Consul registration: {e}")
            return False

    async def deregister_service(self, service_id: str) -> bool:
        """Deregister a service from Consul.

        Args:
            service_id: The service ID to deregister.

        Returns:
            True if deregistration succeeded, False otherwise.
        """
        try:
            self.consul.agent.service.deregister(service_id)

            if service_id in self.registered_services:
                self.registered_services.remove(service_id)

            logger.info(f"Deregistered service from Consul: {service_id}")
            return True

        except consul.ConsulException as e:
            logger.error(f"Failed to deregister service from Consul: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Consul deregistration: {e}")
            return False

    async def deregister_all(self) -> None:
        """Deregister all services registered by this client.

        This should be called during graceful shutdown to clean up
        all services registered by this client instance.
        """
        # Make a copy since we'll be modifying the list
        services_to_deregister = self.registered_services.copy()

        for service_id in services_to_deregister:
            await self.deregister_service(service_id)

        logger.info("Deregistered all services from Consul")

    async def get_service_health(self, service_name: str) -> list[dict[str, Any]]:
        """Get health status of a service from Consul.

        Args:
            service_name: Name of the service to query.

        Returns:
            List of health check results for all instances of the service.
            Each result contains 'Node', 'Service', and 'Checks' information.
        """
        try:
            _, health_data = self.consul.health.service(
                service=service_name,
                passing=False,  # Include all statuses, not just passing
            )

            results = []
            for entry in health_data:
                service_info = entry.get("Service", {})
                checks = entry.get("Checks", [])

                # Determine overall status from checks
                statuses = [check.get("Status", "unknown") for check in checks]
                if all(s == "passing" for s in statuses):
                    overall_status = "healthy"
                elif "critical" in statuses:
                    overall_status = "unhealthy"
                else:
                    overall_status = "warning"

                results.append({
                    "service_id": service_info.get("ID", ""),
                    "service_name": service_info.get("Service", ""),
                    "address": service_info.get("Address", ""),
                    "port": service_info.get("Port", 0),
                    "tags": service_info.get("Tags", []),
                    "status": overall_status,
                    "checks": [
                        {
                            "check_id": check.get("CheckID", ""),
                            "name": check.get("Name", ""),
                            "status": check.get("Status", "unknown"),
                            "output": check.get("Output", ""),
                        }
                        for check in checks
                    ],
                })

            return results

        except consul.ConsulException as e:
            logger.error(f"Failed to get service health from Consul: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting service health: {e}")
            return []

    async def get_healthy_services(
        self, service_name: str
    ) -> list[dict[str, Any]]:
        """Get only healthy instances of a service.

        This is useful for service discovery when you need to find
        available service instances.

        Args:
            service_name: Name of the service to query.

        Returns:
            List of healthy service instances with address and port.
        """
        try:
            _, health_data = self.consul.health.service(
                service=service_name,
                passing=True,  # Only passing health checks
            )

            results = []
            for entry in health_data:
                service_info = entry.get("Service", {})
                results.append({
                    "service_id": service_info.get("ID", ""),
                    "address": service_info.get("Address", ""),
                    "port": service_info.get("Port", 0),
                    "tags": service_info.get("Tags", []),
                })

            return results

        except consul.ConsulException as e:
            logger.error(f"Failed to get healthy services from Consul: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting healthy services: {e}")
            return []
