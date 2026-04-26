"""pep_ingest — read a PEP RST file from disk and parse it into a PEPSource.

Architecture.md §6 routes this node to Haiku because the work is "structural
parsing of RST. No reasoning load." The current implementation does the parse
in pure Python (regex section split) — no LLM call. The routing seam is held
open in case a later block wants to add LLM-assisted noise removal on PEPs
with unusual structure.

The peps directory is ``data/peps`` by default and overridable via
``RELEASELENS_PEPS_DIR`` so tests can point at ``tests/fixtures/peps``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from releaselens.peps.rst import split_sections
from releaselens.schemas import ErrorRecord, PEPSource

_DEFAULT_PEPS_DIR = "data/peps"


class _Shard(TypedDict):
    pep_id: str


def pep_ingest(shard: _Shard) -> dict:
    pep_id = shard["pep_id"]
    rst_path = _peps_dir() / f"{pep_id}.rst"

    if not rst_path.exists():
        err = ErrorRecord(
            node="pep_ingest",
            severity="error",
            message=f"PEP source missing on disk: {rst_path}",
            timestamp=datetime.now(UTC),
        )
        return {"errors": [err]}

    body = rst_path.read_text(encoding="utf-8")
    src = PEPSource(
        pep_id=pep_id,
        rst_url=f"https://peps.python.org/{pep_id.lower()}/",
        fetched_at=datetime.now(UTC),
        body=body,
        parsed_sections=split_sections(body),
    )
    return {"pep_sources": {pep_id: src}}


def _peps_dir() -> Path:
    return Path(os.environ.get("RELEASELENS_PEPS_DIR", _DEFAULT_PEPS_DIR))
