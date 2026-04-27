"""Push eval F1 scores onto the Langfuse trace for a run.

Kept behind the same ``tracing_active()`` seam used by ``observability/langfuse.py``
so the runner stays infra-free when ``LANGFUSE_*`` env vars are absent. Score names
are namespaced by ``pep_id`` so multiple fixtures don't collide on a single run.
"""

from __future__ import annotations

from releaselens.eval.runner import PEPResult
from releaselens.observability.langfuse import tracing_active


def push_scores(run_id: str, per_pep: dict[str, PEPResult]) -> None:
    if not tracing_active():
        return

    from langfuse import Langfuse

    client = Langfuse()
    for pep_id, result in per_pep.items():
        client.score(
            trace_id=run_id,
            name=f"{pep_id}.feature_f1",
            value=result.feature_score.f1,
        )
        client.score(
            trace_id=run_id,
            name=f"{pep_id}.evidence_f1",
            value=result.evidence_scores.aggregate.f1,
        )
    client.flush()
