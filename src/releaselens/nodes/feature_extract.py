"""feature_extract — derive Features and SpecClaims from a PEP. Scaffold stub."""

from __future__ import annotations

from typing import TypedDict

from releaselens.routing import get_model_for
from releaselens.schemas import Feature, SpecClaim


class _Shard(TypedDict):
    pep_id: str


def feature_extract(shard: _Shard) -> dict:
    _ = get_model_for(__name__)  # routing seam, even in stub
    pep_id = shard["pep_id"]
    feature_id = f"{pep_id.lower()}.feature-1"
    claim = SpecClaim(
        id=f"{feature_id}.claim-01",
        feature_id=feature_id,
        claim_text="STUB claim",
        claim_type="behavioural",
        testable=True,
        pep_section_ref=f"{pep_id}#stub",
    )
    feature = Feature(
        id=feature_id,
        pep_id=pep_id,
        title="STUB feature",
        description="STUB",
        pep_status="Final",
        pep_finalised_on=None,
        spec_claims=[claim],
    )
    return {"features": [feature]}
