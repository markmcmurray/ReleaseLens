"""DifferentialTest, TestCritique, TestAuthoringResult (architecture.md §4.9–§4.11)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DifferentialTest(BaseModel):
    id: str
    claim_id: str
    test_kind: Literal["static_signature", "behavioural_probe", "metadata_assertion"]
    setup: str
    invocation: str
    expected: str
    differentiator: str
    iteration: int
    authored_by: Literal["test_author"] = "test_author"


class TestCritique(BaseModel):
    id: str
    test_id: str
    coverage_score: float
    determinism_score: float
    overall_score: float
    feedback: str
    accept: bool
    iteration: int


class TestAuthoringResult(BaseModel):
    claim_id: str
    final_test: DifferentialTest | None = None
    iterations_used: int
    status: Literal["accepted", "budget_exhausted", "unverifiable"]
    history: list[str]
