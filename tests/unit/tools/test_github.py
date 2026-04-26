"""Stub-mode tests for the github wrapper."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from releaselens.tools import StubNotRegistered, github
from releaselens.tools.github import CommitRef, ReleaseRef


def test_search_commits_stub():
    commits = [
        CommitRef(
            sha="abc",
            message="implement PEP-691",
            committed_at=datetime(2022, 5, 4, tzinfo=UTC),
            url="https://github.com/pypa/pip/commit/abc",
        )
    ]
    github.register_stub("search_commits", "pypa/pip", "PEP-691", None, value=commits)

    assert github.search_commits("pypa/pip", "PEP-691") == commits


def test_search_commits_with_since_is_distinct_key():
    github.register_stub("search_commits", "pypa/pip", "PEP-691", "2022-01-01", value=[])
    with pytest.raises(StubNotRegistered):
        github.search_commits("pypa/pip", "PEP-691")  # since=None has no stub
    assert github.search_commits("pypa/pip", "PEP-691", since=date(2022, 1, 1)) == []


def test_list_releases_stub():
    releases = [ReleaseRef(tag="23.0", name="23.0", published_at=None, url="u")]
    github.register_stub("list_releases", "pypa/pip", value=releases)

    assert github.list_releases("pypa/pip") == releases


def test_get_release_notes_stub():
    github.register_stub("get_release_notes", "pypa/pip", "23.0", value="notes body")
    assert github.get_release_notes("pypa/pip", "23.0") == "notes body"
