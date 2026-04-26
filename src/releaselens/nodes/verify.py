"""verify — claim ↔ evidence reconciliation per Feature (architecture.md §4.5, §7)."""

from __future__ import annotations

from typing import TypedDict

from releaselens.routing import get_model_for
from releaselens.schemas import ClaimEvidenceLink, VerificationResult


class _Shard(TypedDict):
    feature_id: str
    claim_ids: list[str]


def verify(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    feature_id = shard["feature_id"]
    links = [
        ClaimEvidenceLink(
            claim_id=cid,
            evidence_refs=[],
            aligned=True,
            misalignment_note=None,
        )
        for cid in shard["claim_ids"]
    ]
    result = VerificationResult(
        feature_id=feature_id,
        links=links,
        temporal_gap_days=0,
        earliest_tool="pip",
        notes="STUB",
    )
    return {"verifications": [result]}
