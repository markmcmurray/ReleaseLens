"""Pydantic fixture models for ground-truth labels (architecture.md §11.2).

Hand-labelled fixtures live at data/fixtures/PEP-XXX.yaml. These models validate them
at load time so typos and schema drift fail fast with the offending field path.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class ExpectedEvidence(BaseModel):
    found: bool
    version_first_seen: str | None = None


class SpecClaimFixture(BaseModel):
    id: str
    claim_text: str


class FeatureFixture(BaseModel):
    id: str
    title: str
    spec_claims: list[SpecClaimFixture]
    expected_evidence: dict[Literal["warehouse", "pip", "uv"], ExpectedEvidence]


class PEPFixture(BaseModel):
    pep_id: str
    pep_finalised_on: date
    features: list[FeatureFixture]


def load_fixture(path: Path) -> PEPFixture:
    with path.open() as f:
        data = yaml.safe_load(f)
    return PEPFixture.model_validate(data)
