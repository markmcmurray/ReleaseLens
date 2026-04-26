"""evidence_static — cheapest evidence method (architecture.md §7.3.2, §9).

Pipeline per shard ``{feature, tool}``:

1. Derive identifier-like search candidates from the feature's spec_claims.
2. ripgrep the tool's local source clone for each candidate.
3. Send the top hits + claim text to Nova-lite for found/not_found/ambiguous
   classification with a confidence score.
4. Pack the result into an ``ImplementationEvidence``. Confidence ≥ threshold
   short-circuits the escalation ladder; lower confidence falls through to
   ``evidence_changelog``.

The ripgrep call is wrapped in ``tool_span`` (inside the wrapper) and the LLM
call rides on ``llm.call`` so both surface under the node span in Langfuse.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, Field, ValidationError

from releaselens import llm
from releaselens.config import get_source_dir
from releaselens.routing import get_model_for
from releaselens.schemas import Feature, ImplementationEvidence, Tool
from releaselens.tools import ripgrep

_MAX_CANDIDATES_PER_FEATURE = 8
_MAX_HITS_PER_CANDIDATE = 5
_MAX_HITS_TO_LLM = 12
_MAX_SOURCE_REFS = 5
_MAX_EXCERPT_CHARS = 500
_FILE_GLOBS = ["*.py", "*.rst", "*.md", "*.txt"]

# Tokens lifted from claim_text. We want identifier-like things — kebab-case
# protocol fields ("data-dist-info-metadata"), snake_case symbols, dotted
# paths, content-type values. Two-char minimum, one capital/digit/symbol to
# avoid English-prose noise like "the" or "and".
_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_\-./]{2,}")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "must",
        "should",
        "when",
        "MUST",
        "SHOULD",
        "MAY",
        "tool",
        "tools",
        "field",
        "fields",
        "value",
        "values",
        "client",
        "server",
        "request",
        "response",
        "package",
        "packages",
    }
)

_SYSTEM_PROMPT = """\
You decide whether a Python packaging feature is implemented in a tool's
source tree, given (1) the feature's spec claims and (2) ripgrep hits in
that tree. Be conservative: structural mentions (docstrings, comments) are
weaker than function/method/constant definitions.

Output VALID JSON only. No prose. Schema:

{
  "status": "found" | "not_found" | "ambiguous",
  "confidence": 0.0-1.0,
  "version_first_seen": "X.Y.Z" | null,
  "strongest_match_index": int | null,
  "notes": "<= 200 chars"
}

Rules:
- "found" + confidence >= 0.8 only when at least one hit is a definition or
  a clearly load-bearing reference to the claim's key term.
- "ambiguous" when hits exist but none clearly implement the claim.
- "not_found" when no hits are relevant.
- version_first_seen: only set if a hit explicitly carries a version; else null.
- strongest_match_index: 0-based index into the provided hit list, or null.
"""


class _Shard(TypedDict):
    tool: Tool
    feature: Feature


class _LLMVerdict(BaseModel):
    status: Literal["found", "not_found", "ambiguous"]
    confidence: float = Field(ge=0.0, le=1.0)
    version_first_seen: str | None = None
    strongest_match_index: int | None = None
    notes: str = ""


def evidence_static(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    feature = shard["feature"]
    tool: Tool = shard["tool"]
    feature_id = feature.id

    source_dir = get_source_dir(tool)
    candidates = _derive_candidates(feature)
    hits = _gather_hits(candidates, source_dir) if candidates else []

    # Stub LLM mode is the smoke-test path. Short-circuit with a canned
    # high-confidence verdict so the escalation ladder doesn't fall through
    # to the still-stubbed downstream nodes (which crash on empty shards).
    if os.environ.get("RELEASELENS_LLM_MODE") == "stub":
        return _stub_evidence(feature_id, tool, hits, source_dir)

    if not candidates:
        return _evidence(feature_id, tool, found=False, confidence=0.0,
                         notes="no search candidates derivable from claims")

    if not hits:
        return _evidence(
            feature_id,
            tool,
            found=False,
            confidence=0.2,
            notes=f"no ripgrep hits for {len(candidates)} candidates in {source_dir}",
        )

    verdict = _classify(feature, hits)
    if verdict is None:
        return _evidence(
            feature_id,
            tool,
            found=False,
            confidence=0.0,
            notes="LLM classification failed; defer to changelog",
        )

    found = verdict.status == "found"
    confidence = verdict.confidence if found else min(verdict.confidence, 0.5)

    source_refs = _format_source_refs(tool, hits, source_dir, verdict.strongest_match_index)
    excerpt = _excerpt(hits, verdict.strongest_match_index)

    return _evidence(
        feature_id,
        tool,
        found=found,
        confidence=confidence,
        version_first_seen=verdict.version_first_seen,
        source_refs=source_refs,
        raw_excerpt=excerpt,
        notes=verdict.notes or f"static: {verdict.status} via {len(hits)} hits",
    )


# ---- Candidate derivation -------------------------------------------------


def _derive_candidates(feature: Feature) -> list[str]:
    """Pick identifier-shaped tokens from claim text.

    Heuristic: keep only tokens that contain at least one separator
    (``-_./``) or digit. That filters English prose ("Indexes", "Clients")
    while keeping protocol names (``data-dist-info-metadata``), dotted
    paths, version-bearing strings, and PEP-numbered references.
    """
    seen: set[str] = set()
    out: list[str] = []
    for claim in feature.spec_claims:
        for token in _TOKEN_PATTERN.findall(claim.claim_text):
            t = token.strip(".-_/")
            if len(t) < 4 or t in _STOPWORDS or t.lower() in _STOPWORDS:
                continue
            if not any(ch in t for ch in "-_./0123456789"):
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= _MAX_CANDIDATES_PER_FEATURE:
                return out
    return out


# ---- ripgrep aggregation --------------------------------------------------


def _gather_hits(candidates: list[str], root) -> list[tuple[str, ripgrep.RipgrepHit]]:
    """Returns a flat list of ``(candidate, hit)`` across all candidates."""
    out: list[tuple[str, ripgrep.RipgrepHit]] = []
    for cand in candidates:
        try:
            results = ripgrep.search(
                cand, root, file_globs=_FILE_GLOBS, max_results=_MAX_HITS_PER_CANDIDATE
            )
        except (RuntimeError, LookupError):
            # LookupError covers ripgrep's StubNotRegistered when a test
            # registers some but not all candidate tokens.
            continue
        for hit in results:
            out.append((cand, hit))
    return out


def _stub_evidence(
    feature_id: str,
    tool: Tool,
    hits: list[tuple[str, ripgrep.RipgrepHit]],
    source_dir,
) -> dict:
    """Stub-mode evidence: real source_refs if any hits arrived, canned otherwise.

    Confidence is pinned at 0.85 so the escalation ladder still short-circuits
    (matching the prior stub behaviour), but ``source_refs`` carry the real
    ``<tool>:<rel>:<line>`` shape when ripgrep stubs were registered, making
    this exercisable in tests.
    """
    if hits:
        refs = _format_source_refs(tool, hits, source_dir, strongest_idx=0)
        excerpt = _excerpt(hits, strongest_idx=0)
        notes = f"STUB classification over {len(hits)} ripgrep hit(s)"
    else:
        refs = [f"{tool}:STUB:0"]
        excerpt = None
        notes = "STUB classification (no ripgrep hits)"
    return _evidence(
        feature_id,
        tool,
        found=True,
        confidence=0.85,
        version_first_seen=None,
        source_refs=refs,
        raw_excerpt=excerpt,
        notes=notes,
    )


# ---- LLM classification ---------------------------------------------------


def build_user_prompt(
    feature: Feature, hits: list[tuple[str, ripgrep.RipgrepHit]]
) -> str:
    """Render the LLM user message. Public so tests can compute cassette keys."""
    rendered_hits = "\n".join(
        f"[{i}] candidate={cand!r} {hit.path}:{hit.line_no}: {hit.line_text.strip()[:200]}"
        for i, (cand, hit) in enumerate(hits[:_MAX_HITS_TO_LLM])
    )
    rendered_claims = "\n".join(
        f"- ({c.claim_type}) {c.claim_text}" for c in feature.spec_claims
    )
    return (
        f"Feature: {feature.title}\n"
        f"Description: {feature.description}\n\n"
        f"Spec claims:\n{rendered_claims}\n\n"
        f"Ripgrep hits:\n{rendered_hits}\n"
    )


def _classify(
    feature: Feature, hits: list[tuple[str, ripgrep.RipgrepHit]]
) -> _LLMVerdict | None:
    user = build_user_prompt(feature, hits)
    try:
        raw = llm.call("evidence_static", system=_SYSTEM_PROMPT, user=user)
        return _LLMVerdict.model_validate_json(llm.strip_json_fences(raw))
    except (ValidationError, ValueError, json.JSONDecodeError, llm.CassetteMissing,
            RuntimeError):
        return None


# ---- Evidence assembly ----------------------------------------------------


def _format_source_refs(
    tool: Tool,
    hits: list[tuple[str, ripgrep.RipgrepHit]],
    root,
    strongest_idx: int | None,
) -> list[str]:
    ordered = list(hits)
    if strongest_idx is not None and 0 <= strongest_idx < len(ordered):
        ordered.insert(0, ordered.pop(strongest_idx))
    refs: list[str] = []
    seen: set[str] = set()
    root_str = str(root).rstrip("/")
    for _, hit in ordered:
        rel = hit.path
        if rel.startswith(root_str):
            rel = rel[len(root_str) :].lstrip("/")
        ref = f"{tool}:{rel}:{hit.line_no}"
        if ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
        if len(refs) >= _MAX_SOURCE_REFS:
            break
    return refs


def _excerpt(
    hits: list[tuple[str, ripgrep.RipgrepHit]], strongest_idx: int | None
) -> str | None:
    if not hits:
        return None
    idx = strongest_idx if (strongest_idx is not None and 0 <= strongest_idx < len(hits)) else 0
    return hits[idx][1].line_text[:_MAX_EXCERPT_CHARS]


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
        method="static",
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
# Lets `releaselens run` exercise the node without a cassette. ripgrep is
# stubbed via tests/conftest.py registrations or by the CLI's stub fixtures.
_STUB_RESPONSE = json.dumps(
    {
        "status": "found",
        "confidence": 0.85,
        "version_first_seen": None,
        "strongest_match_index": 0,
        "notes": "STUB classification",
    }
)
llm.register_stub("evidence_static", _STUB_RESPONSE)
