"""Differential test runner (architecture.md §9, ADR-0005).

Executes ``DifferentialTest``s produced by the test-author/critic loop. Three
executors keyed on ``test_kind``:

- ``static_signature``   → ripgrep + ``importlib``/``inspect`` resolution
- ``behavioural_probe``  → ``uv venv`` sandbox runs the invocation
- ``metadata_assertion`` → HTTP GET against the registry, JSON-path assertion

**No LLM in this path** (ADR-0005). Outputs are hard pass/fail/error signals;
nodes downstream only interpret those signals when assigning confidence.

The legacy ``RELEASELENS_PROBE_MODE`` env var is honoured as a backward-compat
alias for ``RELEASELENS_DIFFERENTIAL_RUNNER_MODE`` (architecture.md §9).
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from releaselens.observability.langfuse import tool_span
from releaselens.schemas import DifferentialTest
from releaselens.tools import _stub_mode, ripgrep, uv_sandbox

TOOL = "differential_runner"
_LEGACY_MODE_VAR = "RELEASELENS_PROBE_MODE"


class DifferentialResult(BaseModel):
    test_id: str
    outcome: Literal["pass", "fail", "error"]
    detail: str
    raw_output: str | None = None


def run(test: DifferentialTest, *, search_root: Path | str | None = None) -> DifferentialResult:
    """Execute ``test`` and return a structured pass/fail/error result."""
    if _resolve_mode() == "stub":
        return _stub_mode.lookup_stub(TOOL, test.id)

    executor = _EXECUTORS.get(test.test_kind)
    if executor is None:
        return DifferentialResult(
            test_id=test.id, outcome="error", detail=f"unknown test_kind {test.test_kind!r}"
        )
    with tool_span(
        "tool.differential_runner",
        executor=test.test_kind,
        test_id=test.id,
        claim_id=test.claim_id,
    ):
        return executor(test, search_root)


def register_stub(test_id: str, result: DifferentialResult) -> None:
    """Register a canned result for ``test_id``."""
    _stub_mode.register_stub(TOOL, test_id, result)


def _resolve_mode() -> _stub_mode.Mode:
    """Resolve mode honouring the legacy ``RELEASELENS_PROBE_MODE`` alias.

    Reads both env vars without writing to ``os.environ`` — keeping ``run()``
    side-effect-free is required for predictable test isolation.
    """
    canonical = f"RELEASELENS_{TOOL.upper()}_MODE"
    if canonical not in os.environ and (legacy := os.environ.get(_LEGACY_MODE_VAR)):
        if legacy.lower() not in ("real", "stub"):
            raise ValueError(f"{_LEGACY_MODE_VAR}={legacy!r} not in ('real', 'stub')")
        return legacy.lower()  # type: ignore[return-value]
    return _stub_mode.mode_for(TOOL)


def _run_static_signature(
    test: DifferentialTest, search_root: Path | str | None
) -> DifferentialResult:
    """Resolve ``module:attr`` via importlib/inspect; fall back to ripgrep when no module."""
    target = test.invocation.strip()
    module_name, _, attr = target.partition(":")

    if not module_name:
        return _ripgrep_fallback(test, target, search_root)

    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        return DifferentialResult(
            test_id=test.id, outcome="fail", detail=f"module not importable: {e}"
        )

    if not attr:
        return DifferentialResult(
            test_id=test.id, outcome="pass", detail=f"{module_name} importable"
        )

    obj = getattr(mod, attr, None)
    if obj is None:
        return DifferentialResult(
            test_id=test.id, outcome="fail", detail=f"{module_name}:{attr} not found"
        )
    sig = str(inspect.signature(obj)) if callable(obj) else repr(obj)
    return DifferentialResult(
        test_id=test.id,
        outcome="pass",
        detail=f"{module_name}:{attr} resolved",
        raw_output=sig,
    )


def _ripgrep_fallback(
    test: DifferentialTest, target: str, search_root: Path | str | None
) -> DifferentialResult:
    if search_root is None:
        return DifferentialResult(
            test_id=test.id, outcome="error", detail="no search_root for fallback ripgrep"
        )
    hits = ripgrep.search(target, search_root, max_results=10)
    if not hits:
        return DifferentialResult(test_id=test.id, outcome="fail", detail="no hits")
    return DifferentialResult(
        test_id=test.id,
        outcome="pass",
        detail=f"{len(hits)} hits via ripgrep",
        raw_output=hits[0].line_text,
    )


def _run_behavioural_probe(
    test: DifferentialTest, _search_root: Path | str | None
) -> DifferentialResult:
    """``setup`` lists pip-installable packages (one per line); ``invocation``
    is the shell-style command to run inside the sandbox."""
    packages = [line.strip() for line in test.setup.splitlines() if line.strip()]
    invalid = [p for p in packages if not _is_pep508_requirement(p)]
    if invalid:
        return DifferentialResult(
            test_id=test.id,
            outcome="error",
            detail=(
                f"setup contains {len(invalid)} non-pip-installable line(s); "
                f"first: {invalid[0]!r}"
            ),
        )
    cmd = test.invocation.split()
    if not cmd:
        return DifferentialResult(
            test_id=test.id, outcome="error", detail="invocation is empty"
        )
    with uv_sandbox.sandbox(packages) as sbx:
        result = sbx.run(cmd)
    matches = test.expected.strip() in result.stdout
    outcome: Literal["pass", "fail"] = "pass" if matches and result.exit_code == 0 else "fail"
    return DifferentialResult(
        test_id=test.id,
        outcome=outcome,
        detail=f"exit={result.exit_code} expected_in_stdout={matches}",
        raw_output=result.stdout,
    )


def _run_metadata_assertion(
    test: DifferentialTest, _search_root: Path | str | None
) -> DifferentialResult:
    """``invocation`` is ``GET <url> :: <json_path>``.

    e.g. ``GET https://… :: $.meta.api_version``. Asserts the JSON-path value
    equals ``expected`` after JSON parsing.
    """
    import httpx

    spec, _, json_path = test.invocation.partition("::")
    method, _, url = spec.strip().partition(" ")
    if method.upper() != "GET" or not url:
        return DifferentialResult(
            test_id=test.id, outcome="error", detail=f"unsupported invocation: {test.invocation!r}"
        )
    try:
        resp = httpx.get(url.strip(), timeout=10)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        return DifferentialResult(test_id=test.id, outcome="error", detail=str(e))

    actual = _resolve_json_path(payload, json_path.strip())
    expected_value = _coerce_expected(test.expected)
    matches = actual == expected_value
    return DifferentialResult(
        test_id=test.id,
        outcome="pass" if matches else "fail",
        detail=f"actual={actual!r} expected={expected_value!r}",
        raw_output=json.dumps(payload)[:500],
    )


_EXECUTORS = {
    "static_signature": _run_static_signature,
    "behavioural_probe": _run_behavioural_probe,
    "metadata_assertion": _run_metadata_assertion,
}


def _resolve_json_path(payload, path: str):
    """Tiny ``$.a.b[0]`` resolver — no external jsonpath dep."""
    import re

    if not path or path == "$":
        return payload
    if path.startswith("$."):
        path = path[2:]
    cur = payload
    for token in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if token.startswith("["):
            cur = cur[int(token[1:-1])]
        else:
            cur = cur[token]
    return cur


def _coerce_expected(raw: str):
    try:
        return json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return raw


def _is_pep508_requirement(spec: str) -> bool:
    """True if ``spec`` parses as a PEP 508 requirement (``foo==1.2``, etc.).

    Used to fail fast when a behavioural_probe's setup field carries prose
    instead of pip-installable specs — uv would emit a parse error several
    layers deep otherwise.
    """
    try:
        from packaging.requirements import InvalidRequirement, Requirement
    except ImportError:
        # packaging is a transitive dep of pip/uv; fall back to a permissive
        # check if it's somehow not on the path.
        return " " not in spec
    try:
        Requirement(spec)
        return True
    except InvalidRequirement:
        return False
