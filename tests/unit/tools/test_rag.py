"""Stub-mode tests for the rag wrapper."""

from __future__ import annotations

import pytest

from releaselens.tools import StubNotRegistered, rag
from releaselens.tools.rag import RagSnippet, RagStore, _iter_sections


def test_stub_query_returns_registered_snippets():
    snippets = [
        RagSnippet(
            collection="peps",
            doc_id="PEP-691#001",
            text="JSON Simple API",
            metadata={"pep_id": "PEP-691"},
            score=0.9,
        )
    ]
    rag.register_stub("peps", "json simple api", snippets)

    store = RagStore()
    assert store.query("peps", "json simple api", k=5) == snippets


def test_stub_unregistered_raises():
    store = RagStore()
    with pytest.raises(StubNotRegistered):
        store.query("peps", "nope")


def test_stub_ingest_is_noop():
    store = RagStore()
    store.ingest_peps([])
    store.ingest_connector_docs([])


def test_iter_sections_uses_shared_splitter_and_drops_preamble():
    text = (
        "PEP: 999\nTitle: Example\n\n"
        "Abstract\n========\n\nAbstract body.\n\n"
        "Specification\n=============\n\nSpec body.\n"
    )
    sections = _iter_sections(text)
    assert [h for h, _ in sections] == ["Abstract", "Specification"]
    assert sections[1][1].startswith("Spec body")
