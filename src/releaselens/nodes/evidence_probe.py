"""evidence_probe — terminal escalation step (architecture.md §7.3.2 / §9, ADR-0005).

Reached when both static and changelog evidence are inconclusive. Picks the
``DifferentialTest`` the test-author/critic loop produced for one of the
feature's claims and hands it to ``differential_runner.run`` — the runner
returns a structured pass/fail/error signal with no LLM in the loop.

The Nova-lite step here is narrow: it summarises the runner's signal into a
human-readable ``notes`` field and assigns confidence. It does **not**
flip ``found``; the runner's binary signal is authoritative (ADR-0005).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, Field, ValidationError

from releaselens import llm
from releaselens.routing import get_model_for
from releaselens.schemas import (
    DifferentialTest,
    Feature,
    ImplementationEvidence,
    TestAuthoringResult,
    Tool,
)
from releaselens.tools import differential_runner
from releaselens.tools.differential_runner import DifferentialResult

_MAX_EXCERPT_CHARS = 500

_SYSTEM_PROMPT = """\
You read a differential-test runner result and write a one-sentence summary
plus a confidence value. The runner's `outcome` is authoritative — your
only job is interpretation. Do NOT contradict the runner.

Output VALID JSON only. No prose. Schema:

{
  "confidence": 0.0-1.0,
  "version_first_seen": "X.Y.Z" | null,
  "notes": "<= 200 chars"
}

Rules:
- outcome="pass": confidence in [0.8, 0.95]; high but never absolute.
- outcome="fail": confidence in [0.6, 0.85] (we are confident the feature
  is NOT present at the tested version).
- outcome="error": confidence <= 0.3; the test couldn't run.
- version_first_seen: only set if the test pinned a specific version in
  setup or invocation; null otherwise.
- notes: one sentence describing what the runner observed.
"""


class _Shard(TypedDict, total=False):
    tool: Tool
    feature: Feature
    differential_tests: list[DifferentialTest]
    test_authoring_results: list[TestAuthoringResult]


class _LLMSummary(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    version_first_seen: str | None = None
    notes: str = ""


def evidence_probe(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    feature = shard.get("feature")
    tool: Tool | None = shard.get("tool")
    if feature is None or tool is None:
        return _evidence(
            feature_id=(feature.id if feature else "unknown"),
            tool=tool or "pip",
            found=False,
            confidence=0.0,
            notes="probe skipped: shard missing feature/tool",
        )

    test = _pick_test_for(feature, shard)
    if test is None:
        return _evidence(
            feature_id=feature.id,
            tool=tool,
            found=False,
            confidence=0.1,
            notes="no accepted DifferentialTest available for any claim",
        )

    try:
        result = differential_runner.run(test)
    except (RuntimeError, LookupError) as exc:
        return _evidence(
            feature_id=feature.id,
            tool=tool,
            found=False,
            confidence=0.0,
            notes=f"differential runner failed: {exc}",
        )

    summary = _summarise(test, result)
    found = result.outcome == "pass"
    confidence = _bound_confidence(result.outcome, summary.confidence if summary else None)
    notes = (summary.notes if summary else None) or _fallback_notes(result)

    return _evidence(
        feature_id=feature.id,
        tool=tool,
        found=found,
        confidence=confidence,
        version_first_seen=(summary.version_first_seen if summary else None),
        source_refs=[
            f"differential-test:{test.id}",
            f"test-kind:{test.test_kind}",
        ],
        raw_excerpt=(result.raw_output or result.detail)[:_MAX_EXCERPT_CHARS],
        notes=notes,
    )


# ---- Test selection -------------------------------------------------------


def _pick_test_for(feature: Feature, shard: _Shard) -> DifferentialTest | None:
    """Pick the most recent accepted DifferentialTest for any of feature's claims.

    Prefers tests referenced from a ``status="accepted"`` TestAuthoringResult;
    falls back to the latest matching record in ``differential_tests`` so the
    probe still runs if the authoring metadata is missing.
    """
    claim_ids = {c.id for c in feature.spec_claims}
    results = shard.get("test_authoring_results") or []
    for res in reversed(results):
        if res.claim_id in claim_ids and res.status == "accepted" and res.final_test is not None:
            return res.final_test
    tests = shard.get("differential_tests") or []
    for t in reversed(tests):
        if t.claim_id in claim_ids:
            return t
    return None


# ---- LLM summarisation (narrow) ------------------------------------------


def build_user_prompt(test: DifferentialTest, result: DifferentialResult) -> str:
    return (
        f"Test id: {test.id}\n"
        f"Test kind: {test.test_kind}\n"
        f"Invocation: {test.invocation}\n"
        f"Expected: {test.expected}\n"
        f"Setup:\n{test.setup}\n\n"
        f"Runner outcome: {result.outcome}\n"
        f"Runner detail: {result.detail}\n"
        f"Raw output: {(result.raw_output or '')[:600]}\n"
    )


def _summarise(test: DifferentialTest, result: DifferentialResult) -> _LLMSummary | None:
    user = build_user_prompt(test, result)
    try:
        raw = llm.call("evidence_probe", system=_SYSTEM_PROMPT, user=user)
        return _LLMSummary.model_validate_json(llm.strip_json_fences(raw))
    except (ValidationError, ValueError, json.JSONDecodeError, llm.CassetteMissing,
            RuntimeError):
        return None


def _bound_confidence(
    outcome: Literal["pass", "fail", "error"], suggested: float | None
) -> float:
    """Clamp the LLM's confidence into the band the outcome allows.

    The runner's signal is authoritative; the LLM can scale within the band
    but cannot push confidence outside it (so a pass never reads as
    inconclusive, and an error never reads as confident).
    """
    if outcome == "pass":
        lo, hi = 0.8, 0.95
    elif outcome == "fail":
        lo, hi = 0.6, 0.85
    else:
        lo, hi = 0.0, 0.3
    if suggested is None:
        return (lo + hi) / 2
    return max(lo, min(hi, suggested))


def _fallback_notes(result: DifferentialResult) -> str:
    return f"runner outcome={result.outcome}: {result.detail[:160]}"


def _evidence(
    feature_id: str,
    tool: Tool,
    *,
    found: bool,
    confidence: float,
    version_first_seen: str | None = None,
    source_refs: list[str] | None = None,
    raw_excerpt: str | None = None,
    notes: str | None = None,
) -> dict:
    ev = ImplementationEvidence(
        feature_id=feature_id,
        tool=tool,
        method="probe",
        found=found,
        version_first_seen=version_first_seen,
        confidence=confidence,
        source_refs=source_refs or [],
        raw_excerpt=raw_excerpt,
        notes=notes,
        collected_at=datetime.now(UTC),
    )
    return {"evidence": [ev]}


# ---- Stub-mode LLM response (RELEASELENS_LLM_MODE=stub) -------------------
_STUB_RESPONSE = json.dumps(
    {
        "confidence": 0.85,
        "version_first_seen": None,
        "notes": "STUB summary",
    }
)
llm.register_stub("evidence_probe", _STUB_RESPONSE)
