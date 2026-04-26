"""feature_extract — derive Features and SpecClaims from a PEPSource.

Architecture.md §4.1 + §6: an LLM (Sonnet by routing config) reads a PEP and
decomposes it into atomic capabilities. One PEP yields N Features, each with
its own list of testable SpecClaims.

The extraction output schema mirrors the public Feature/SpecClaim schemas but
omits ID and pep_id fields — those are assigned deterministically here from
the PEP id and a slug of the feature title so the same PEP body always
produces the same IDs (architecture.md §11.1 — eval set arithmetic depends
on stable ids).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, ValidationError

from releaselens import llm
from releaselens.schemas import (
    ErrorRecord,
    Feature,
    PEPSource,
    SpecClaim,
)

_PEP_STATUS_PATTERN = re.compile(r"^Status:\s*(\S+)", re.MULTILINE)
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
_VALID_PEP_STATUSES = {"Draft", "Accepted", "Final", "Withdrawn", "Rejected"}

_SYSTEM_PROMPT = """\
You are an expert reader of Python packaging PEPs. Your job is to extract
atomic, testable features from a PEP and the spec claims that define each
feature's contract.

Definitions:
- A "feature" is an atomic capability. One PEP typically yields multiple
  features. Decompose by capability, not by section. Do NOT collapse the
  whole PEP into a single feature.
- A "spec claim" is one testable assertion about a feature, lifted from the
  PEP text. Use the model's own words from the PEP where possible.

Each claim has a claim_type:
- behavioural: tool produces output X when given input Y
- structural: data structure has a specific shape or field
- protocol: API exposes endpoint, URL, method, or content-type rule
- metadata: package or registry metadata contains a specific field

Set testable=false only when the claim cannot be verified by inspecting code
or running a tool (e.g. it's pure motivation or rationale). Most spec-section
claims are testable.

pep_section_ref must be of the form "PEP-XXX#<section-name>" where
<section-name> is a lowercase-hyphenated version of the section heading the
claim was lifted from.

Output VALID JSON only. No prose before or after. The JSON must match exactly:

{
  "features": [
    {
      "title": "Short title, 3-8 words",
      "description": "1-3 sentence summary of the capability",
      "introduced_version_claim": "X.Y.Z or null",
      "spec_claims": [
        {
          "claim_text": "The PEP text or close paraphrase",
          "claim_type": "behavioural" | "structural" | "protocol" | "metadata",
          "testable": true,
          "pep_section_ref": "PEP-XXX#section-name"
        }
      ]
    }
  ]
}
"""


class _ExtractedClaim(BaseModel):
    claim_text: str
    claim_type: Literal["behavioural", "structural", "protocol", "metadata"]
    testable: bool
    pep_section_ref: str


class _ExtractedFeature(BaseModel):
    title: str
    description: str
    introduced_version_claim: str | None = None
    spec_claims: list[_ExtractedClaim]


class _ExtractionOutput(BaseModel):
    features: list[_ExtractedFeature]


class _Shard(TypedDict):
    pep_id: str
    source: PEPSource


def feature_extract(shard: _Shard) -> dict:
    pep_id = shard["pep_id"]
    source = shard["source"]
    user_prompt = f"PEP id: {source.pep_id}\n\nPEP body:\n\n{source.body}"

    try:
        raw = llm.call("feature_extract", system=_SYSTEM_PROMPT, user=user_prompt)
        extraction = _ExtractionOutput.model_validate_json(_strip_json_fences(raw))
    except (ValidationError, ValueError, json.JSONDecodeError, llm.CassetteMissing) as exc:
        return _error(pep_id, f"feature_extract failed: {exc}")

    pep_status = _detect_pep_status(source.body)
    features = [_to_feature(pep_id, ef, pep_status) for ef in extraction.features]
    return {"features": features}


def _strip_json_fences(text: str) -> str:
    """Models occasionally wrap JSON in ```json fences. Strip them if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    return text


def _detect_pep_status(body: str) -> Literal["Draft", "Accepted", "Final", "Withdrawn", "Rejected"]:
    match = _PEP_STATUS_PATTERN.search(body)
    if match and match.group(1) in _VALID_PEP_STATUSES:
        return match.group(1)  # type: ignore[return-value]
    return "Draft"


def _to_feature(
    pep_id: str,
    extracted: _ExtractedFeature,
    pep_status: Literal["Draft", "Accepted", "Final", "Withdrawn", "Rejected"],
) -> Feature:
    feature_id = f"{pep_id.lower()}.{_slugify(extracted.title)}"
    claims = [
        SpecClaim(
            id=f"{feature_id}.claim-{idx:02d}",
            feature_id=feature_id,
            claim_text=c.claim_text,
            claim_type=c.claim_type,
            testable=c.testable,
            pep_section_ref=c.pep_section_ref,
        )
        for idx, c in enumerate(extracted.spec_claims, start=1)
    ]
    return Feature(
        id=feature_id,
        pep_id=pep_id,
        title=extracted.title,
        description=extracted.description,
        pep_status=pep_status,
        pep_finalised_on=None,
        spec_claims=claims,
        introduced_version_claim=extracted.introduced_version_claim,
    )


def _slugify(text: str) -> str:
    return _SLUG_PATTERN.sub("-", text.lower()).strip("-")


def _error(pep_id: str, message: str) -> dict:
    return {
        "errors": [
            ErrorRecord(
                node="feature_extract",
                severity="error",
                message=f"[{pep_id}] {message}",
                timestamp=datetime.now(UTC),
            )
        ]
    }


# Deterministic stub for RELEASELENS_LLM_MODE=stub. Lets the smoke test exercise
# the full graph end-to-end without recording a cassette or hitting Bedrock.
_STUB_RESPONSE = json.dumps(
    {
        "features": [
            {
                "title": "STUB feature",
                "description": "Stub feature emitted under RELEASELENS_LLM_MODE=stub.",
                "introduced_version_claim": None,
                "spec_claims": [
                    {
                        "claim_text": "STUB claim text.",
                        "claim_type": "behavioural",
                        "testable": True,
                        "pep_section_ref": "PEP-XXX#stub",
                    }
                ],
            }
        ]
    }
)
llm.register_stub("feature_extract", _STUB_RESPONSE)
