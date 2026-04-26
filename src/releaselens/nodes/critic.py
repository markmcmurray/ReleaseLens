"""critic — score a DifferentialTest against the rubric (architecture.md §7.3.1)."""

from __future__ import annotations

from typing import TypedDict

from releaselens.routing import get_model_for
from releaselens.schemas import DifferentialTest, TestAuthoringResult, TestCritique


class _Shard(TypedDict):
    test_id: str
    claim_id: str
    iteration: int
    test: DifferentialTest


def critic(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    test_id = shard["test_id"]
    claim_id = shard["claim_id"]
    iteration = shard.get("iteration", 0)
    # Stub: always accept on first iteration so the loop terminates immediately.
    critique = TestCritique(
        id=f"{test_id}.crit-{iteration:02d}",
        test_id=test_id,
        coverage_score=0.95,
        determinism_score=0.95,
        overall_score=0.95,
        feedback="",
        accept=True,
        iteration=iteration,
    )
    # On accept, also emit the terminal TestAuthoringResult.
    # Architecture §7.1 shows this as a separate aggregator node, but §16's repo
    # layout doesn't list one — folded here to match §16. Flag for cleanup.
    result = TestAuthoringResult(
        claim_id=claim_id,
        final_test=shard["test"],
        iterations_used=iteration + 1,
        status="accepted",
        history=[critique.id],
    )
    return {
        "test_critiques": [critique],
        "test_authoring_results": [result],
    }
