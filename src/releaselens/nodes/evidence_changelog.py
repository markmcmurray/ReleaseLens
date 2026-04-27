"""evidence_changelog — escalation step 2 (CHANGELOG/release-tag mining). Scaffold stub.

Unreachable on the happy path because evidence_static returns confidence>=threshold.
Stays deterministic regardless.
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


def evidence_changelog(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    # LangGraph drops Send-payload fields when a conditional edge hands off
    # to a different node; the shard here may be empty. The real changelog
    # node will read state, but the stub just emits a sentinel record so
    # the pipeline keeps moving.
    feature = shard.get("feature")
    feature_id = shard.get("feature_id") or (feature.id if feature else "unknown")
    tool: Tool = shard.get("tool") or "pip"
    ev = ImplementationEvidence(
        feature_id=feature_id,
        tool=tool,
        method="changelog",
        found=True,
        version_first_seen="0.0.0-stub",
        confidence=0.7,
        source_refs=["stub://changelog"],
        raw_excerpt=None,
        notes="STUB",
        collected_at=datetime.now(UTC),
    )
    return {"evidence": [ev]}
