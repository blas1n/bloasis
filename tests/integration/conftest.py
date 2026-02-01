"""Pytest fixtures for integration tests.

This module provides fixtures for Consul integration testing.
Tests will be skipped if Consul is not available or services are not registered.
"""

import os
import time
from typing import Generator

import consul
import pytest

# Consul connection settings - use 'consul' hostname in devcontainer
CONSUL_HOST = os.getenv("CONSUL_HOST", "consul")
CONSUL_PORT = int(os.getenv("CONSUL_PORT", "8500"))


def wait_for_consul(timeout: int = 30) -> bool:
    """Wait for Consul to be ready.

    Args:
        timeout: Maximum time to wait in seconds.

    Returns:
        True if Consul is ready, False otherwise.
    """
    client = consul.Consul(host=CONSUL_HOST, port=CONSUL_PORT)
    start = time.time()

    while time.time() - start < timeout:
        try:
            leader = client.status.leader()
            if leader:
                return True
        except Exception:
            pass
        time.sleep(1)

    return False


def wait_for_services(timeout: int = 60) -> bool:
    """Wait for services to register with Consul.

    Args:
        timeout: Maximum time to wait in seconds.

    Returns:
        True if all required services are registered, False otherwise.
    """
    client = consul.Consul(host=CONSUL_HOST, port=CONSUL_PORT)
    start = time.time()

    required_services = ["market-regime", "portfolio", "market-data"]

    while time.time() - start < timeout:
        try:
            services = client.agent.services()
            registered = [s.get("Service") for s in services.values()]

            if all(svc in registered for svc in required_services):
                return True
        except Exception:
            pass
        time.sleep(2)

    return False


@pytest.fixture(scope="session")
def consul_available() -> Generator[bool, None, None]:
    """Check if Consul is available.

    This fixture can be used by tests that need to know if Consul
    is available without necessarily skipping.

    Yields:
        True if Consul is available, False otherwise.
    """
    available = wait_for_consul(timeout=5)
    yield available


@pytest.fixture(scope="session")
def consul_client(consul_available: bool) -> Generator[consul.Consul, None, None]:
    """Create Consul client for testing.

    This fixture creates a Consul client if Consul is available.
    Tests using this fixture will be skipped if Consul is not available.

    Args:
        consul_available: Whether Consul is available.

    Yields:
        Consul client instance.
    """
    if not consul_available:
        pytest.skip("Consul not available")

    client = consul.Consul(host=CONSUL_HOST, port=CONSUL_PORT)
    yield client


@pytest.fixture(scope="session")
def services_registered(consul_available: bool) -> Generator[bool, None, None]:
    """Check if required services are registered with Consul.

    Args:
        consul_available: Whether Consul is available.

    Yields:
        True if all required services are registered, False otherwise.
    """
    if not consul_available:
        yield False
        return

    registered = wait_for_services(timeout=10)
    yield registered


@pytest.fixture(scope="session", autouse=True)
def setup_integration_environment(
    consul_available: bool,
    services_registered: bool,
) -> Generator[None, None, None]:
    """Setup integration test environment.

    This fixture runs automatically for all integration tests.
    It skips tests if Consul or services are not available.

    Args:
        consul_available: Whether Consul is available.
        services_registered: Whether required services are registered.
    """
    if not consul_available:
        pytest.skip("Consul not available - skipping integration tests")

    if not services_registered:
        pytest.skip("Services not registered with Consul - skipping integration tests")

    yield
