"""critic — score a DifferentialTest against the rubric (architecture.md §4.10, §7.3.1).

Haiku by routing config — deliberately a cheaper tier than the author it
critiques. Asymmetric model tiers across the loop are the point: a cheaper
critic forces the author to write tests that are clearly defensible, not
just plausible-sounding.

The LLM outputs three numeric scores plus feedback prose. Code computes the
overall_score (0.6*coverage + 0.4*determinism per architecture §4.10) and
the accept boolean (overall_score >= test_acceptance_threshold). Keeping
those two derivations in code rather than asking the LLM for them is what
makes this a rubric, not LLM-as-judge (ADR-0005).

This node returns a langgraph Command. On accept, it dispatches to
test_authoring_aggregate with the final test. On reject + budget remaining,
it dispatches back to test_author with the feedback so the next iteration
sees what was wrong. On reject + budget exhausted, it dispatches to the
aggregator with status="budget_exhausted" so the loop terminates cleanly.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TypedDict

from langgraph.types import Command, Send
from pydantic import BaseModel, ValidationError

from releaselens import llm
from releaselens.config import get_thresholds
from releaselens.schemas import DifferentialTest, ErrorRecord, TestCritique

_COVERAGE_WEIGHT = 0.6
_DETERMINISM_WEIGHT = 0.4

_SYSTEM_PROMPT = """\
You are a critic evaluating differential tests for Python packaging tooling.

You will be given a single spec claim and a candidate test. Score the test on
two axes from 0.0 to 1.0:

- coverage: does this test exercise the claim's truth condition? A test that
  asserts on something tangential to the claim scores low. A test that
  precisely targets the assertion the claim makes scores high.
- determinism: does the test produce a binary signal under a clean fixture?
  A test whose result depends on environment state, ordering, or fuzzy
  comparisons scores low. A test that produces an unambiguous PASS/FAIL on
  a controlled fixture scores high.

Produce structured feedback the author can act on. If the test is weak, name
the specific weakness (e.g. "the invocation depends on global state") and
suggest a concrete fix. If the test is strong, leave feedback empty.

Output VALID JSON only. No prose before or after. The JSON must match exactly:

{
  "coverage_score": 0.0,
  "determinism_score": 0.0,
  "feedback": "Specific actionable feedback, or empty string if no issues."
}

Do not output the overall score or an accept/reject decision — those are
computed deterministically from your two scores. Your job is to judge the
two axes honestly and give the author something to work with on rejection.
"""


class _RawCritique(BaseModel):
    coverage_score: float
    determinism_score: float
    feedback: str


class _Shard(TypedDict):
    test_id: str
    claim_id: str
    claim_text: str
    claim_type: str
    pep_section_ref: str
    iteration: int
    test: DifferentialTest
    history: list[str]


def critic(shard: _Shard) -> Command:
    test_id = shard["test_id"]
    claim_id = shard["claim_id"]
    iteration = shard["iteration"]
    test = shard["test"]
    history = shard.get("history", [])
    thresholds = get_thresholds()
    threshold = thresholds.test_acceptance_threshold
    retry_budget = thresholds.test_retry_budget

    user_prompt = _build_user_prompt(shard)

    try:
        raw = llm.call("critic", system=_SYSTEM_PROMPT, user=user_prompt)
        parsed = _RawCritique.model_validate_json(llm.strip_json_fences(raw))
    except (ValidationError, ValueError, json.JSONDecodeError, llm.CassetteMissing) as exc:
        return _terminate_with_error(claim_id, iteration, history, exc)

    overall = (
        _COVERAGE_WEIGHT * parsed.coverage_score + _DETERMINISM_WEIGHT * parsed.determinism_score
    )
    accept = overall >= threshold
    critique = TestCritique(
        id=f"{test_id}.crit-{iteration:02d}",
        test_id=test_id,
        coverage_score=parsed.coverage_score,
        determinism_score=parsed.determinism_score,
        overall_score=overall,
        feedback=parsed.feedback,
        accept=accept,
        iteration=iteration,
    )
    new_history = [*history, critique.id]

    if accept:
        return Command(
            update={"test_critiques": [critique]},
            goto=Send(
                "test_authoring_aggregate",
                {
                    "claim_id": claim_id,
                    "status": "accepted",
                    "final_test": test,
                    "iterations_used": iteration + 1,
                    "history": new_history,
                },
            ),
        )

    if iteration < retry_budget:
        return Command(
            update={"test_critiques": [critique]},
            goto=Send(
                "test_author",
                {
                    "claim_id": claim_id,
                    "claim_text": shard["claim_text"],
                    "claim_type": shard["claim_type"],
                    "pep_section_ref": shard["pep_section_ref"],
                    "iteration": iteration + 1,
                    "prior_test": test,
                    "prior_feedback": critique.feedback,
                    "history": new_history,
                },
            ),
        )

    return Command(
        update={"test_critiques": [critique]},
        goto=Send(
            "test_authoring_aggregate",
            {
                "claim_id": claim_id,
                "status": "budget_exhausted",
                "final_test": None,
                "iterations_used": iteration + 1,
                "history": new_history,
            },
        ),
    )


def _build_user_prompt(shard: _Shard) -> str:
    test = shard["test"]
    return (
        f"Claim id: {shard['claim_id']}\n"
        f"Claim type: {shard['claim_type']}\n"
        f"Section ref: {shard['pep_section_ref']}\n\n"
        f"Claim text:\n{shard['claim_text']}\n\n"
        "Candidate test:\n"
        + json.dumps(
            {
                "test_kind": test.test_kind,
                "setup": test.setup,
                "invocation": test.invocation,
                "expected": test.expected,
                "differentiator": test.differentiator,
            },
            indent=2,
        )
    )


def _terminate_with_error(
    claim_id: str, iteration: int, history: list[str], exc: Exception
) -> Command:
    """Critic LLM failure ends the loop for this claim with budget_exhausted.

    Routing back to test_author would risk an infinite loop if the same prompt
    keeps failing. budget_exhausted is the architecture-defined terminal state
    for "we tried and couldn't get a defensible test" — same outcome here.
    """
    return Command(
        update={
            "errors": [
                ErrorRecord(
                    node="critic",
                    severity="error",
                    message=f"[{claim_id} iter={iteration}] {exc}",
                    timestamp=datetime.now(UTC),
                )
            ]
        },
        goto=Send(
            "test_authoring_aggregate",
            {
                "claim_id": claim_id,
                "status": "budget_exhausted",
                "final_test": None,
                "iterations_used": iteration + 1,
                "history": history,
            },
        ),
    )


# Stub for RELEASELENS_LLM_MODE=stub. Always accepts on iteration 0 so the
# smoke test loop terminates immediately without cassettes or Bedrock creds.
_STUB_RESPONSE = json.dumps(
    {
        "coverage_score": 0.95,
        "determinism_score": 0.95,
        "feedback": "",
    }
)
llm.register_stub("critic", _STUB_RESPONSE)
