"""Tests for evidence_static.

Two coverage axes:

- Stub mode (RELEASELENS_LLM_MODE=stub + ripgrep stubs): exercises the full
  node pipeline without cassettes or rg subprocess. Asserts the evidence
  shape and that source_refs are real (``<tool>:<rel-path>:<line>``), not
  ``stub://static`` placeholders.
- LLM cassette replay path: stubs ripgrep with a hand-built hit, asks the
  node to classify, and asserts the verdict propagates — covers the
  classification branch with deterministic LLM via the cassette directory.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from releaselens.config import get_source_dir
from releaselens.nodes.evidence_static import (
    _FILE_GLOBS,
    _SYSTEM_PROMPT,
    build_user_prompt,
    evidence_static,
)
from releaselens.schemas import Feature, SpecClaim
from releaselens.tools import ripgrep
from releaselens.tools.ripgrep import RipgrepHit

_PIP_ROOT = get_source_dir("pip")


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
                claim_text=(
                    "Indexes that serve PEP 503 simple repositories MAY include a "
                    "data-dist-info-metadata attribute on each anchor link."
                ),
                claim_type="protocol",
                testable=True,
                pep_section_ref="PEP-658#specification",
            ),
            SpecClaim(
                id=f"{feature_id}.claim-02",
                feature_id=feature_id,
                claim_text=(
                    "Clients MAY then fetch the metadata file by appending "
                    "'.metadata' to the wheel URL."
                ),
                claim_type="behavioural",
                testable=True,
                pep_section_ref="PEP-658#client-behaviour",
            ),
        ],
    )


def test_evidence_static_stub_mode_returns_real_source_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")

    hit = RipgrepHit(
        path="src/pip/_internal/index/collector.py",
        line_no=414,
        line_text='        if anchor.get("data-dist-info-metadata") is not None:',
    )
    ripgrep.register_stub(
        "data-dist-info-metadata", _PIP_ROOT, [hit], file_globs=_FILE_GLOBS
    )

    out = evidence_static({"tool": "pip", "feature": _feature()})

    assert "evidence" in out
    [ev] = out["evidence"]
    assert ev.feature_id == _feature().id
    assert ev.tool == "pip"
    assert ev.method == "static"
    assert ev.found is True
    assert 0.0 <= ev.confidence <= 1.0
    assert ev.confidence >= 0.8
    assert ev.source_refs, "expected at least one source_ref"
    for ref in ev.source_refs:
        assert ref.startswith("pip:"), f"source_ref {ref!r} not <tool>-prefixed"
        assert "stub://" not in ref, "stub-mode must still emit real-shape refs"
    assert ev.collected_at.tzinfo is not None
    # Sanity: collected_at recent.
    assert (datetime.now(UTC) - ev.collected_at).total_seconds() < 5


def test_evidence_static_no_hits_falls_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """In real-LLM mode, no ripgrep hits → low-confidence not-found.

    Uses replay mode with an empty cassette dir so the LLM is never reached
    (the no-hits early return fires first). This is the path that lets the
    escalation ladder progress to ``evidence_changelog``.
    """
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "replay")
    monkeypatch.setenv("RELEASELENS_CASSETTES_DIR", str(tmp_path / "cassettes"))
    feature = _feature()
    # All candidates ripgrep will be asked about — stub each to an empty list.
    from releaselens.nodes.evidence_static import _derive_candidates

    for token in _derive_candidates(feature):
        ripgrep.register_stub(token, _PIP_ROOT, [], file_globs=_FILE_GLOBS)

    out = evidence_static({"tool": "pip", "feature": feature})
    [ev] = out["evidence"]
    assert ev.method == "static"
    assert ev.found is False
    assert ev.confidence < 0.5
    assert ev.source_refs == []


def test_evidence_static_llm_classification_via_cassette(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Classification path with a hand-authored cassette so we don't need Bedrock."""
    cassette_dir = tmp_path / "cassettes"
    monkeypatch.setenv("RELEASELENS_CASSETTES_DIR", str(cassette_dir))
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "replay")

    from releaselens import llm
    from releaselens.routing import get_model_for

    cfg = get_model_for("evidence_static", stub=False)
    hit = RipgrepHit(
        path="src/pip/_internal/index/collector.py",
        line_no=414,
        line_text='if anchor.get("data-dist-info-metadata") is not None:',
    )
    ripgrep.register_stub(
        "data-dist-info-metadata", _PIP_ROOT, [hit], file_globs=_FILE_GLOBS
    )

    feature = _feature()
    # Reuse the production prompt builder so this test breaks loudly if the
    # prompt format drifts (rather than producing a stale cassette key).
    user = build_user_prompt(feature, [("data-dist-info-metadata", hit)])
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    key = llm._cassette_key(cfg.model, messages, cfg.temperature, cfg.max_tokens)
    cassette_path = cassette_dir / "evidence_static" / f"{key}.json"
    cassette_path.parent.mkdir(parents=True, exist_ok=True)
    response_text = json.dumps(
        {
            "status": "found",
            "confidence": 0.92,
            "version_first_seen": "22.0",
            "strongest_match_index": 0,
            "notes": "definitive guard on data-dist-info-metadata anchor attr",
        }
    )
    cassette_path.write_text(
        json.dumps({"model": cfg.model, "messages": messages, "response": response_text})
    )

    out = evidence_static({"tool": "pip", "feature": feature})
    [ev] = out["evidence"]
    assert ev.found is True
    assert ev.confidence == pytest.approx(0.92)
    assert ev.version_first_seen == "22.0"
    assert any("collector.py" in ref for ref in ev.source_refs)
    assert ev.raw_excerpt and "data-dist-info-metadata" in ev.raw_excerpt
