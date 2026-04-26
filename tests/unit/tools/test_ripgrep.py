"""Stub-mode tests for the ripgrep wrapper."""

from __future__ import annotations

import pytest

from releaselens.tools import StubNotRegistered, ripgrep
from releaselens.tools.ripgrep import RipgrepHit


def test_stub_returns_registered_hits():
    hits = [RipgrepHit(path="src/foo.py", line_no=42, line_text="def bar():")]
    ripgrep.register_stub("def bar", "/repo", hits)

    result = ripgrep.search("def bar", "/repo")

    assert result == hits


def test_stub_distinguishes_globs():
    base_hit = [RipgrepHit(path="a.py", line_no=1, line_text="x")]
    py_hit = [RipgrepHit(path="b.py", line_no=2, line_text="y")]
    ripgrep.register_stub("x", "/r", base_hit)
    ripgrep.register_stub("x", "/r", py_hit, file_globs=["*.py"])

    assert ripgrep.search("x", "/r") == base_hit
    assert ripgrep.search("x", "/r", file_globs=["*.py"]) == py_hit


def test_stub_unregistered_raises():
    with pytest.raises(StubNotRegistered):
        ripgrep.search("nope", "/nowhere")
