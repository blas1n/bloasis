"""
BLOASIS Shared Package

Shared code between services:
- proto: gRPC protocol buffer definitions
- utils: Shared utilities

Architecture rule: Services do not directly import other services.
All inter-service communication is done via gRPC or Redpanda.
"""

__version__ = "0.1.0"
