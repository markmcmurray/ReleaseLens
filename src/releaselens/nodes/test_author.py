"""test_author — generate a DifferentialTest for a SpecClaim (architecture.md §7.3.1)."""

from __future__ import annotations

from typing import TypedDict

from releaselens.routing import get_model_for
from releaselens.schemas import DifferentialTest


class _Shard(TypedDict):
    claim_id: str
    iteration: int


def test_author(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    claim_id = shard["claim_id"]
    iteration = shard.get("iteration", 0)
    test = DifferentialTest(
        id=f"{claim_id}.test-{iteration:02d}",
        claim_id=claim_id,
        test_kind="behavioural_probe",
        setup="STUB setup",
        invocation="STUB invocation",
        expected="STUB expected",
        differentiator="STUB differentiator",
        iteration=iteration,
    )
    return {"differential_tests": [test]}
