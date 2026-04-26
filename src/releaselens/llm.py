"""LiteLLM call wrapper with cassette-based record/replay (architecture.md §6, §11.6).

Tests must be deterministic (AGENTS.md). Real LLM calls are recorded to
``tests/cassettes/<node_name>/<sha256(request)>.json`` once and replayed
thereafter — replay is the default so unit tests never reach Bedrock.

Modes via ``RELEASELENS_LLM_MODE``:
- ``replay`` (default): cassette must exist; missing cassette raises
- ``record-missing``: replay when cassette exists, otherwise call live and write
- ``record``: always call live and overwrite the cassette
- ``live``: always call live, never read or write cassettes
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

import litellm

from releaselens.routing import get_model_for

CassetteMode = Literal["replay", "record-missing", "record", "live", "stub"]

_CASSETTE_DIR = Path("tests/cassettes")
_VALID_MODES: tuple[CassetteMode, ...] = (
    "replay",
    "record-missing",
    "record",
    "live",
    "stub",
)


class CassetteMissing(RuntimeError):
    """Raised when replay mode is active but no cassette exists for the request."""


_STUB_RESPONSES: dict[str, str] = {}


def register_stub(node_name: str, response: str) -> None:
    """Register a deterministic stub response for ``RELEASELENS_LLM_MODE=stub``.

    Each node that wants to be runnable end-to-end without cassettes or live
    Bedrock provides one canonical stub at import time.
    """
    _STUB_RESPONSES[node_name] = response


def call(node_name: str, *, system: str, user: str) -> str:
    """Call the LLM routed for ``node_name`` and return the raw response text."""
    mode = _resolve_mode()

    if mode == "stub":
        if node_name not in _STUB_RESPONSES:
            raise RuntimeError(
                f"No stub registered for node {node_name!r}. "
                f"Call llm.register_stub({node_name!r}, ...) at module load."
            )
        return _STUB_RESPONSES[node_name]

    cfg = get_model_for(node_name, stub=False)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    key = _cassette_key(cfg.model, messages, cfg.temperature, cfg.max_tokens)
    cassette_path = _CASSETTE_DIR / node_name / f"{key}.json"

    if mode in ("replay", "record-missing") and cassette_path.exists():
        return _read_cassette(cassette_path)

    if mode == "replay":
        raise CassetteMissing(
            f"No cassette at {cassette_path}. Set RELEASELENS_LLM_MODE=record-missing to capture."
        )

    response = litellm.completion(
        model=cfg.model,
        messages=messages,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        timeout=cfg.timeout_seconds,
    )
    text = response.choices[0].message.content or ""
    if mode in ("record", "record-missing"):
        _write_cassette(cassette_path, cfg.model, messages, text)
    return text


def _resolve_mode() -> CassetteMode:
    mode = os.environ.get("RELEASELENS_LLM_MODE", "replay")
    if mode not in _VALID_MODES:
        raise ValueError(f"RELEASELENS_LLM_MODE={mode!r} is not one of {_VALID_MODES}")
    return mode  # type: ignore[return-value]


def _cassette_key(model: str, messages: list[dict], temperature: float, max_tokens: int) -> str:
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _read_cassette(path: Path) -> str:
    return json.loads(path.read_text())["response"]


def _write_cassette(path: Path, model: str, messages: list[dict], response: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "messages": messages,
        "response": response,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
