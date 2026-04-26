"""ImplementationEvidence, FeatureMatrix(Row) (architecture.md §4.3, §4.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Tool = Literal["warehouse", "pip", "uv"]
Method = Literal["static", "changelog", "probe"]


class ImplementationEvidence(BaseModel):
    feature_id: str
    tool: Tool
    method: Method
    found: bool
    version_first_seen: str | None = None
    confidence: float
    source_refs: list[str]
    raw_excerpt: str | None = None
    notes: str | None = None
    collected_at: datetime


class FeatureMatrixRow(BaseModel):
    feature_id: str
    per_tool: dict[Tool, ImplementationEvidence]
    consensus_status: Literal[
        "implemented_everywhere",
        "partial",
        "missing",
        "inconsistent",
    ]


class FeatureMatrix(BaseModel):
    pep_id: str
    rows: list[FeatureMatrixRow]
    generated_at: datetime
