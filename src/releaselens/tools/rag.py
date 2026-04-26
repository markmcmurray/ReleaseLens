"""ChromaDB-backed RAG store (architecture.md §9).

Two collections: ``peps`` (used by ``feature_extract``, ``verify``) and
``connector_docs`` (used by ``impact_scope``). Embeddings come from Bedrock
Titan via LiteLLM; Chroma is used purely as the vector index — embeddings
are computed in this module so we never depend on Chroma's embedding-function
machinery.
"""

from __future__ import annotations

import os
from collections.abc import Hashable, Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from releaselens.peps.rst import split_sections
from releaselens.tools import _stub_mode

TOOL = "rag"

Collection = Literal["peps", "connector_docs"]
_DEFAULT_PERSIST_DIR = "data/chroma"
_DEFAULT_EMBED_MODEL = "bedrock/amazon.titan-embed-text-v2:0"
# Titan v2 accepts small input batches; chunk to stay well under per-request limits.
_EMBED_BATCH_SIZE = 16


class RagSnippet(BaseModel):
    collection: Collection
    doc_id: str
    text: str
    metadata: dict
    score: float


class RagStore:
    """Thin wrapper over a ChromaDB persistent client."""

    def __init__(
        self,
        persist_dir: Path | str = _DEFAULT_PERSIST_DIR,
        embed_model: str = _DEFAULT_EMBED_MODEL,
    ) -> None:
        self._persist_dir = Path(persist_dir)
        self._embed_model = embed_model
        self._client = None

    def query(self, collection: Collection, q: str, k: int = 5) -> list[RagSnippet]:
        if _stub_mode.mode_for(TOOL) == "stub":
            return list(_stub_mode.lookup_stub(TOOL, ("query", collection, q, k)))

        coll = self._collection(collection)
        embedding = self._embed([q])[0]
        result = coll.query(query_embeddings=[embedding], n_results=k)
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        return [
            RagSnippet(
                collection=collection,
                doc_id=doc_id,
                text=text,
                metadata=meta or {},
                score=1.0 - float(dist),
            )
            for doc_id, text, meta, dist in zip(ids, docs, metas, dists, strict=False)
        ]

    def ingest_peps(self, paths: list[Path]) -> None:
        """Chunk each PEP RST by top-level section and upsert."""
        self._ingest("peps", _pep_items(paths))

    def ingest_connector_docs(self, paths: list[Path]) -> None:
        """Chunk connector/target docs by top-level section and upsert."""
        self._ingest("connector_docs", _connector_doc_items(paths))

    def _ingest(self, collection: Collection, items: Iterable[tuple[str, str, dict]]) -> None:
        if _stub_mode.mode_for(TOOL) == "stub":
            return

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []
        for doc_id, text, meta in items:
            ids.append(doc_id)
            docs.append(text)
            metas.append(meta)
        if not ids:
            return
        embeddings = self._embed(docs)
        self._collection(collection).upsert(
            ids=ids, documents=docs, metadatas=metas, embeddings=embeddings
        )

    def _collection(self, name: Collection):
        if self._client is None:
            import chromadb

            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        return self._client.get_or_create_collection(name)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        import litellm

        out: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[start : start + _EMBED_BATCH_SIZE]
            resp = litellm.embedding(
                model=self._embed_model,
                input=batch,
                aws_region_name=os.environ.get("AWS_REGION", "us-east-1"),
            )
            out.extend(item["embedding"] for item in resp.data)
        return out


def register_stub(collection: Collection, q: str, snippets: list[RagSnippet], k: int = 5) -> None:
    """Register canned ``snippets`` for a stub-mode ``query`` call."""
    _stub_mode.register_stub(TOOL, _key(collection, q, k), snippets)


def _key(collection: Collection, q: str, k: int) -> Hashable:
    return ("query", collection, q, k)


def _pep_items(paths: list[Path]) -> Iterable[tuple[str, str, dict]]:
    for path in paths:
        pep_id = path.stem
        for idx, (heading, body) in enumerate(_iter_sections(path.read_text())):
            yield f"{pep_id}#{idx:03d}", body, {"pep_id": pep_id, "heading": heading}


def _connector_doc_items(paths: list[Path]) -> Iterable[tuple[str, str, dict]]:
    for path in paths:
        for idx, (heading, body) in enumerate(_iter_sections(path.read_text())):
            yield (
                f"{path}#{idx:03d}",
                body,
                {"source": str(path), "heading": heading},
            )


def _iter_sections(text: str) -> list[tuple[str, str]]:
    """Top-level RST sections via the shared splitter; preamble dropped."""
    return [(h, body) for h, body in split_sections(text).items() if h != "preamble" and body]
