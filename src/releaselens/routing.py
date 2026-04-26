"""LiteLLM gateway loader (architecture.md §6).

Nodes never name a model directly — they call get_model_for(node_name) which reads
config/model_routing.yaml. In the scaffold this returns a stub config; the seam is in
place so real Bedrock IDs can be wired by editing YAML, not code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel


class LiteLLMConfig(BaseModel):
    model: str
    temperature: float = 0.0
    max_tokens: int = 4000
    timeout_seconds: int = 60


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "model_routing.yaml"


@lru_cache(maxsize=1)
def _load_routing(path: Path = _DEFAULT_CONFIG_PATH) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def get_model_for(node_name: str, *, stub: bool = True) -> LiteLLMConfig:
    """Return the LiteLLM config for a node.

    In the scaffold, defaults to stub=True so no real model is ever resolved.
    Set stub=False once nodes are ready to call Bedrock.
    """
    routing = _load_routing()
    defaults = routing.get("defaults", {})
    node_cfg = routing.get("nodes", {}).get(node_name, {})

    if stub:
        model = "stub"
    else:
        model = node_cfg.get("model", "stub")

    return LiteLLMConfig(
        model=model,
        temperature=defaults.get("temperature", 0.0),
        max_tokens=node_cfg.get("max_tokens", defaults.get("max_tokens", 4000)),
        timeout_seconds=defaults.get("timeout_seconds", 60),
    )
