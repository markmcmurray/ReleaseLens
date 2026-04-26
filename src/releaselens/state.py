"""PipelineState — TypedDict per architecture.md §3.

Plain TypedDict (not Pydantic) so LangGraph reducers compose cleanly. Pydantic models
live *inside* state for the record types that need validation. Every field that
receives concurrent writes from Send-fanned nodes is Annotated[..., add]; single-writer
fields are plain.

Get the reducer annotations wrong and the second concurrent write silently overwrites
the first.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict

from releaselens.schemas import (
    DifferentialTest,
    ErrorRecord,
    Feature,
    FeatureMatrix,
    FeatureReport,
    ImpactFinding,
    ImplementationEvidence,
    PEPSource,
    TargetRef,
    TestAuthoringResult,
    TestCritique,
    VerificationResult,
)


def _dict_merge[K, V](a: dict[K, V] | None, b: dict[K, V] | None) -> dict[K, V]:
    """Reducer for dict fields that receive concurrent writes from Send-fanned nodes.

    Architecture.md §3 lists `pep_sources` and `matrices` as plain dicts but §7.1/§7.2
    fans out their producers per pep_id. Without a merge reducer the last shard wins.
    Using shallow merge: shards write disjoint keys (pep_id), so collisions shouldn't
    occur on the success path. Flag if they do.
    """
    if a is None:
        return dict(b or {})
    if b is None:
        return dict(a)
    return {**a, **b}


class PipelineState(TypedDict, total=False):
    # ---- Inputs (set at graph invocation) ----
    run_id: str
    pep_ids: list[str]
    target: TargetRef
    confidence_threshold: float
    test_retry_budget: int
    test_acceptance_threshold: float

    # ---- Stage outputs (filled progressively) ----
    pep_sources: Annotated[dict[str, PEPSource], _dict_merge]
    features: Annotated[list[Feature], add]
    differential_tests: Annotated[list[DifferentialTest], add]
    test_critiques: Annotated[list[TestCritique], add]
    test_authoring_results: Annotated[list[TestAuthoringResult], add]
    evidence: Annotated[list[ImplementationEvidence], add]
    matrices: Annotated[dict[str, FeatureMatrix], _dict_merge]
    verifications: Annotated[list[VerificationResult], add]
    impacts: Annotated[list[ImpactFinding], add]
    report: FeatureReport | None

    # ---- Observability ----
    errors: Annotated[list[ErrorRecord], add]
