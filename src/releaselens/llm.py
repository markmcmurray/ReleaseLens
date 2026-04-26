"""LiteLLM call wrapper with cassette-based record/replay (architecture.md §11.6.1).

Tests must be deterministic (AGENTS.md). Real LLM calls are recorded to
``$RELEASELENS_CASSETTES_DIR/<node_name>/<sha256(request)>.json`` (default
``tests/cassettes``) once and replayed thereafter — replay is the default so
unit tests never reach Bedrock.

Modes via ``RELEASELENS_LLM_MODE``:
- ``replay`` (default): cassette must exist; missing cassette raises
- ``record-missing``: replay when cassette exists, otherwise call live and write
- ``record``: always call live and overwrite the cassette
- ``live``: always call live, never read or write cassettes
- ``stub``: return a per-node response registered via :func:`register_stub`
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

import litellm

from releaselens.routing import get_model_for

CassetteMode = Literal["replay", "record-missing", "record", "live", "stub"]

_DEFAULT_CASSETTE_DIR = "tests/cassettes"
_VALID_MODES: tuple[CassetteMode, ...] = (
    "replay",
    "record-missing",
    "record",
    "live",
    "stub",
)
_JSON_FENCE_OPEN = re.compile(r"^```(?:json)?\s*\n")
_JSON_FENCE_CLOSE = re.compile(r"\n```\s*$")


class CassetteMissing(RuntimeError):
    """Raised when replay mode is active but no cassette exists for the request."""


_STUB_RESPONSES: dict[str, str] = {}


def register_stub(node_name: str, response: str) -> None:
    """Register a deterministic stub response for ``RELEASELENS_LLM_MODE=stub``.

    Each node that wants to be runnable end-to-end without cassettes or live
    Bedrock provides one canonical stub at import time.
    """
    _STUB_RESPONSES[node_name] = response


def call(
    node_name: str,
    *,
    system: str,
    user: str,
    metadata: dict | None = None,
) -> str:
    """Call the LLM routed for ``node_name`` and return the raw response text.

    ``metadata`` is forwarded to LiteLLM in live mode, where the Langfuse
    callback consumes ``trace_id``/``generation_name``/``tags`` keys to group
    generations under the correct trace. Ignored in cassette/stub modes.
    """
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
    cassette_path = _cassette_dir() / node_name / f"{key}.json"

    if mode in ("replay", "record-missing") and cassette_path.exists():
        return _read_cassette(cassette_path)

    if mode == "replay":
        raise CassetteMissing(
            f"No cassette at {cassette_path}. Set RELEASELENS_LLM_MODE=record-missing to capture."
        )

    from releaselens.observability.langfuse import current_run_id

    trace_metadata = {
        "trace_id": current_run_id.get(),
        "generation_name": node_name,
        "tags": [f"node:{node_name}"],
        **(metadata or {}),
    }
    response = litellm.completion(
        model=cfg.model,
        messages=messages,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        timeout=cfg.timeout_seconds,
        metadata=trace_metadata,
    )
    text = response.choices[0].message.content or ""
    if mode in ("record", "record-missing"):
        _write_cassette(cassette_path, cfg.model, messages, text)
    return text


def strip_json_fences(text: str) -> str:
    """Strip ```json ... ``` wrappers some models add around JSON output.

    Lifted to llm.py because every JSON-out LLM node needs this; keeping it
    per-node would invite drift on the regex.
    """
    text = text.strip()
    if not text.startswith("```"):
        return text
    text = _JSON_FENCE_OPEN.sub("", text)
    text = _JSON_FENCE_CLOSE.sub("", text)
    return text


def _cassette_dir() -> Path:
    return Path(os.environ.get("RELEASELENS_CASSETTES_DIR", _DEFAULT_CASSETTE_DIR))


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
    """Atomic write: render to a sibling tempfile, then os.replace into place.

    A direct write_text can leave a partial cassette if the process is killed
    mid-write — replay would then read truncated JSON and either crash or
    (worse) silently produce wrong test outputs. Atomic rename eliminates
    the partial-state window.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "messages": messages, "response": response}
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(rendered)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)
