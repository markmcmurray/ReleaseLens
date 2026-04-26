"""pep_ingest — fetch and parse PEP RST. Scaffold stub returns synthetic PEPSource."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from releaselens.schemas import PEPSource


class _Shard(TypedDict):
    pep_id: str


def pep_ingest(shard: _Shard) -> dict:
    pep_id = shard["pep_id"]
    src = PEPSource(
        pep_id=pep_id,
        rst_url=f"https://peps.python.org/{pep_id.lower()}/",
        fetched_at=datetime.now(UTC),
        body="STUB body",
        parsed_sections={"abstract": "STUB"},
    )
    return {"pep_sources": {pep_id: src}}
