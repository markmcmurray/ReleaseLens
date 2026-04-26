"""ripgrep wrapper — fast structural search (architecture.md §9).

Used by ``evidence_static`` and ``impact_scope``, and by the
``static_signature`` executor inside the differential test runner.

Real mode shells out to ``rg --json`` and parses match events. Stub mode
returns canned hits registered with ``register_stub``.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Hashable
from pathlib import Path

from pydantic import BaseModel

from releaselens.tools import _stub_mode

TOOL = "ripgrep"


class RipgrepHit(BaseModel):
    path: str
    line_no: int
    line_text: str


def search(
    pattern: str,
    root: Path | str,
    *,
    file_globs: list[str] | None = None,
    max_results: int = 200,
) -> list[RipgrepHit]:
    """Search ``root`` for ``pattern``. Returns up to ``max_results`` hits."""
    root_str = str(root)
    if _stub_mode.mode_for(TOOL) == "stub":
        return list(_stub_mode.lookup_stub(TOOL, _key(pattern, root_str, file_globs)))

    cmd = ["rg", "--json", "--no-messages", pattern, root_str]
    for glob in file_globs or []:
        cmd.extend(["--glob", glob])

    hits: list[RipgrepHit] = []
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "match":
                continue
            data = event["data"]
            hits.append(
                RipgrepHit(
                    path=data["path"]["text"],
                    line_no=data["line_number"],
                    line_text=data["lines"]["text"].rstrip("\n"),
                )
            )
            if len(hits) >= max_results:
                proc.terminate()
                break
    finally:
        proc.stdout.close() if proc.stdout else None
        rc = proc.wait()
    if rc not in (0, 1) and len(hits) < max_results:  # 1 = no matches; >1 = real error
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"rg failed (exit {rc}): {stderr.strip()}")
    return hits


def register_stub(
    pattern: str,
    root: Path | str,
    hits: list[RipgrepHit],
    *,
    file_globs: list[str] | None = None,
) -> None:
    """Register canned ``hits`` for a stub-mode ``search`` call."""
    _stub_mode.register_stub(TOOL, _key(pattern, str(root), file_globs), hits)


def _key(pattern: str, root: str, file_globs: list[str] | None) -> Hashable:
    return (pattern, root, tuple(file_globs or ()))
