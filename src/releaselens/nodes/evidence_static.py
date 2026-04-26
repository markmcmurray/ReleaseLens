"""evidence_static — cheapest evidence method (static/grep). Scaffold stub."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from releaselens.routing import get_model_for
from releaselens.schemas import ImplementationEvidence, Tool


class _Shard(TypedDict):
    feature_id: str
    tool: Tool


def evidence_static(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    # Stub returns confidence=0.9 so the escalation ladder short-circuits.
    ev = ImplementationEvidence(
        feature_id=shard["feature_id"],
        tool=shard["tool"],
        method="static",
        found=True,
        version_first_seen="0.0.0-stub",
        confidence=0.9,
        source_refs=["stub://static"],
        raw_excerpt=None,
        notes="STUB",
        collected_at=datetime.now(UTC),
    )
    return {"evidence": [ev]}
