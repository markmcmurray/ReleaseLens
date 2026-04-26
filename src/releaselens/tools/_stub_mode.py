"""Stub-mode parity helper for non-LLM tools (architecture.md §9).

Every wrapper module under ``src/releaselens/tools/`` exposes both a real and
a stub mode. Mode is selected by ``RELEASELENS_<TOOL>_MODE`` (default ``real``);
tests force ``stub`` via the autouse fixture in ``tests/conftest.py``.

Stub data is registered per-tool with a hashable key. Unregistered keys raise
``StubNotRegistered`` rather than returning empty results — silent zero-result
replays mask bugs in tests.
"""

from __future__ import annotations

import os
from collections.abc import Hashable
from typing import Any, Literal

Mode = Literal["real", "stub"]

_VALID_MODES: tuple[Mode, ...] = ("real", "stub")
_STUBS: dict[str, dict[Hashable, Any]] = {}


class StubNotRegistered(LookupError):
    """Raised by stub-mode tools when no canned response exists for a key."""


def mode_for(tool_name: str) -> Mode:
    """Return the active mode for ``tool_name``.

    Reads ``RELEASELENS_<TOOL>_MODE`` (case-insensitive value), defaults ``real``.
    Raises ``ValueError`` on an unrecognised value.
    """
    env = f"RELEASELENS_{tool_name.upper()}_MODE"
    raw = os.environ.get(env, "real").lower()
    if raw not in _VALID_MODES:
        raise ValueError(f"{env}={raw!r} not in {_VALID_MODES}")
    return raw  # type: ignore[return-value]


def register_stub(tool_name: str, key: Hashable, value: Any) -> None:
    """Register a canned ``value`` for ``tool_name`` under ``key``."""
    _STUBS.setdefault(tool_name, {})[key] = value


def lookup_stub(tool_name: str, key: Hashable) -> Any:
    """Fetch a previously registered stub value or raise ``StubNotRegistered``."""
    bucket = _STUBS.get(tool_name)
    if bucket is None or key not in bucket:
        raise StubNotRegistered(f"No stub registered for tool={tool_name!r} key={key!r}")
    return bucket[key]


def reset_stubs(tool_name: str | None = None) -> None:
    """Drop registered stubs. ``None`` clears every tool."""
    if tool_name is None:
        _STUBS.clear()
    else:
        _STUBS.pop(tool_name, None)
