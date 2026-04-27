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

    def fake_call(node_name: str, *, system: str, user: str, metadata: dict | None = None) -> str:
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


def test_per_kind_contract_rejects_prose_in_behavioural_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM drift: free-form English in a behavioural_probe setup field should
    fail validation and surface as an error record (not a runnable test)."""
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")
    llm.register_stub(
        "test_author",
        json.dumps(
            {
                "test_kind": "behavioural_probe",
                "setup": "Create a Python package with the right metadata.",
                "invocation": "pip install foo",
                "expected": "data-dist-info-metadata",
                "differentiator": "older pip omits this",
            }
        ),
    )
    cmd = run_test_author({**_BASE_SHARD})
    assert cmd.update is not None
    assert cmd.update.get("errors"), "expected an error record for malformed test"
    assert "differential_tests" not in cmd.update


def test_per_kind_contract_rejects_non_module_attr_static_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """static_signature invocation must be ``module:attr`` — Python source
    snippets like ``import x; x.foo()`` are common LLM drift and should be
    rejected at parse time so the critic loop can iterate."""
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")
    llm.register_stub(
        "test_author",
        json.dumps(
            {
                "test_kind": "static_signature",
                "setup": "",
                "invocation": "import pkg; hasattr(pkg, 'x')",
                "expected": "True",
                "differentiator": "missing attr",
            }
        ),
    )
    cmd = run_test_author({**_BASE_SHARD})
    assert cmd.update is not None
    assert cmd.update.get("errors")
    assert "differential_tests" not in cmd.update


def test_per_kind_contract_accepts_well_formed_behavioural_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")
    llm.register_stub(
        "test_author",
        json.dumps(
            {
                "test_kind": "behavioural_probe",
                "setup": "pip==22.3\nrequests>=2.0",
                "invocation": "pip --version",
                "expected": "22.3",
                "differentiator": "older pip prints another version",
            }
        ),
    )
    cmd = run_test_author({**_BASE_SHARD})
    assert cmd.update is not None
    [test] = cmd.update["differential_tests"]
    assert test.test_kind == "behavioural_probe"
    assert "pip==22.3" in test.setup
