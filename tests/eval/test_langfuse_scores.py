"""push_scores must be a no-op when tracing is inactive."""

from __future__ import annotations

from releaselens.eval.langfuse_scores import push_scores
from releaselens.eval.runner import PEPResult
from releaselens.eval.score import EvidenceScores, Score


def test_push_scores_noop_without_langfuse_env(monkeypatch) -> None:
    # Belt-and-braces: clear the env vars so tracing_active() is False even if
    # the developer's shell has them set.
    for var in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)

    per_pep = {
        "PEP-658": PEPResult(
            pep_id="PEP-658",
            feature_score=Score(tp=1, fp=0, fn=0),
            evidence_scores=EvidenceScores(aggregate=Score(tp=2, fp=0, fn=0)),
        )
    }

    # No raise, no network, no Langfuse import side effects.
    push_scores(run_id="run-x", per_pep=per_pep)
