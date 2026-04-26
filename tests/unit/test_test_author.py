"""Unit tests for test_author — stub mode, error handling, feedback piping."""

from __future__ import annotations

import json

import pytest
from langgraph.types import Send

from releaselens import llm
from releaselens.nodes.test_author import test_author as run_test_author
from releaselens.schemas import DifferentialTest

_BASE_SHARD = {
    "claim_id": "pep-658.metadata-attribute.claim-01",
    "claim_text": "Repositories may include a data-dist-info-metadata attribute.",
    "claim_type": "structural",
    "pep_section_ref": "PEP-658#specification",
    "iteration": 0,
}


def test_stub_returns_command_targeting_critic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")
    cmd = run_test_author({**_BASE_SHARD})

    assert isinstance(cmd.goto, Send)
    assert cmd.goto.node == "critic"
    assert cmd.update is not None
    [test] = cmd.update["differential_tests"]
    assert isinstance(test, DifferentialTest)
    assert test.id == "pep-658.metadata-attribute.claim-01.test-00"
    assert test.iteration == 0
    assert test.test_kind in {"static_signature", "behavioural_probe", "metadata_assertion"}


def test_loop_iteration_pipes_prior_feedback_into_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")
    captured: dict[str, str] = {}

    def fake_call(node_name: str, *, system: str, user: str) -> str:
        captured["user"] = user
        return llm._STUB_RESPONSES[node_name]

    monkeypatch.setattr(llm, "call", fake_call)

    prior_test = DifferentialTest(
        id="pep-658.metadata-attribute.claim-01.test-00",
        claim_id="pep-658.metadata-attribute.claim-01",
        test_kind="static_signature",
        setup="prior setup",
        invocation="prior invocation",
        expected="prior expected",
        differentiator="prior differentiator",
        iteration=0,
    )
    run_test_author(
        {
            **_BASE_SHARD,
            "iteration": 1,
            "prior_test": prior_test,
            "prior_feedback": "Test depends on global state; isolate the fixture.",
            "history": ["pep-658.metadata-attribute.claim-01.test-00.crit-00"],
        }
    )

    assert "iteration 1" in captured["user"]
    assert "prior setup" in captured["user"]
    assert "Test depends on global state" in captured["user"]


def test_malformed_response_returns_error_command_no_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "call", lambda *a, **kw: "this is not json")
    cmd = run_test_author({**_BASE_SHARD})

    assert isinstance(cmd.goto, Send)
    assert cmd.goto.node == "test_authoring_aggregate"
    assert cmd.goto.arg["status"] == "budget_exhausted"
    assert cmd.update is not None
    assert len(cmd.update["errors"]) == 1
    assert cmd.update["errors"][0].node == "test_author"


def test_stub_response_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity check: the registered stub passes our own private extraction model."""
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")
    cmd = run_test_author({**_BASE_SHARD})
    assert cmd.update is not None
    assert json.loads(cmd.update["differential_tests"][0].model_dump_json())
