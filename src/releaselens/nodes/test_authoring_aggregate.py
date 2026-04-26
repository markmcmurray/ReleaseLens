"""test_authoring_aggregate — terminal join for the test-author/critic loop.

Architecture.md §7.1 / §7.3.1 / §16: this is where every per-claim authoring
flow ends. Three producer paths converge here:

- ``critic`` accept path: emits ``status="accepted"`` with the final test.
- ``critic`` budget-exhausted path: emits ``status="budget_exhausted"`` with
  no final test.
- ``_fanout_test_author`` for non-testable claims: emits ``status="unverifiable"``
  directly without ever entering the loop.

Pure Python — no LLM, no model routing. One ``TestAuthoringResult`` per shard.
The shape of the final report's "spec claims we couldn't write a defensible
test for" appendix flows from this node.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from releaselens.schemas import DifferentialTest, TestAuthoringResult


class _Shard(TypedDict):
    claim_id: str
    status: Literal["accepted", "budget_exhausted", "unverifiable"]


class _LoopShard(_Shard, total=False):
    final_test: DifferentialTest | None
    iterations_used: int
    history: list[str]


def test_authoring_aggregate(shard: _LoopShard) -> dict:
    result = TestAuthoringResult(
        claim_id=shard["claim_id"],
        final_test=shard.get("final_test"),
        iterations_used=shard.get("iterations_used", 0),
        status=shard["status"],
        history=shard.get("history", []),
    )
    return {"test_authoring_results": [result]}
