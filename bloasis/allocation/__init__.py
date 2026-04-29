"""Allocation layer — strategy composition (core + satellite blending).

Phase 1 supports two strategy types:
  - `spy_passive`: lump-sum buy SPY and hold (the safety floor).
  - `strategy`: bloasis rule/ML scorer signals (the alpha attempt).

The composer translates `allocation.strategies` config into per-leg
capital and returns an aggregated execution plan. Live trade flows
through this on the way to the broker so a misbehaving strategy never
exceeds its slice of capital.
"""

from bloasis.allocation.composer import AllocationLeg, ExecutionPlan, StrategyComposer

__all__ = [
    "AllocationLeg",
    "ExecutionPlan",
    "StrategyComposer",
]
