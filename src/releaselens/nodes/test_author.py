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
import re
from datetime import UTC, datetime
from typing import Literal, TypedDict

from langgraph.types import Command, Send
from pydantic import BaseModel, ValidationError, model_validator

from releaselens import llm
from releaselens.schemas import DifferentialTest, ErrorRecord

_SYSTEM_PROMPT = """\
You are an expert at writing differential tests for Python packaging tooling.

Given a single spec claim lifted from a PEP, your job is to author one test
that produces a deterministic binary signal: PASS if a tool implements the
claim correctly, FAIL if it does not. The test must distinguish conformant
from non-conformant implementations — a test that passes on every tool, or
fails on every tool, has no information value.

The test will be EXECUTED by an automated runner. Your output must conform
to the per-kind contract below — free-form English in the structured
fields makes the test unrunnable and the critic will reject it.

test_kind contracts:

1) static_signature
   setup:       leave empty ("") — invocation carries the import target.
   invocation:  exactly one ``module:attr`` import target.
                Examples: "pip._internal.metadata:dist_info_metadata",
                          "uv:__version__".
   expected:    a short string the runner can match against
                ``str(getattr(module, attr))``. Use "" if any resolution
                counts as pass.

2) behavioural_probe
   setup:       NEWLINE-SEPARATED LIST OF PEP 508 REQUIREMENT SPECS, one
                per line. Examples (each on its own line):
                  pip==22.3
                  uv>=0.4
                NO English. NO descriptive sentences. The runner pipes
                each line into ``uv pip install``.
   invocation:  shell-style command run inside the sandbox, e.g.
                "pip install --dry-run --report - some-pkg".
   expected:    a substring the runner asserts is present in stdout.

3) metadata_assertion
   setup:       one short sentence describing the registry endpoint
                under test (free-form OK here).
   invocation:  EXACTLY of the form "GET <url> :: <jsonpath>", e.g.
                "GET https://pypi.org/simple/foo/ :: $.meta.api_version".
   expected:    the JSON value the path should resolve to (a literal
                string, number, bool, or JSON-encoded object).

Pick the test_kind that gives the highest-coverage, most-deterministic
signal for the claim at hand. Prefer simpler kinds: don't author a
behavioural probe when a static signature check would do.

The critic will score on:
- coverage: does this test exercise the claim's truth condition?
- determinism: does it produce a binary signal under a clean fixture?
- format compliance: is each field shaped per the per-kind contract?

Output VALID JSON only. No prose before or after. The JSON must match exactly:

{
  "test_kind": "static_signature" | "behavioural_probe" | "metadata_assertion",
  "setup": "<per-kind contract>",
  "invocation": "<per-kind contract>",
  "expected": "<per-kind contract>",
  "differentiator": "What would distinguish a non-conformant implementation"
}
"""

_MODULE_ATTR_RE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")
_GET_JSONPATH_RE = re.compile(r"^GET\s+\S+\s+::\s+\S+", re.IGNORECASE)


class _AuthoredTest(BaseModel):
    test_kind: Literal["static_signature", "behavioural_probe", "metadata_assertion"]
    setup: str
    invocation: str
    expected: str
    differentiator: str

    @model_validator(mode="after")
    def _enforce_per_kind_contract(self) -> _AuthoredTest:
        """Reject LLM outputs whose fields don't match the test_kind contract.

        Rejection here surfaces as a ValidationError up to ``test_author``,
        which converts it into an error record. Within the critic loop a
        rejected attempt consumes one of the retry budget slots, so a
        well-targeted prompt should still converge in 1–2 iterations.
        """
        kind = self.test_kind
        if kind == "static_signature":
            target = self.invocation.strip()
            if not _MODULE_ATTR_RE.match(target):
                raise ValueError(
                    f"static_signature invocation must be 'module:attr'; got {target!r}"
                )
        elif kind == "behavioural_probe":
            packages = [line.strip() for line in self.setup.splitlines() if line.strip()]
            if not packages:
                raise ValueError("behavioural_probe setup must list at least one PEP 508 spec")
            for pkg in packages:
                if not _is_pep508(pkg):
                    raise ValueError(
                        f"behavioural_probe setup line is not pip-installable: {pkg!r}"
                    )
            if not self.invocation.strip():
                raise ValueError("behavioural_probe invocation must be a shell command")
        elif kind == "metadata_assertion":
            if not _GET_JSONPATH_RE.match(self.invocation.strip()):
                raise ValueError(
                    "metadata_assertion invocation must be 'GET <url> :: <jsonpath>'; "
                    f"got {self.invocation!r}"
                )
        return self


def _is_pep508(spec: str) -> bool:
    try:
        from packaging.requirements import InvalidRequirement, Requirement
    except ImportError:
        return " " not in spec
    try:
        Requirement(spec)
        return True
    except InvalidRequirement:
        return False


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
        raw = llm.call(
            "test_author",
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            metadata={"iteration": iteration, "claim_id": claim_id},
        )
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
        "setup": "",
        "invocation": "json:dumps",
        "expected": "",
        "differentiator": "STUB differentiator",
    }
)
llm.register_stub("test_author", _STUB_RESPONSE)
