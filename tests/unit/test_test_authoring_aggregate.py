"""Unit tests for test_authoring_aggregate — three terminal statuses."""

from __future__ import annotations

from releaselens.nodes.test_authoring_aggregate import (
    test_authoring_aggregate as run_aggregate,
)
from releaselens.schemas import DifferentialTest

_TEST = DifferentialTest(
    id="pep-658.metadata-attribute.claim-01.test-00",
    claim_id="pep-658.metadata-attribute.claim-01",
    test_kind="static_signature",
    setup="setup",
    invocation="invocation",
    expected="expected",
    differentiator="differentiator",
    iteration=0,
)


def test_accepted_status_carries_final_test() -> None:
    out = run_aggregate(
        {
            "claim_id": "pep-658.metadata-attribute.claim-01",
            "status": "accepted",
            "final_test": _TEST,
            "iterations_used": 1,
            "history": ["pep-658.metadata-attribute.claim-01.test-00.crit-00"],
        }
    )
    [result] = out["test_authoring_results"]
    assert result.status == "accepted"
    assert result.final_test == _TEST
    assert result.iterations_used == 1
    assert result.history == ["pep-658.metadata-attribute.claim-01.test-00.crit-00"]


def test_budget_exhausted_status_has_no_final_test() -> None:
    out = run_aggregate(
        {
            "claim_id": "pep-658.metadata-attribute.claim-01",
            "status": "budget_exhausted",
            "final_test": None,
            "iterations_used": 3,
            "history": ["c0", "c1", "c2"],
        }
    )
    [result] = out["test_authoring_results"]
    assert result.status == "budget_exhausted"
    assert result.final_test is None
    assert result.iterations_used == 3


def test_unverifiable_status_with_minimal_shard() -> None:
    """Non-testable claims arrive directly from _fanout_test_authoring with
    only claim_id and status set — defaults handle the rest."""
    out = run_aggregate(
        {
            "claim_id": "pep-658.motivation.claim-01",
            "status": "unverifiable",
        }
    )
    [result] = out["test_authoring_results"]
    assert result.status == "unverifiable"
    assert result.final_test is None
    assert result.iterations_used == 0
    assert result.history == []
