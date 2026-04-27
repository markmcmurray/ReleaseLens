"""Comparison procedure for eval (architecture.md §11.3).

Pure-Python set arithmetic. No LLM, no embedding similarity, no overlap heuristics.
Two stages:

* Feature decomposition — TP/FP/FN over `Feature.id` sets per PEP.
* Evidence detection — TP/FP/FN over `(feature_id, tool, found, version_first_seen)`
  tuples, with aggregate / per-tool / per-method facets.

Scope rule: evidence detection only compares `(feature_id, tool)` pairs the fixture
explicitly labels in `expected_evidence`. Omitting a tool from the fixture means
"N/A — don't score" rather than "expected absent." Generated evidence for an
unlabelled tool is ignored, not counted as FP.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from releaselens.eval.fixtures import PEPFixture
from releaselens.schemas import Feature, FeatureMatrix, ImplementationEvidence

EvidenceTuple = tuple[str, str, bool, str | None]
PrimaryMap = dict[tuple[str, str], ImplementationEvidence]


@dataclass(frozen=True)
class Score:
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass(frozen=True)
class EvidenceScores:
    aggregate: Score
    per_tool: dict[str, Score] = field(default_factory=dict)
    per_method: dict[str, Score] = field(default_factory=dict)


def _score(expected: set, generated: set) -> Score:
    return Score(
        tp=len(expected & generated),
        fp=len(generated - expected),
        fn=len(expected - generated),
    )


def score_features(fixture: PEPFixture, generated: Iterable[Feature]) -> Score:
    expected_ids = {f.id for f in fixture.features}
    generated_ids = {f.id for f in generated if f.pep_id == fixture.pep_id}
    return _score(expected_ids, generated_ids)


def _expected_pairs(fixture: PEPFixture) -> set[tuple[str, str]]:
    return {
        (feat.id, tool)
        for feat in fixture.features
        for tool in feat.expected_evidence
    }


def _expected_tuples(fixture: PEPFixture) -> set[EvidenceTuple]:
    out: set[EvidenceTuple] = set()
    for feat in fixture.features:
        for tool, ev in feat.expected_evidence.items():
            version = ev.version_first_seen if ev.found else None
            out.add((feat.id, tool, ev.found, version))
    return out


def _generated_from_matrix(matrix: FeatureMatrix) -> tuple[set[EvidenceTuple], PrimaryMap]:
    primary: PrimaryMap = {}
    tuples: set[EvidenceTuple] = set()
    for row in matrix.rows:
        for tool, ev in row.per_tool.items():
            version = ev.version_first_seen if ev.found else None
            tuples.add((row.feature_id, tool, ev.found, version))
            primary[(row.feature_id, tool)] = ev
    return tuples, primary


def score_evidence(fixture: PEPFixture, matrix: FeatureMatrix | None) -> EvidenceScores:
    expected = _expected_tuples(fixture)
    scope = _expected_pairs(fixture)

    if matrix is None:
        return EvidenceScores(aggregate=_score(expected, set()))

    generated_all, primary = _generated_from_matrix(matrix)
    generated = {t for t in generated_all if (t[0], t[1]) in scope}

    aggregate = _score(expected, generated)

    tools = {t[1] for t in expected | generated}
    per_tool = {
        tool: _score(
            {x for x in expected if x[1] == tool},
            {x for x in generated if x[1] == tool},
        )
        for tool in sorted(tools)
    }

    by_method_exp: dict[str, set[EvidenceTuple]] = defaultdict(set)
    by_method_gen: dict[str, set[EvidenceTuple]] = defaultdict(set)
    for x in expected:
        ev = primary.get((x[0], x[1]))
        bucket = ev.method if ev is not None else "missing"
        by_method_exp[bucket].add(x)
    for x in generated:
        ev = primary.get((x[0], x[1]))
        bucket = ev.method if ev is not None else "missing"
        by_method_gen[bucket].add(x)
    methods = set(by_method_exp) | set(by_method_gen)
    per_method = {
        m: _score(by_method_exp.get(m, set()), by_method_gen.get(m, set()))
        for m in sorted(methods)
    }

    return EvidenceScores(aggregate=aggregate, per_tool=per_tool, per_method=per_method)
