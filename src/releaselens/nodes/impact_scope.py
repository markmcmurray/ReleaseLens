"""impact_scope — engineer-style scoping against the target (architecture.md §4.6, §7.5).

Cut-offs are enforced at the node level (not delegated to the LLM): existence-scan
budget and delta-size threshold. Stub returns a deterministic ImpactFinding.
"""

from __future__ import annotations

from typing import TypedDict

from releaselens.routing import get_model_for
from releaselens.schemas import ImpactFinding, TargetRef


class _Shard(TypedDict):
    feature_id: str
    target: TargetRef


def impact_scope(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    finding = ImpactFinding(
        feature_id=shard["feature_id"],
        target=shard["target"],
        current_behaviour="not_present",
        delta_description="STUB delta",
        affected_paths=[],
        effort_estimate="S",
        risk_notes=None,
        confidence=0.5,
    )
    return {"impacts": [finding]}
