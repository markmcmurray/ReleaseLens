"""evidence_probe — terminal escalation step (runs DifferentialTests). Scaffold stub.

Unreachable on the happy path. Real implementation invokes the differential test runner
(architecture.md §9). LLM only interprets results — no LLM-as-judge (ADR-0005).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from releaselens.routing import get_model_for
from releaselens.schemas import ImplementationEvidence, Tool


class _Shard(TypedDict):
    feature_id: str
    tool: Tool


def evidence_probe(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    ev = ImplementationEvidence(
        feature_id=shard["feature_id"],
        tool=shard["tool"],
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
