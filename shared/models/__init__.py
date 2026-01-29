"""
BLOASIS Shared Models Package.

This package contains shared model definitions that are used across
multiple services. These models are primarily enumerations and value
objects that map to proto message fields.

Note: Per MSA architecture rules, Pydantic and SQLAlchemy models are
NOT shared between services. Each service maintains its own models
to ensure service independence. Only enumerations and simple value
objects that directly map to proto fields are shared.

Exports:
    MarketRegime: Enum for market regime classification (Tier 1, 6-hour cache).
    RiskProfile: Enum for user risk profile types (conservative, moderate, aggressive).
"""

from shared.models.market_regime import MarketRegime
from shared.models.risk_profile import RiskProfile

__all__ = [
    "MarketRegime",
    "RiskProfile",
]
