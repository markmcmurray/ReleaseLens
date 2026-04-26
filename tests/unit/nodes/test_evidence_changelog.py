"""Tests for evidence_changelog.

Mirrors test_evidence_static's three-axis coverage:

- Stub mode: github stubs + LLM stub, asserts the evidence shape and that
  source_refs are real GitHub URLs (not ``stub://changelog``).
- Empty artefacts in real-LLM mode: low-confidence not-found short-circuit
  so the ladder progresses to evidence_probe.
- Cassette replay: hand-authored cassette plus github stubs exercises the
  classification path deterministically.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from releaselens.config import get_repo_for
from releaselens.nodes.evidence_changelog import (
    _SYSTEM_PROMPT,
    _Artefact,
    build_user_prompt,
    evidence_changelog,
)
from releaselens.schemas import Feature, SpecClaim
from releaselens.tools import github
from releaselens.tools.github import CommitRef, ReleaseRef


def _feature() -> Feature:
    feature_id = "pep-658.dist-info-metadata"
    return Feature(
        id=feature_id,
        pep_id="PEP-658",
        title="Static dist-info metadata",
        description="Index serves a separate dist-info file for each wheel.",
        pep_status="Final",
        pep_finalised_on=None,
        introduced_version_claim=None,
        spec_claims=[
            SpecClaim(
                id=f"{feature_id}.claim-01",
                feature_id=feature_id,
                claim_text=(
                    "Indexes that serve PEP 503 simple repositories MAY include a "
                    "data-dist-info-metadata attribute on each anchor link."
                ),
                claim_type="protocol",
                testable=True,
                pep_section_ref="PEP-658#specification",
            ),
        ],
    )


def _commit() -> CommitRef:
    return CommitRef(
        sha="abc1234deadbeef",
        message="Implement PEP 658 dist-info-metadata fetching (#11111)",
        committed_at=datetime(2022, 9, 1, tzinfo=UTC),
        url="https://github.com/pypa/pip/commit/abc1234",
    )


def _release() -> ReleaseRef:
    return ReleaseRef(
        tag="22.3",
        name="pip 22.3",
        published_at=datetime(2022, 10, 15, tzinfo=UTC),
        url="https://github.com/pypa/pip/releases/tag/22.3",
    )


def _register_github_stubs(repo: str) -> None:
    """Register canned github responses keyed for both PEP query forms."""
    github.register_stub("search_commits", repo, "PEP 658", None, value=[_commit()])
    github.register_stub("search_commits", repo, "PEP-658", None, value=[_commit()])
    github.register_stub(
        "search_commits", repo, "data-dist-info-metadata", None, value=[]
    )
    github.register_stub("list_releases", repo, value=[_release()])
    github.register_stub(
        "get_release_notes",
        repo,
        "22.3",
        value="Add support for PEP 658 metadata files served by simple indexes.",
    )


def test_evidence_changelog_stub_mode_returns_real_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "stub")
    repo = get_repo_for("pip")
    _register_github_stubs(repo)

    out = evidence_changelog({"tool": "pip", "feature": _feature()})

    [ev] = out["evidence"]
    assert ev.feature_id == _feature().id
    assert ev.tool == "pip"
    assert ev.method == "changelog"
    assert ev.found is True
    assert ev.confidence >= 0.8
    assert ev.source_refs, "expected GitHub URLs"
    for ref in ev.source_refs:
        assert ref.startswith("https://github.com/"), f"non-URL ref: {ref!r}"
        assert "stub://" not in ref


def test_evidence_changelog_no_artefacts_falls_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "replay")
    monkeypatch.setenv("RELEASELENS_CASSETTES_DIR", str(tmp_path / "cassettes"))
    repo = get_repo_for("pip")
    github.register_stub("search_commits", repo, "PEP 658", None, value=[])
    github.register_stub("search_commits", repo, "PEP-658", None, value=[])
    github.register_stub(
        "search_commits", repo, "data-dist-info-metadata", None, value=[]
    )
    github.register_stub("list_releases", repo, value=[])

    out = evidence_changelog({"tool": "pip", "feature": _feature()})
    [ev] = out["evidence"]
    assert ev.method == "changelog"
    assert ev.found is False
    assert ev.confidence < 0.5
    assert ev.source_refs == []


def test_evidence_changelog_llm_classification_via_cassette(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cassette_dir = tmp_path / "cassettes"
    monkeypatch.setenv("RELEASELENS_CASSETTES_DIR", str(cassette_dir))
    monkeypatch.setenv("RELEASELENS_LLM_MODE", "replay")

    from releaselens import llm
    from releaselens.routing import get_model_for

    cfg = get_model_for("evidence_changelog", stub=False)
    repo = get_repo_for("pip")
    _register_github_stubs(repo)

    feature = _feature()
    commit_artefact = _Artefact(
        kind="commit",
        summary=f"{_commit().sha[:7]} ({_commit().committed_at.date()}): {_commit().message.splitlines()[0][:160]}",
        url=_commit().url,
        excerpt=_commit().message[:500],
    )
    release_artefact = _Artefact(
        kind="release",
        summary=f"{_release().tag} ({_release().published_at.date()}): {_release().name}".strip(),
        url=_release().url,
        excerpt="Add support for PEP 658 metadata files served by simple indexes."[:1500],
    )
    artefacts = [commit_artefact, release_artefact]
    user = build_user_prompt(feature, artefacts)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    key = llm._cassette_key(cfg.model, messages, cfg.temperature, cfg.max_tokens)
    cassette_path = cassette_dir / "evidence_changelog" / f"{key}.json"
    cassette_path.parent.mkdir(parents=True, exist_ok=True)
    response_text = json.dumps(
        {
            "status": "found",
            "confidence": 0.91,
            "version_first_seen": "22.3",
            "strongest_artefact_index": 1,
            "notes": "release 22.3 explicitly attributes PEP 658",
        }
    )
    cassette_path.write_text(
        json.dumps({"model": cfg.model, "messages": messages, "response": response_text})
    )

    out = evidence_changelog({"tool": "pip", "feature": feature})
    [ev] = out["evidence"]
    assert ev.found is True
    assert ev.confidence == pytest.approx(0.91)
    assert ev.version_first_seen == "22.3"
    assert _release().url in ev.source_refs
    assert ev.raw_excerpt and "PEP 658" in ev.raw_excerpt
