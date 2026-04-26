"""Supporting schemas — see architecture.md §4.8 and §5.

PEPSource, ErrorRecord, ResolvedTarget, RegistryCapabilities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from releaselens.schemas.impact import TargetRef


class PEPSource(BaseModel):
    pep_id: str
    rst_url: str
    fetched_at: datetime
    body: str
    parsed_sections: dict[str, str]


class ErrorRecord(BaseModel):
    node: str
    severity: Literal["warn", "error"]
    message: str
    timestamp: datetime


class ResolvedTarget(BaseModel):
    ref: TargetRef
    pinned_version: str
    artefact_url: str


class RegistryCapabilities(BaseModel):
    serves_pep_691_json: bool
    serves_pep_658_metadata: bool
    serves_pep_740_attestations: bool
    notes: str | None = None
