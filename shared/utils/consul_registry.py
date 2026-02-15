"""
Consul Service Registry for BLOASIS Microservices

Automatically registers gRPC services with Consul for dynamic service discovery.
Envoy Proxy uses Consul DNS to locate backend services.
"""

import atexit
import logging
import os
import socket
from typing import Optional

import consul

logger = logging.getLogger(__name__)


class ConsulServiceRegistry:
    """Manages service registration with Consul for service discovery."""

    def __init__(
        self,
        consul_host: str = "localhost",
        consul_port: int = 8500,
    ):
        """
        Initialize Consul client.

        Args:
            consul_host: Consul agent host (default: localhost)
            consul_port: Consul HTTP API port (default: 8500)
        """
        self.consul_client = consul.Consul(host=consul_host, port=consul_port)
        self.registered_services = []

    def register_grpc_service(
        self,
        service_name: str,
        grpc_port: int,
        service_id: Optional[str] = None,
        health_check_interval: str = "10s",
    ) -> str:
        """
        Register a gRPC service with Consul.

        Args:
            service_name: Service name (e.g., 'market-regime')
            grpc_port: gRPC port the service is listening on
            service_id: Unique service instance ID (auto-generated if None)
            health_check_interval: Health check interval (default: 10s)

        Returns:
            service_id: The registered service ID

        Example:
            >>> registry = ConsulServiceRegistry()
            >>> registry.register_grpc_service('market-regime', 50051)
            'market-regime-hostname-50051'
        """
        if service_id is None:
            hostname = socket.gethostname()
            service_id = f"{service_name}-{hostname}-{grpc_port}"

        # Use host.docker.internal so Envoy (in Docker) can reach localhost services
        # For production, this would be the actual service IP/hostname
        address = os.getenv("SERVICE_ADDRESS", "host.docker.internal")

        # Register service with Consul
        self.consul_client.agent.service.register(
            name=service_name,
            service_id=service_id,
            address=address,
            port=grpc_port,
            tags=[
                "grpc",
                "bloasis",
                f"port-{grpc_port}",
            ],
            # gRPC health check (requires grpc_health_probe or equivalent)
            check=consul.Check.ttl(health_check_interval),
            meta={
                "protocol": "grpc",
                "http2": "true",
            },
        )

        logger.info(
            f"Registered service '{service_name}' (ID: {service_id}) "
            f"at {address}:{grpc_port} with Consul"
        )

        # Track registered services for cleanup
        self.registered_services.append(service_id)

        # Auto-deregister on process exit
        atexit.register(self._deregister_service, service_id)

        # Mark service as healthy immediately
        self._mark_healthy(service_id)

        return service_id

    def _mark_healthy(self, service_id: str):
        """Mark service as passing health check."""
        try:
            self.consul_client.agent.check.ttl_pass(f"service:{service_id}")
            logger.debug(f"Marked service {service_id} as healthy")
        except Exception as e:
            logger.warning(f"Failed to mark service {service_id} as healthy: {e}")

    def _deregister_service(self, service_id: str):
        """Deregister service from Consul on shutdown."""
        try:
            self.consul_client.agent.service.deregister(service_id)
            logger.info(f"Deregistered service {service_id} from Consul")
        except Exception as e:
            logger.error(f"Failed to deregister service {service_id}: {e}")

    def heartbeat(self, service_id: str):
        """
        Send heartbeat to Consul for TTL-based health check.

        Call this periodically (e.g., every 5 seconds) to keep service healthy.

        Args:
            service_id: Service ID to send heartbeat for
        """
        try:
            self.consul_client.agent.check.ttl_pass(f"service:{service_id}")
        except Exception as e:
            logger.error(f"Heartbeat failed for {service_id}: {e}")

    def deregister_all(self):
        """Manually deregister all services (called on shutdown)."""
        for service_id in self.registered_services:
            self._deregister_service(service_id)
        self.registered_services.clear()


# Global registry instance (singleton)
_registry: Optional[ConsulServiceRegistry] = None


def get_registry() -> ConsulServiceRegistry:
    """Get or create the global Consul registry instance."""
    global _registry
    if _registry is None:
        consul_host = os.getenv("CONSUL_HOST", "localhost")
        consul_port = int(os.getenv("CONSUL_PORT", "8500"))
        _registry = ConsulServiceRegistry(consul_host, consul_port)
    return _registry


def register_service(service_name: str, grpc_port: int) -> str:
    """
    Convenience function to register a service with Consul.

    Args:
        service_name: Service name
        grpc_port: gRPC port

    Returns:
        service_id: Registered service ID

    Example:
        >>> from shared.utils.consul_registry import register_service
        >>> service_id = register_service('market-regime', 50051)
    """
    registry = get_registry()
    return registry.register_grpc_service(service_name, grpc_port)
