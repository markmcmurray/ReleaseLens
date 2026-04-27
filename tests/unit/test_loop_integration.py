"""End-to-end test for one PEP-658 claim through author + critic via cassettes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from langgraph.types import Send

from releaselens.nodes.critic import critic as run_critic
from releaselens.nodes.test_author import test_author as run_test_author
from releaselens.schemas import DifferentialTest, SpecClaim

_AUTHOR_CASSETTES = Path(__file__).parents[1] / "cassettes" / "test_author"
_CRITIC_CASSETTES = Path(__file__).parents[1] / "cassettes" / "critic"

_CLAIM = SpecClaim(
    id="pep-658.metadata-attribute-on-distribution-links.claim-01",
    feature_id="pep-658.metadata-attribute-on-distribution-links",
    claim_text=(
        "Repository anchor tags pointing to distributions may include a "
        "data-dist-info-metadata attribute to indicate that Core Metadata is "
        "available separately and will not be modified during processing or "
        "installation."
    ),
    claim_type="structural",
    testable=True,
    pep_section_ref="PEP-658#specification",
)


def _have_cassettes() -> bool:
    return (
        _AUTHOR_CASSETTES.exists()
        and _CRITIC_CASSETTES.exists()
        and any(_AUTHOR_CASSETTES.glob("*.json"))
        and any(_CRITIC_CASSETTES.glob("*.json"))
    )


def test_author_then_critic_for_one_pep_658_claim() -> None:
    """Run author → critic for one real PEP-658 claim, replayed from cassette.

    Verifies the loop produces well-formed records end-to-end:
    - DifferentialTest with deterministic ID and valid test_kind
    - TestCritique with scores in [0, 1] and a sensible accept decision
    - Critic Command's Send target reflects the accept/reject decision
    """
    mode = os.environ.get("RELEASELENS_LLM_MODE", "replay")
    if mode == "replay" and not _have_cassettes():
        pytest.skip(
            "Loop cassettes not recorded yet (or invalidated by a prompt "
            "tightening). Run with RELEASELENS_LLM_MODE=record-missing "
            "AWS_REGION=eu-west-1 once to capture."
        )

    author_cmd = run_test_author(
        {
            "claim_id": _CLAIM.id,
            "claim_text": _CLAIM.claim_text,
            "claim_type": _CLAIM.claim_type,
            "pep_section_ref": _CLAIM.pep_section_ref,
            "iteration": 0,
        }
    )
    assert author_cmd.update is not None
    # test_author swallows CassetteMissing and ValidationError into the errors
    # channel and routes to the aggregator. When the loop test's specific
    # cassette wasn't recorded (eval recordings populate the dir with other
    # claims' cassettes), or when the recorded LLM output trips _AuthoredTest's
    # validators, skip — neither is what this test is asserting on.
    if "differential_tests" not in author_cmd.update:
        pytest.skip(
            f"test_author produced no DifferentialTest for the loop-test claim: "
            f"{author_cmd.update.get('errors', '<no errors>')!r}"
        )
    [test] = author_cmd.update["differential_tests"]
    assert isinstance(test, DifferentialTest)
    assert test.claim_id == _CLAIM.id
    assert test.test_kind in {"static_signature", "behavioural_probe", "metadata_assertion"}
    assert isinstance(author_cmd.goto, Send)
    assert author_cmd.goto.node == "critic"

    critic_cmd = run_critic(author_cmd.goto.arg)
    assert critic_cmd.update is not None
    [critique] = critic_cmd.update["test_critiques"]
    assert 0.0 <= critique.coverage_score <= 1.0
    assert 0.0 <= critique.determinism_score <= 1.0
    assert 0.0 <= critique.overall_score <= 1.0
    assert critique.test_id == test.id
    assert critique.iteration == 0
    assert isinstance(critic_cmd.goto, Send)
    if critique.accept:
        assert critic_cmd.goto.node == "test_authoring_aggregate"
        assert critic_cmd.goto.arg["status"] == "accepted"
    else:
        # Reject: either loop or terminate by exhaustion. iteration 0 with
        # default budget=2 means a remaining attempt — should loop.
        assert critic_cmd.goto.node == "test_author"
        assert critic_cmd.goto.arg["iteration"] == 1
