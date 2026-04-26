"""Unit tests for critic — accept / reject-loop / reject-exhausted Command targeting."""

from __future__ import annotations

import json

import pytest
from langgraph.types import Send

from releaselens import llm
from releaselens.nodes.critic import critic
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
_BASE_SHARD = {
    "test_id": _TEST.id,
    "claim_id": _TEST.claim_id,
    "claim_text": "claim text",
    "claim_type": "structural",
    "pep_section_ref": "PEP-658#specification",
    "iteration": 0,
    "test": _TEST,
    "history": [],
}


def _patch_llm(monkeypatch: pytest.MonkeyPatch, response: dict) -> None:
    monkeypatch.setattr(llm, "call", lambda *a, **kw: json.dumps(response))


def test_accept_routes_to_aggregator(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm(monkeypatch, {"coverage_score": 0.9, "determinism_score": 0.9, "feedback": ""})
    cmd = critic({**_BASE_SHARD})

    assert isinstance(cmd.goto, Send)
    assert cmd.goto.node == "test_authoring_aggregate"
    assert cmd.goto.arg["status"] == "accepted"
    assert cmd.goto.arg["final_test"] == _TEST
    assert cmd.goto.arg["iterations_used"] == 1
    assert cmd.update is not None
    [critique] = cmd.update["test_critiques"]
    assert critique.accept is True
    assert critique.overall_score >= 0.75


def test_reject_with_budget_remaining_loops_back_with_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_llm(
        monkeypatch,
        {
            "coverage_score": 0.2,
            "determinism_score": 0.3,
            "feedback": "Test depends on global state.",
        },
    )
    cmd = critic({**_BASE_SHARD, "iteration": 0})

    assert isinstance(cmd.goto, Send)
    assert cmd.goto.node == "test_author"
    assert cmd.goto.arg["iteration"] == 1
    assert cmd.goto.arg["prior_feedback"] == "Test depends on global state."
    assert cmd.goto.arg["prior_test"] == _TEST
    assert cmd.update is not None
    [critique] = cmd.update["test_critiques"]
    assert critique.accept is False
    assert critique.feedback == "Test depends on global state."


def test_reject_with_budget_exhausted_terminates(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_llm(monkeypatch, {"coverage_score": 0.1, "determinism_score": 0.1, "feedback": "weak"})
    # Default test_retry_budget=2 so iteration=2 is the last attempt.
    cmd = critic({**_BASE_SHARD, "iteration": 2})

    assert isinstance(cmd.goto, Send)
    assert cmd.goto.node == "test_authoring_aggregate"
    assert cmd.goto.arg["status"] == "budget_exhausted"
    assert cmd.goto.arg["final_test"] is None
    assert cmd.goto.arg["iterations_used"] == 3


def test_llm_failure_terminates_loop_via_aggregator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "call", lambda *a, **kw: "garbage not json")
    cmd = critic({**_BASE_SHARD})

    assert isinstance(cmd.goto, Send)
    assert cmd.goto.node == "test_authoring_aggregate"
    assert cmd.goto.arg["status"] == "budget_exhausted"
    assert cmd.update is not None
    assert len(cmd.update["errors"]) == 1
    assert cmd.update["errors"][0].node == "critic"
