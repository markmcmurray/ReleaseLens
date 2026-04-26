"""FeatureReport, ReportSummary (architecture.md §4.7)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from releaselens.schemas.impact import TargetRef


class ReportSummary(BaseModel):
    feature_count: int
    pep_count: int
    budget_exhausted_claims: int = 0
    unverifiable_claims: int = 0
    top_temporal_gaps: list[str] = []
    top_impact_items: list[str] = []
    degraded: bool = False


class FeatureReport(BaseModel):
    run_id: str
    pep_ids: list[str]
    target: TargetRef
    markdown_path: Path
    summary: ReportSummary
    generated_at: datetime
