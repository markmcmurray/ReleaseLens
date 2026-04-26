"""Tests for pep_ingest reading bundled RST fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from releaselens.nodes.pep_ingest import pep_ingest

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "peps"


def test_reads_bundled_pep_658(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELEASELENS_PEPS_DIR", str(_FIXTURES))
    out = pep_ingest({"pep_id": "PEP-658"})
    assert "pep_sources" in out
    src = out["pep_sources"]["PEP-658"]
    assert src.pep_id == "PEP-658"
    assert "Distribution Metadata" in src.body
    assert "Specification" in src.parsed_sections


def test_missing_pep_records_error_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RELEASELENS_PEPS_DIR", str(tmp_path))
    out = pep_ingest({"pep_id": "PEP-999"})
    assert "pep_sources" not in out
    assert len(out["errors"]) == 1
    err = out["errors"][0]
    assert err.severity == "error"
    assert err.node == "pep_ingest"
    assert "PEP-999" in err.message
