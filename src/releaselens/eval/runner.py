"""`releaselens eval` orchestration (architecture.md §11.4, §11.6).

Loads fixtures, invokes the graph, collects matrices and features from final state,
and compares against ground-truth labels via `score.py`. Multi-run averaging via
`runs=N` produces N independent `RunResult`s the report layer can mean/stdev over.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from releaselens.eval.fixtures import PEPFixture, load_fixture
from releaselens.eval.score import EvidenceScores, Score, score_evidence, score_features
from releaselens.schemas import TargetRef


@dataclass(frozen=True)
class PEPResult:
    pep_id: str
    feature_score: Score
    evidence_scores: EvidenceScores


@dataclass(frozen=True)
class RunResult:
    run_id: str
    per_pep: dict[str, PEPResult]


def _default_target() -> TargetRef:
    return TargetRef(connector="devpi-public", package="stub-package", version=None)


def _ensure_pep_files_on_disk(pep_ids: list[str]) -> None:
    """Mirror cli._ensure_pep_files_on_disk so eval works without `releaselens run` first."""
    data_dir = Path("data/peps")
    fixtures_dir = Path("tests/fixtures/peps")
    data_dir.mkdir(parents=True, exist_ok=True)
    for pep_id in pep_ids:
        target = data_dir / f"{pep_id}.rst"
        if target.exists():
            continue
        fixture = fixtures_dir / f"{pep_id}.rst"
        if fixture.exists():
            target.write_bytes(fixture.read_bytes())


def run_pipeline(
    pep_ids: list[str],
    target: TargetRef,
    *,
    run_id: str | None = None,
    callbacks: list | None = None,
) -> dict[str, Any]:
    """Invoke the graph once for the given PEP ids and return final state."""
    from releaselens.graph import build_graph

    run_id = run_id or str(uuid.uuid4())
    graph = build_graph()
    config: dict[str, Any] = {"configurable": {"thread_id": run_id}}
    if callbacks:
        config["callbacks"] = callbacks
    return graph.invoke(
        {
            "run_id": run_id,
            "pep_ids": pep_ids,
            "target": target,
            "confidence_threshold": 0.8,
            "test_retry_budget": 2,
            "test_acceptance_threshold": 0.75,
        },
        config=config,
    )


def score_state(fixtures: list[PEPFixture], state: dict[str, Any]) -> dict[str, PEPResult]:
    features = state.get("features", []) or []
    matrices = state.get("matrices", {}) or {}
    return {
        fx.pep_id: PEPResult(
            pep_id=fx.pep_id,
            feature_score=score_features(fx, features),
            evidence_scores=score_evidence(fx, matrices.get(fx.pep_id)),
        )
        for fx in fixtures
    }


def load_fixtures(fixtures_dir: Path) -> list[PEPFixture]:
    return [load_fixture(p) for p in sorted(fixtures_dir.glob("PEP-*.yaml"))]


def run_eval(
    fixtures_dir: Path,
    *,
    runs: int = 1,
    target: TargetRef | None = None,
    callbacks_factory: Callable[[str], list] | None = None,
) -> list[RunResult]:
    fixtures = load_fixtures(fixtures_dir)
    if not fixtures:
        return []
    pep_ids = [fx.pep_id for fx in fixtures]
    _ensure_pep_files_on_disk(pep_ids)
    target = target or _default_target()

    from releaselens.eval.langfuse_scores import push_scores

    results: list[RunResult] = []
    for _ in range(runs):
        run_id = str(uuid.uuid4())
        callbacks = callbacks_factory(run_id) if callbacks_factory else None
        state = run_pipeline(pep_ids, target, run_id=run_id, callbacks=callbacks)
        per_pep = score_state(fixtures, state)
        push_scores(run_id, per_pep)
        results.append(RunResult(run_id=run_id, per_pep=per_pep))
    return results
