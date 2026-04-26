"""ImpactFinding, TargetRef (architecture.md §4.6, §4.8)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TargetRef(BaseModel):
    connector: str
    package: str
    version: str | None = None


class ImpactFinding(BaseModel):
    feature_id: str
    target: TargetRef
    current_behaviour: str
    delta_description: str
    affected_paths: list[str]
    effort_estimate: Literal["XS", "S", "M", "L", "too_large_to_estimate"]
    risk_notes: str | None = None
    confidence: float
