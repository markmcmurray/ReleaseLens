"""ClaimEvidenceLink, VerificationResult (architecture.md §4.5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ClaimEvidenceLink(BaseModel):
    claim_id: str
    evidence_refs: list[str]
    aligned: bool
    misalignment_note: str | None = None


class VerificationResult(BaseModel):
    feature_id: str
    links: list[ClaimEvidenceLink]
    temporal_gap_days: int | None = None
    earliest_tool: Literal["warehouse", "pip", "uv"] | None = None
    notes: str | None = None
