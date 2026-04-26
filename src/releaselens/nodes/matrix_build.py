"""matrix_build — deterministic per-PEP rollup across tools (architecture.md §4.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from releaselens.schemas import (
    Feature,
    FeatureMatrix,
    FeatureMatrixRow,
    ImplementationEvidence,
    Tool,
)


class _State(TypedDict, total=False):
    features: list[Feature]
    evidence: list[ImplementationEvidence]


_ALL_TOOLS: tuple[Tool, ...] = ("warehouse", "pip", "uv")


def matrix_build(state: _State) -> dict:
    features = state.get("features", [])
    evidence = state.get("evidence", [])

    # Index evidence by (feature_id, tool); pick highest confidence.
    primary: dict[tuple[str, str], ImplementationEvidence] = {}
    for ev in evidence:
        key = (ev.feature_id, ev.tool)
        prev = primary.get(key)
        if prev is None or ev.confidence > prev.confidence:
            primary[key] = ev

    matrices: dict[str, FeatureMatrix] = {}
    by_pep: dict[str, list[Feature]] = {}
    for f in features:
        by_pep.setdefault(f.pep_id, []).append(f)

    for pep_id, feats in by_pep.items():
        rows: list[FeatureMatrixRow] = []
        for f in feats:
            per_tool: dict[Tool, ImplementationEvidence] = {}
            for tool in _ALL_TOOLS:
                ev = primary.get((f.id, tool))
                if ev is not None:
                    per_tool[tool] = ev
            if per_tool and all(ev.found for ev in per_tool.values()):
                consensus = "implemented_everywhere"
            elif per_tool and any(ev.found for ev in per_tool.values()):
                consensus = "partial"
            else:
                consensus = "missing"
            rows.append(
                FeatureMatrixRow(
                    feature_id=f.id,
                    per_tool=per_tool,
                    consensus_status=consensus,
                )
            )
        matrices[pep_id] = FeatureMatrix(
            pep_id=pep_id,
            rows=rows,
            generated_at=datetime.now(UTC),
        )

    return {"matrices": matrices}
