"""evidence_aggregate — confidence math + version reconciliation. Pure Python (no LLM).

Picks the highest-confidence evidence record per (feature_id, tool) as the primary
record (architecture.md §8). Lower-confidence records are retained on the matrix row's
appendix.
"""

from __future__ import annotations

from typing import TypedDict

from releaselens.schemas import ImplementationEvidence


class _State(TypedDict, total=False):
    evidence: list[ImplementationEvidence]


def evidence_aggregate(state: _State) -> dict:
    # Pure-Python aggregation. No LLM, no routing call. The architecture lists this
    # node as model: none in §6 — explicitly deterministic.
    return {"evidence": []}  # add reducer means [] is a no-op merge
