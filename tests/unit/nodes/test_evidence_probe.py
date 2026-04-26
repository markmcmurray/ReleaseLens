"""Tests for evidence_probe.

Three branches:
- stub mode: differential_runner stub returns pass; LLM stub fills the
  summary; assert non-stub source_refs and confidence in the pass band.
- ADR-0005 invariant: when the runner says ``pass`` (or ``fail``), the
  LLM's confidence is clamped into the band the outcome allows — the LLM
  cannot push confidence outside that range and cannot flip ``found``.
- no test available: the node returns a low-confidence sentinel rather
  than crashing.
"""

from __future__ import annotations

import pytest

from releaselens.nodes.evidence_probe import (
    _bound_confidence,
    evidence_probe,
)
from releaselens.schemas import (
    DifferentialTest,
    Feature,
    SpecClaim,
    TestAuthoringResult,
)
from releaselens.tools import differential_runner
from releaselens.tools.differential_runner import DifferentialResult


def _feature() -> Feature:
    feature_id = "pep-658.dist-info-metadata"
    return Feature(
        id=feature_id,
        pep_id="PEP-658",
        title="Static dist-info metadata",
        description="Index serves a separate dist-info file for each wheel.",
        pep_status="Final",
        pep_finalised_on=None,
        introduced_version_claim=None,
        spec_claims=[
            SpecClaim(
                id=f"{feature_id}.claim-01",
                feature_id=feature_id,
                claim_text="Indexes serve dist-info-metadata as a separate file.",
                claim_type="protocol",
                testable=True,
                pep_section_ref="PEP-658#specification",
            ),
        ],
    )


def _diff_test(claim_id: str = "pep-658.dist-info-metadata.claim-01") -> DifferentialTest:
    return DifferentialTest(
        id=f"{claim_id}.test-01",
        claim_id=claim_id,
        test_kind="behavioural_probe",
        setup="pip==22.3",
        invocation="pip install --dry-run --report - some-pkg",
        expected="data-dist-info-metadata",
        differentiator="pre-22.3 pip omits this field",
        iteration=0,
    )


def test_evidence_probe_stub_mode_returns_pass_band(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")
    test = _diff_test()
    differential_runner.register_stub(
        test.id,
        DifferentialResult(
            test_id=test.id,
            outcome="pass",
            detail="exit=0 expected_in_stdout=True",
            raw_output="data-dist-info-metadata observed",
        ),
    )
    auth_result = TestAuthoringResult(
        claim_id=test.claim_id,
        final_test=test,
        iterations_used=1,
        status="accepted",
        history=[],
    )

    out = evidence_probe(
        {
            "tool": "pip",
            "feature": _feature(),
            "test_authoring_results": [auth_result],
            "differential_tests": [test],
        }
    )

    [ev] = out["evidence"]
    assert ev.method == "probe"
    assert ev.found is True
    assert 0.8 <= ev.confidence <= 0.95, "pass-band confidence"
    assert any(r.startswith("differential-test:") for r in ev.source_refs)
    assert all("stub://" not in r for r in ev.source_refs)
    assert ev.raw_excerpt and "data-dist-info-metadata" in ev.raw_excerpt


def test_evidence_probe_llm_cannot_flip_pass_to_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0005: the runner's binary signal is authoritative.

    Even if the LLM "summary" returns confidence=0.1 (which would be in the
    error band, not the pass band), the node must clamp into the pass band
    [0.8, 0.95] and keep ``found=True``.
    """
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")

    import json

    from releaselens import llm

    llm.register_stub(
        "evidence_probe",
        json.dumps(
            {
                "confidence": 0.1,  # try to drag confidence way down
                "version_first_seen": None,
                "notes": "model thinks this is shaky",
            }
        ),
    )

    test = _diff_test()
    differential_runner.register_stub(
        test.id,
        DifferentialResult(
            test_id=test.id, outcome="pass", detail="exit=0", raw_output="ok"
        ),
    )

    out = evidence_probe(
        {
            "tool": "pip",
            "feature": _feature(),
            "differential_tests": [test],
        }
    )
    [ev] = out["evidence"]
    assert ev.found is True, "ADR-0005: pass cannot be flipped"
    assert ev.confidence >= 0.8, "confidence clamped to pass band"
    assert ev.confidence <= 0.95


def test_evidence_probe_no_test_available_returns_sentinel() -> None:
    out = evidence_probe(
        {
            "tool": "pip",
            "feature": _feature(),
            "differential_tests": [],
            "test_authoring_results": [],
        }
    )
    [ev] = out["evidence"]
    assert ev.method == "probe"
    assert ev.found is False
    assert ev.confidence < 0.5
    assert "no accepted DifferentialTest" in (ev.notes or "")


def test_bound_confidence_clamps_to_outcome_bands() -> None:
    # pass band [0.8, 0.95]
    assert _bound_confidence("pass", 0.99) == pytest.approx(0.95)
    assert _bound_confidence("pass", 0.1) == pytest.approx(0.8)
    assert _bound_confidence("pass", 0.85) == pytest.approx(0.85)
    # fail band [0.6, 0.85]
    assert _bound_confidence("fail", 0.99) == pytest.approx(0.85)
    assert _bound_confidence("fail", 0.0) == pytest.approx(0.6)
    # error band [0.0, 0.3]
    assert _bound_confidence("error", 0.9) == pytest.approx(0.3)
    # None -> midpoint
    assert _bound_confidence("pass", None) == pytest.approx(0.875)
