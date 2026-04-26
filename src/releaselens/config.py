"""Configuration loaders (architecture.md §15).

Lazily loads ``config/thresholds.yaml`` for nodes that need numeric thresholds
not naturally carried by their Send shard. Caches via lru_cache so repeated
node invocations don't re-read the YAML.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
_DEFAULT_THRESHOLDS_PATH = _CONFIG_DIR / "thresholds.yaml"


class Thresholds(BaseModel):
    confidence_threshold: float = 0.8
    test_retry_budget: int = 2
    test_acceptance_threshold: float = 0.75


@lru_cache(maxsize=1)
def get_thresholds(path: Path = _DEFAULT_THRESHOLDS_PATH) -> Thresholds:
    if not path.exists():
        return Thresholds()
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return Thresholds.model_validate(data)
