"""test_author — author a DifferentialTest for one SpecClaim (architecture.md §4.9, §7.3.1).

Sonnet by routing config. The LLM generates a single test that, if the spec is
correctly implemented by the tool under inspection, would produce a deterministic
binary signal distinguishing conformant from non-conformant implementations.

On iteration > 0, the prior attempt and the critic's structured feedback are
piped into the prompt verbatim — this is the architecture §7.3.1 "feedback
piping" rule. Without it the loop is just resampling, not evaluator-optimizer.

This node returns a langgraph Command that updates state with the new
DifferentialTest and dispatches a Send to the critic carrying the full claim
context, so the loop can iterate without an intermediate fan-out router.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal, TypedDict

from langgraph.types import Command, Send
from pydantic import BaseModel, ValidationError

from releaselens import llm
from releaselens.schemas import DifferentialTest, ErrorRecord

_SYSTEM_PROMPT = """\
You are an expert at writing differential tests for Python packaging tooling.

Given a single spec claim lifted from a PEP, your job is to author one test
that produces a deterministic binary signal: PASS if a tool implements the
claim correctly, FAIL if it does not. The test must distinguish conformant
from non-conformant implementations — a test that passes on every tool, or
fails on every tool, has no information value.

Output a single test as JSON. The "test_kind" field is one of:
- static_signature: tool exposes a function/class/attribute with a specific
  shape. Verified by importing the tool and inspecting its public surface.
- behavioural_probe: invoking the tool with controlled input produces specific
  output. Verified by running the tool against a fixture in an isolated venv.
- metadata_assertion: an HTTP GET against the registry returns a JSON or
  header value matching a specific shape.

Pick the test_kind that gives the highest-coverage, most-deterministic signal
for the claim at hand. Don't author a behavioural probe when a static signature
check would do — simpler tests are better tests.

The critic will score the test you produce on:
- coverage: does this test exercise the claim's truth condition?
- determinism: does it produce a binary signal under a clean fixture?

Author with the rubric in mind.

Output VALID JSON only. No prose before or after. The JSON must match exactly:

{
  "test_kind": "static_signature" | "behavioural_probe" | "metadata_assertion",
  "setup": "Human-readable preconditions and fixture description",
  "invocation": "Exact command, request, or code to run",
  "expected": "What a conformant implementation produces",
  "differentiator": "What would distinguish a non-conformant implementation"
}
"""


class _AuthoredTest(BaseModel):
    test_kind: Literal["static_signature", "behavioural_probe", "metadata_assertion"]
    setup: str
    invocation: str
    expected: str
    differentiator: str


class _Shard(TypedDict):
    claim_id: str
    claim_text: str
    claim_type: str
    pep_section_ref: str
    iteration: int


class _LoopShard(_Shard, total=False):
    prior_test: DifferentialTest | None
    prior_feedback: str | None
    history: list[str]


def test_author(shard: _LoopShard) -> Command:
    claim_id = shard["claim_id"]
    iteration = shard["iteration"]
    history = shard.get("history", [])
    user_prompt = _build_user_prompt(shard)

    try:
        raw = llm.call("test_author", system=_SYSTEM_PROMPT, user=user_prompt)
        authored = _AuthoredTest.model_validate_json(llm.strip_json_fences(raw))
    except (ValidationError, ValueError, json.JSONDecodeError, llm.CassetteMissing) as exc:
        return Command(
            update={
                "errors": [
                    ErrorRecord(
                        node="test_author",
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

    test = DifferentialTest(
        id=f"{claim_id}.test-{iteration:02d}",
        claim_id=claim_id,
        test_kind=authored.test_kind,
        setup=authored.setup,
        invocation=authored.invocation,
        expected=authored.expected,
        differentiator=authored.differentiator,
        iteration=iteration,
    )
    return Command(
        update={"differential_tests": [test]},
        goto=Send(
            "critic",
            {
                "test_id": test.id,
                "claim_id": claim_id,
                "claim_text": shard["claim_text"],
                "claim_type": shard["claim_type"],
                "pep_section_ref": shard["pep_section_ref"],
                "iteration": iteration,
                "test": test,
                "history": history,
            },
        ),
    )


def _build_user_prompt(shard: _LoopShard) -> str:
    base = (
        f"Claim id: {shard['claim_id']}\n"
        f"Claim type: {shard['claim_type']}\n"
        f"Section ref: {shard['pep_section_ref']}\n\n"
        f"Claim text:\n{shard['claim_text']}\n"
    )
    iteration = shard["iteration"]
    if iteration == 0:
        return base
    prior_test = shard.get("prior_test")
    prior_feedback = shard.get("prior_feedback") or ""
    if prior_test is None:
        return base
    return (
        base
        + "\n---\n"
        + f"This is iteration {iteration}. Your previous attempt was rejected.\n\n"
        + "Previous test:\n"
        + json.dumps(
            {
                "test_kind": prior_test.test_kind,
                "setup": prior_test.setup,
                "invocation": prior_test.invocation,
                "expected": prior_test.expected,
                "differentiator": prior_test.differentiator,
            },
            indent=2,
        )
        + "\n\nCritic feedback:\n"
        + prior_feedback
        + "\n\nProduce a new test addressing the feedback."
        + " Do not repeat the previous attempt verbatim."
    )


# Stub for RELEASELENS_LLM_MODE=stub. Lets the smoke test run end-to-end without
# cassettes or Bedrock creds.
_STUB_RESPONSE = json.dumps(
    {
        "test_kind": "static_signature",
        "setup": "STUB setup.",
        "invocation": "STUB invocation",
        "expected": "STUB expected",
        "differentiator": "STUB differentiator",
    }
)
llm.register_stub("test_author", _STUB_RESPONSE)
