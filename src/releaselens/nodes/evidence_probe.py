"""evidence_probe — terminal escalation step (runs DifferentialTests). Scaffold stub.

Unreachable on the happy path. Real implementation invokes the differential test runner
(architecture.md §9). LLM only interprets results — no LLM-as-judge (ADR-0005).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from releaselens.routing import get_model_for
from releaselens.schemas import Feature, ImplementationEvidence, Tool


class _Shard(TypedDict, total=False):
    feature_id: str
    tool: Tool
    feature: Feature


def evidence_probe(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    # See evidence_changelog: shard may be empty when reached via
    # conditional-edge fall-through. Stub stays defensive until the real
    # implementation lands.
    feature = shard.get("feature")
    feature_id = shard.get("feature_id") or (feature.id if feature else "unknown")
    tool: Tool = shard.get("tool") or "pip"
    ev = ImplementationEvidence(
        feature_id=feature_id,
        tool=tool,
        method="probe",
        found=False,
        version_first_seen=None,
        confidence=0.5,
        source_refs=["stub://probe"],
        raw_excerpt=None,
        notes="STUB",
        collected_at=datetime.now(UTC),
    )
    return {"evidence": [ev]}
