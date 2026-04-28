"""Tests for `bloasis.scoring.rationale` data carriers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bloasis.scoring.rationale import FactorContribution, Rationale, ScoredCandidate


def test_factor_contribution_immutable() -> None:
    fc = FactorContribution(name="value", composite_score=0.5, weight=0.18, contribution=0.09)
    with pytest.raises((AttributeError, TypeError)):
        fc.weight = 0.5  # type: ignore[misc]


def test_factor_contribution_inputs_default_empty() -> None:
    fc = FactorContribution(name="value", composite_score=0.5, weight=0.18, contribution=0.09)
    assert fc.inputs == {}


def test_rationale_default_empty_triggers_risks() -> None:
    r = Rationale(contributions=())
    assert r.triggers == ()
    assert r.risks == ()


def test_scored_candidate_holds_all_fields() -> None:
    ts = datetime.now(tz=UTC)
    sc = ScoredCandidate(
        symbol="AAPL",
        timestamp=ts,
        score=0.75,
        rationale=Rationale(contributions=()),
    )
    assert sc.symbol == "AAPL"
    assert sc.timestamp == ts
    assert sc.score == 0.75
    assert isinstance(sc.rationale, Rationale)
