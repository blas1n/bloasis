"""Tests for `bloasis.backtest.attribution`."""

from __future__ import annotations

import pytest

from bloasis.backtest.attribution import attribute_pnl_to_factors
from bloasis.scoring.rationale import FactorContribution, Rationale


def _rat(*pairs: tuple[str, float]) -> Rationale:
    return Rationale(
        contributions=tuple(
            FactorContribution(
                name=name,
                composite_score=0.5,
                weight=0.5,
                contribution=contrib,
            )
            for name, contrib in pairs
        )
    )


def test_attribution_distributes_pnl_proportionally() -> None:
    rat = _rat(("value", 0.3), ("momentum", 0.7))
    out = attribute_pnl_to_factors([(100.0, rat)])
    # 100 * 0.3/1.0 = 30 to value, 70 to momentum.
    assert out["value"] == pytest.approx(30.0)
    assert out["momentum"] == pytest.approx(70.0)
    assert out["unattributed"] == 0.0


def test_attribution_no_rationale_unattributed() -> None:
    out = attribute_pnl_to_factors([(50.0, None), (-10.0, None)])
    assert out["unattributed"] == pytest.approx(40.0)


def test_attribution_uses_abs_for_normalization() -> None:
    """Negative contributions still have positive normalized weight."""
    rat = _rat(("value", -0.6), ("momentum", 0.4))
    out = attribute_pnl_to_factors([(100.0, rat)])
    # Abs weights: 0.6, 0.4 → fractions 0.6, 0.4
    assert out["value"] == pytest.approx(60.0)
    assert out["momentum"] == pytest.approx(40.0)


def test_attribution_zero_contributions_to_unattributed() -> None:
    rat = _rat(("value", 0.0), ("momentum", 0.0))
    out = attribute_pnl_to_factors([(100.0, rat)])
    assert out["unattributed"] == pytest.approx(100.0)


def test_attribution_all_factor_keys_present() -> None:
    """Output keys cover the canonical composite list + unattributed."""
    out = attribute_pnl_to_factors([])
    assert "value" in out
    assert "momentum" in out
    assert "unattributed" in out


def test_attribution_sums_across_trades() -> None:
    rat = _rat(("value", 1.0))
    out = attribute_pnl_to_factors([(50.0, rat), (30.0, rat), (-20.0, rat)])
    assert out["value"] == pytest.approx(60.0)
