"""Feature and SpecClaim — atomic capability and testable assertion (architecture.md §4.1, §4.2)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class SpecClaim(BaseModel):
    id: str
    feature_id: str
    claim_text: str
    claim_type: Literal["behavioural", "structural", "protocol", "metadata"]
    testable: bool
    pep_section_ref: str


class Feature(BaseModel):
    id: str
    pep_id: str
    title: str
    description: str
    pep_status: Literal["Draft", "Accepted", "Final", "Withdrawn", "Rejected"]
    pep_finalised_on: date | None = None
    spec_claims: list[SpecClaim]
    introduced_version_claim: str | None = None
