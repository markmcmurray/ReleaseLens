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


_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
_DEFAULT_CONFIG_PATH = _CONFIG_DIR / "model_routing.yaml"
_DEFAULT_PINS_PATH = _CONFIG_DIR / "model_pins.yaml"


@lru_cache(maxsize=1)
def _load_routing(path: Path = _DEFAULT_CONFIG_PATH) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _load_pins(path: Path = _DEFAULT_PINS_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    return data.get("pins", {})


def _resolve_pin(family_alias: str) -> str:
    """Resolve a family alias to its pinned Bedrock model ID.

    Architecture.md §6 says nodes reference family aliases in routing.yaml
    and exact Bedrock IDs live in model_pins.yaml. Reproducibility for eval
    runs depends on this — a missing pin raises rather than silently using
    a wrong model.
    """
    pins = _load_pins()
    if family_alias not in pins:
        raise KeyError(
            f"No pin for {family_alias!r} in model_pins.yaml. "
            f"Add an entry mapping the alias to an exact Bedrock model ID."
        )
    return pins[family_alias]


def get_model_for(node_name: str, *, stub: bool = True) -> LiteLLMConfig:
    """Return the LiteLLM config for a node.

    Defaults to ``stub=True`` so no real model is ever resolved by accident.
    The LLM call wrapper passes ``stub=False`` when it intends to hit Bedrock.
    """
    routing = _load_routing()
    defaults = routing.get("defaults", {})
    node_cfg = routing.get("nodes", {}).get(node_name, {})
    family_alias = node_cfg.get("model", "stub")

    if stub or family_alias == "stub" or family_alias == "none":
        model = "stub"
    else:
        model = _resolve_pin(family_alias)

    return LiteLLMConfig(
        model=model,
        temperature=defaults.get("temperature", 0.0),
        max_tokens=node_cfg.get("max_tokens", defaults.get("max_tokens", 4000)),
        timeout_seconds=defaults.get("timeout_seconds", 60),
    )
