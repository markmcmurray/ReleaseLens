"""Configuration loaders (architecture.md §15).

Lazily loads ``config/thresholds.yaml`` for nodes that need numeric thresholds
not naturally carried by their Send shard. Caches via lru_cache so repeated
node invocations don't re-read the YAML.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from releaselens.schemas import Tool

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _REPO_ROOT / "config"
_DEFAULT_THRESHOLDS_PATH = _CONFIG_DIR / "thresholds.yaml"
_DEFAULT_SOURCES_DIR = _REPO_ROOT / "data" / "sources"


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


def get_source_dir(tool: Tool) -> Path:
    """Local clone path for ``tool``'s source tree.

    Resolution order: ``RELEASELENS_SOURCES_DIR`` env var (treated as the
    parent dir holding ``pip/``, ``uv/``, ``warehouse/``), else the default
    ``<repo>/data/sources/<tool>``. Existence is not enforced here — the
    caller decides how to react to a missing tree.
    """
    base = Path(os.environ.get("RELEASELENS_SOURCES_DIR", _DEFAULT_SOURCES_DIR))
    return base / tool
