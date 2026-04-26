"""evidence_changelog — escalation step 2 (CHANGELOG/release-tag mining). Scaffold stub.

Unreachable on the happy path because evidence_static returns confidence>=threshold.
Stays deterministic regardless.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from releaselens.routing import get_model_for
from releaselens.schemas import ImplementationEvidence, Tool


class _Shard(TypedDict):
    feature_id: str
    tool: Tool


def evidence_changelog(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    ev = ImplementationEvidence(
        feature_id=shard["feature_id"],
        tool=shard["tool"],
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
