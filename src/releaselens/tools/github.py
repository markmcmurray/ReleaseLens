"""GitHub API tool — commit archaeology (architecture.md §9).

Used by ``evidence_changelog`` for commit-grep, release/tag enumeration, and
release-note retrieval. Wraps PyGithub but never leaks PyGithub objects past
this module — node code only sees the Pydantic models defined below.

Real mode authenticates via ``GITHUB_TOKEN``. Stub mode returns canned
responses registered with ``register_stub``.
"""

from __future__ import annotations

import os
from collections.abc import Hashable
from datetime import date, datetime

from pydantic import BaseModel

from releaselens.tools import _stub_mode

TOOL = "github"


class CommitRef(BaseModel):
    sha: str
    message: str
    committed_at: datetime
    url: str


class ReleaseRef(BaseModel):
    tag: str
    name: str | None
    published_at: datetime | None
    url: str


def search_commits(
    repo: str, query: str, since: date | None = None, *, limit: int = 50
) -> list[CommitRef]:
    """Search ``repo`` (``owner/name``) for commits matching ``query``."""
    if _stub_mode.mode_for(TOOL) == "stub":
        return list(_stub_mode.lookup_stub(TOOL, ("search_commits", repo, query, _date_key(since))))

    from itertools import islice

    gh = _client()
    qualifiers = f"repo:{repo} {query}"
    if since is not None:
        qualifiers += f" committer-date:>={since.isoformat()}"
    return [
        CommitRef(
            sha=c.sha,
            message=c.commit.message,
            committed_at=c.commit.committer.date,
            url=c.html_url,
        )
        for c in islice(gh.search_commits(qualifiers), limit)
    ]


def list_releases(repo: str, *, limit: int = 50) -> list[ReleaseRef]:
    """List up to ``limit`` releases for ``repo``, newest-first."""
    if _stub_mode.mode_for(TOOL) == "stub":
        return list(_stub_mode.lookup_stub(TOOL, ("list_releases", repo)))

    from itertools import islice

    gh = _client()
    repository = gh.get_repo(repo)
    return [
        ReleaseRef(
            tag=r.tag_name,
            name=r.title,
            published_at=r.published_at,
            url=r.html_url,
        )
        for r in islice(repository.get_releases(), limit)
    ]


def get_release_notes(repo: str, tag: str) -> str:
    """Fetch the release-notes body for ``tag`` in ``repo``."""
    if _stub_mode.mode_for(TOOL) == "stub":
        return _stub_mode.lookup_stub(TOOL, ("get_release_notes", repo, tag))

    gh = _client()
    repository = gh.get_repo(repo)
    return repository.get_release(tag).body or ""


def register_stub(call: str, *args: Hashable, value) -> None:
    """Register a canned response for ``(call, *args)``.

    Examples:
        register_stub("search_commits", "pypa/pip", "PEP-691", None, value=[...])
        register_stub("list_releases", "pypa/pip", value=[...])
        register_stub("get_release_notes", "pypa/pip", "23.0", value="...")
    """
    _stub_mode.register_stub(TOOL, (call, *args), value)


def _client():
    from github import Auth, Github

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for real-mode github tool")
    return Github(auth=Auth.Token(token))


def _date_key(d: date | None) -> str | None:
    return d.isoformat() if d else None
