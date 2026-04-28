"""Tests for report_render.

Two coverage axes:

- Golden-file: render a deterministic fixture state and diff the markdown bytes
  against ``tests/fixtures/reports/expected_pep_658.md``. Determinism is the
  contract — any intentional template change re-pins the golden file.
- Edge cases: empty matrices/verifications/impacts must not crash, and a
  feature without ``pep_finalised_on`` must skip the Mermaid timeline cleanly.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from releaselens.nodes.report_render import report_render
from releaselens.schemas import (
    ClaimEvidenceLink,
    Feature,
    FeatureMatrix,
    FeatureMatrixRow,
    ImpactFinding,
    ImplementationEvidence,
    SpecClaim,
    TargetRef,
    VerificationResult,
)

_GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "reports" / "expected_pep_658.md"


def _fixture_state() -> dict:
    feature = Feature(
        id="pep-658.metadata-file-serving",
        pep_id="PEP-658",
        title="Static dist-info metadata",
        description="Index serves a separate dist-info file for each wheel.",
        pep_status="Final",
        pep_finalised_on=date(2021, 5, 17),
        spec_claims=[
            SpecClaim(
                id="c1",
                feature_id="pep-658.metadata-file-serving",
                claim_text="Indexes MAY include data-dist-info-metadata.",
                claim_type="protocol",
                testable=True,
                pep_section_ref="PEP-658#spec",
            ),
        ],
    )
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    target = TargetRef(connector="devpi-public", package="stub-package", version="0.1.0")
    matrix = FeatureMatrix(
        pep_id="PEP-658",
        rows=[
            FeatureMatrixRow(
                feature_id=feature.id,
                per_tool={
                    "warehouse": ImplementationEvidence(
                        feature_id=feature.id,
                        tool="warehouse",
                        method="static",
                        found=True,
                        version_first_seen="1.0",
                        confidence=0.95,
                        source_refs=["https://github.com/pypi/warehouse/pull/9972"],
                        raw_excerpt="data-dist-info-metadata anchor attr",
                        collected_at=ts,
                    ),
                    "pip": ImplementationEvidence(
                        feature_id=feature.id,
                        tool="pip",
                        method="changelog",
                        found=True,
                        version_first_seen="22.0",
                        confidence=0.92,
                        source_refs=["https://github.com/pypa/pip/blob/main/NEWS.rst"],
                        raw_excerpt="Support PEP 658 metadata files.",
                        collected_at=ts,
                    ),
                    "uv": ImplementationEvidence(
                        feature_id=feature.id,
                        tool="uv",
                        method="probe",
                        found=False,
                        confidence=0.40,
                        source_refs=[],
                        raw_excerpt=None,
                        collected_at=ts,
                    ),
                },
                consensus_status="partial",
            ),
        ],
        generated_at=ts,
    )
    verification = VerificationResult(
        feature_id=feature.id,
        links=[
            ClaimEvidenceLink(
                claim_id="c1",
                evidence_refs=["https://github.com/pypi/warehouse/pull/9972"],
                aligned=True,
            ),
        ],
        temporal_gap_days=107,
        earliest_tool="warehouse",
        notes="Warehouse shipped first.",
    )
    impact = ImpactFinding(
        feature_id=feature.id,
        target=target,
        current_behaviour="No metadata files served.",
        delta_description="Add per-wheel .metadata sidecar.",
        affected_paths=["devpi_server/views.py"],
        effort_estimate="M",
        risk_notes="Cache invalidation.",
        confidence=0.85,
    )
    return {
        "run_id": "test-run-pep-658",
        "pep_ids": ["PEP-658"],
        "target": target,
        "features": [feature],
        "matrices": {"PEP-658": matrix},
        "verifications": [verification],
        "impacts": [impact],
    }


def test_report_render_matches_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    out = report_render(_fixture_state())
    rendered = out["report"].markdown_path.read_text()

    if not _GOLDEN.exists():
        _GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        _GOLDEN.write_text(rendered)
        pytest.fail(
            f"Golden file did not exist; wrote {_GOLDEN}. "
            "Inspect it, then re-run the test."
        )

    expected = _GOLDEN.read_text()
    assert rendered == expected, (
        "Rendered report drifted from golden file. If this is intentional, "
        f"rm {_GOLDEN} and re-run the test to regenerate."
    )


def test_report_render_empty_state_does_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    target = TargetRef(connector="devpi-public", package="stub-package", version=None)
    out = report_render(
        {
            "run_id": "empty-run",
            "pep_ids": ["PEP-658"],
            "target": target,
            "features": [],
            "matrices": {},
            "verifications": [],
            "impacts": [],
        }
    )

    rendered = out["report"].markdown_path.read_text()
    assert "# ReleaseLens Report" in rendered
    assert "## Per-PEP matrix" in rendered
    assert "```mermaid" not in rendered, "no timeline expected when no data"


def test_report_render_skips_timeline_without_finalised_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    state = _fixture_state()
    # Strip pep_finalised_on — timeline must skip cleanly.
    feature = state["features"][0]
    state["features"] = [feature.model_copy(update={"pep_finalised_on": None})]

    out = report_render(state)
    rendered = out["report"].markdown_path.read_text()

    assert "```mermaid" not in rendered
    # Matrix table still renders.
    assert "[pep-658.metadata-file-serving]" in rendered
    assert "| partial |" in rendered
