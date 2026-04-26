"""evidence_changelog — escalation step 2: commit + release archaeology.

architecture.md §7.3.2 / §9. Reached when ``evidence_static`` returns
confidence below threshold. Mines the tool's GitHub repo for commit messages
and release notes that mention the PEP id (or claim keywords), then asks
Nova-lite to infer ``version_first_seen`` and a confidence from the
artefacts. ``source_refs`` carry stable GitHub URLs so the report appendix
can cite them.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, Field, ValidationError

from releaselens import llm
from releaselens.config import get_repo_for
from releaselens.routing import get_model_for
from releaselens.schemas import Feature, ImplementationEvidence, Tool
from releaselens.tools import github

_MAX_COMMITS = 20
_MAX_RELEASES = 10
_MAX_RELEASE_NOTES_FETCH = 3
_MAX_RELEASE_NOTES_CHARS = 1500
_MAX_SOURCE_REFS = 5
_MAX_EXCERPT_CHARS = 500

_PEP_ID_PATTERN = re.compile(r"PEP-?(\d{3,4})", re.IGNORECASE)
_KEYWORD_TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_\-./]{3,}")

_SYSTEM_PROMPT = """\
You analyse GitHub commit messages and release notes for a Python packaging
tool to decide when a PEP-defined feature first shipped. Be conservative:
mentions of "PEP-XXX" in a commit pin a likely first-seen release; release
notes calling out the feature explicitly are stronger.

Output VALID JSON only. No prose. Schema:

{
  "status": "found" | "not_found" | "ambiguous",
  "confidence": 0.0-1.0,
  "version_first_seen": "X.Y.Z" | null,
  "strongest_artefact_index": int | null,
  "notes": "<= 200 chars"
}

Rules:
- "found" + confidence >= 0.8 only when an artefact explicitly attributes a
  release to the PEP/feature.
- "ambiguous" when artefacts mention the PEP but the version is unclear.
- "not_found" when nothing relevant turned up.
- version_first_seen: the earliest release tag (without leading ``v``) that
  the artefacts attribute the feature to, or null.
- strongest_artefact_index: 0-based index into the combined artefact list
  (commits then releases), or null.
"""


class _Shard(TypedDict, total=False):
    tool: Tool
    feature: Feature


class _LLMVerdict(BaseModel):
    status: Literal["found", "not_found", "ambiguous"]
    confidence: float = Field(ge=0.0, le=1.0)
    version_first_seen: str | None = None
    strongest_artefact_index: int | None = None
    notes: str = ""


class _Artefact(BaseModel):
    kind: Literal["commit", "release"]
    summary: str
    url: str
    excerpt: str = ""


def evidence_changelog(shard: _Shard) -> dict:
    _ = get_model_for(__name__)
    feature = shard.get("feature")
    tool: Tool | None = shard.get("tool")
    # Defensive: if the router lost context (shouldn't happen with the
    # Send-based routing in graph.py, but keeps the stub-era smoke path
    # working), emit a sentinel record so the ladder keeps moving.
    if feature is None or tool is None:
        return _evidence(
            feature_id=(feature.id if feature else "unknown"),
            tool=tool or "pip",
            found=False,
            confidence=0.0,
            notes="changelog skipped: shard missing feature/tool",
        )

    repo = get_repo_for(tool)
    pep_terms = _query_terms(feature)

    artefacts = _gather_artefacts(repo, pep_terms)

    if not artefacts:
        return _evidence(
            feature_id=feature.id,
            tool=tool,
            found=False,
            confidence=0.2,
            notes=f"no commits/releases mentioning {pep_terms} in {repo}",
        )

    verdict = _classify(feature, artefacts)
    if verdict is None:
        return _evidence(
            feature_id=feature.id,
            tool=tool,
            found=False,
            confidence=0.0,
            notes="LLM classification failed; defer to probe",
        )

    found = verdict.status == "found"
    confidence = verdict.confidence if found else min(verdict.confidence, 0.5)
    source_refs = _format_source_refs(artefacts, verdict.strongest_artefact_index)
    excerpt = _excerpt(artefacts, verdict.strongest_artefact_index)

    return _evidence(
        feature_id=feature.id,
        tool=tool,
        found=found,
        confidence=confidence,
        version_first_seen=verdict.version_first_seen,
        source_refs=source_refs,
        raw_excerpt=excerpt,
        notes=verdict.notes or f"changelog: {verdict.status} via {len(artefacts)} artefact(s)",
    )


# ---- Query construction ---------------------------------------------------


def _query_terms(feature: Feature) -> list[str]:
    """PEP id + the strongest identifier-shaped token, deduped.

    GitHub commit search treats space-separated terms as AND. We issue them
    as separate queries (OR-of-AND) and merge results.
    """
    terms: list[str] = []
    pep_match = _PEP_ID_PATTERN.search(feature.pep_id)
    if pep_match:
        # Both forms appear in the wild ("PEP 658" and "PEP-658").
        n = pep_match.group(1)
        terms.extend([f"PEP {n}", f"PEP-{n}"])
    for claim in feature.spec_claims:
        for token in _KEYWORD_TOKEN_PATTERN.findall(claim.claim_text):
            t = token.strip(".-_/")
            if len(t) < 5 or not any(ch in t for ch in "-_./0123456789"):
                continue
            terms.append(t)
            break
        if len(terms) >= 4:
            break
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ---- GitHub aggregation ---------------------------------------------------


def _gather_artefacts(repo: str, query_terms: list[str]) -> list[_Artefact]:
    commits = _gather_commits(repo, query_terms)
    releases = _gather_releases(repo, query_terms)
    return commits + releases


def _gather_commits(repo: str, query_terms: list[str]) -> list[_Artefact]:
    seen_shas: set[str] = set()
    out: list[_Artefact] = []
    for term in query_terms:
        try:
            commits = github.search_commits(repo, term, limit=_MAX_COMMITS)
        except (RuntimeError, LookupError):
            continue
        for c in commits:
            if c.sha in seen_shas:
                continue
            seen_shas.add(c.sha)
            out.append(
                _Artefact(
                    kind="commit",
                    summary=f"{c.sha[:7]} ({c.committed_at.date()}): {c.message.splitlines()[0][:160]}",
                    url=c.url,
                    excerpt=c.message[:_MAX_EXCERPT_CHARS],
                )
            )
        if len(out) >= _MAX_COMMITS:
            break
    return out[:_MAX_COMMITS]


def _gather_releases(repo: str, query_terms: list[str]) -> list[_Artefact]:
    try:
        releases = github.list_releases(repo, limit=_MAX_RELEASES)
    except (RuntimeError, LookupError):
        return []
    if not releases:
        return []
    needles = [t.lower() for t in query_terms]
    matches: list[_Artefact] = []
    fetched_notes = 0
    for r in releases:
        notes = ""
        if fetched_notes < _MAX_RELEASE_NOTES_FETCH:
            try:
                notes = github.get_release_notes(repo, r.tag) or ""
                fetched_notes += 1
            except (RuntimeError, LookupError):
                notes = ""
        haystack = f"{r.tag} {r.name or ''} {notes}".lower()
        if not any(needle in haystack for needle in needles):
            continue
        published = r.published_at.date().isoformat() if r.published_at else "unknown"
        matches.append(
            _Artefact(
                kind="release",
                summary=f"{r.tag} ({published}): {r.name or ''}".strip(),
                url=r.url,
                excerpt=notes[:_MAX_RELEASE_NOTES_CHARS],
            )
        )
    return matches


# ---- LLM classification ---------------------------------------------------


def build_user_prompt(feature: Feature, artefacts: list[_Artefact]) -> str:
    rendered_claims = "\n".join(
        f"- ({c.claim_type}) {c.claim_text}" for c in feature.spec_claims
    )
    rendered_artefacts = "\n".join(
        f"[{i}] ({a.kind}) {a.summary}\n    url: {a.url}\n    excerpt: {a.excerpt[:300]}"
        for i, a in enumerate(artefacts)
    )
    return (
        f"Feature: {feature.title} ({feature.pep_id})\n"
        f"Description: {feature.description}\n\n"
        f"Spec claims:\n{rendered_claims}\n\n"
        f"GitHub artefacts:\n{rendered_artefacts}\n"
    )


def _classify(feature: Feature, artefacts: list[_Artefact]) -> _LLMVerdict | None:
    user = build_user_prompt(feature, artefacts)
    try:
        raw = llm.call("evidence_changelog", system=_SYSTEM_PROMPT, user=user)
        return _LLMVerdict.model_validate_json(llm.strip_json_fences(raw))
    except (ValidationError, ValueError, json.JSONDecodeError, llm.CassetteMissing,
            RuntimeError):
        return None


# ---- Evidence assembly ----------------------------------------------------


def _format_source_refs(
    artefacts: list[_Artefact], strongest_idx: int | None
) -> list[str]:
    ordered = list(artefacts)
    if strongest_idx is not None and 0 <= strongest_idx < len(ordered):
        ordered.insert(0, ordered.pop(strongest_idx))
    refs: list[str] = []
    seen: set[str] = set()
    for a in ordered:
        if a.url in seen:
            continue
        seen.add(a.url)
        refs.append(a.url)
        if len(refs) >= _MAX_SOURCE_REFS:
            break
    return refs


def _excerpt(artefacts: list[_Artefact], strongest_idx: int | None) -> str | None:
    if not artefacts:
        return None
    idx = strongest_idx if (strongest_idx is not None and 0 <= strongest_idx < len(artefacts)) else 0
    return artefacts[idx].excerpt[:_MAX_EXCERPT_CHARS] or None


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
        method="changelog",
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
        "status": "found",
        "confidence": 0.85,
        "version_first_seen": "0.0.0-stub",
        "strongest_artefact_index": 0,
        "notes": "STUB classification",
    }
)
llm.register_stub("evidence_changelog", _STUB_RESPONSE)
