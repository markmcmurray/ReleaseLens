"""Test feature_extract via cassette replay against bundled PEP-658 fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from releaselens.nodes.feature_extract import feature_extract
from releaselens.nodes.pep_ingest import pep_ingest
from releaselens.tools import rag
from releaselens.tools.rag import RagSnippet

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "peps"
_CASSETTES = Path(__file__).parents[1] / "cassettes" / "feature_extract"


def test_feature_extract_returns_real_features_for_pep_658(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    mode = os.environ.get("RELEASELENS_LLM_MODE", "replay")
    have_cassette = _CASSETTES.exists() and any(_CASSETTES.glob("*.json"))
    if mode == "replay" and not have_cassette:
        pytest.skip(
            "No cassette recorded for feature_extract. "
            "Run RELEASELENS_LLM_MODE=record-missing pytest with Bedrock creds "
            "to capture once."
        )
    monkeypatch.setenv("RELEASELENS_PEPS_DIR", str(_FIXTURES))
    rag.register_stub(
        "peps",
        "PEP-503 specification",
        [
            RagSnippet(
                collection="peps",
                doc_id="PEP-503#000",
                text="The Simple Repository API exposes per-project pages with anchor tags.",
                metadata={"pep_id": "PEP-503", "heading": "Specification"},
                score=0.9,
            )
        ],
        k=3,
    )

    ingest_out = pep_ingest({"pep_id": "PEP-658"})
    source = ingest_out["pep_sources"]["PEP-658"]

    out = feature_extract({"pep_id": "PEP-658", "source": source})
    assert "features" in out, f"Expected features key; got {out}"
    features = out["features"]
    assert len(features) >= 2, "PEP-658 should decompose into multiple features"

    for feature in features:
        assert feature.pep_id == "PEP-658"
        assert feature.id.startswith("pep-658.")
        assert feature.title
        assert feature.description
        assert feature.spec_claims, f"Feature {feature.id} has no claims"
        for claim in feature.spec_claims:
            assert claim.feature_id == feature.id
            assert claim.id.startswith(f"{feature.id}.claim-")
            assert claim.claim_type in {
                "behavioural",
                "structural",
                "protocol",
                "metadata",
            }
            assert claim.pep_section_ref.lower().startswith("pep-658#")
