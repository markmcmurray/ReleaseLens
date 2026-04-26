"""``uv venv`` lifecycle wrapper (architecture.md §9).

Used by the ``behavioural_probe`` executor inside the differential test
runner; reusable by any future probe node that needs an isolated, pinned
Python environment.

Real mode creates a temporary ``uv venv``, ``uv pip install``s the requested
packages, runs commands inside it, and tears down on context exit. Stub mode
returns canned ``SandboxResult``s registered by tests — no venv created.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel

from releaselens.tools import _stub_mode

TOOL = "uv_sandbox"


class SandboxResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


class Sandbox:
    """Handle for a live or stubbed venv."""

    def __init__(self, packages: tuple[str, ...], venv_path: Path | None) -> None:
        self._packages = packages
        self._venv_path = venv_path

    def run(self, cmd: list[str], *, timeout: int = 30) -> SandboxResult:
        if _stub_mode.mode_for(TOOL) == "stub":
            return _stub_mode.lookup_stub(TOOL, _key(self._packages, cmd))

        if self._venv_path is None:
            raise RuntimeError("Sandbox.run called on a stub-mode handle outside stub mode")
        bin_dir = self._venv_path / "bin"
        first = bin_dir / cmd[0]
        resolved = [str(first)] + cmd[1:] if first.exists() else cmd

        proc = subprocess.run(
            resolved,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env=_env_for(self._venv_path),
        )
        return SandboxResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


@contextmanager
def sandbox(packages: list[str], python: str = "3.12") -> Iterator[Sandbox]:
    """Create an isolated venv with ``packages`` installed; tear down on exit."""
    pkg_tuple = tuple(packages)
    if _stub_mode.mode_for(TOOL) == "stub":
        yield Sandbox(pkg_tuple, venv_path=None)
        return

    tmp = Path(tempfile.mkdtemp(prefix="releaselens-sbx-"))
    venv = tmp / "venv"
    try:
        _run_uv(["uv", "venv", "--python", python, str(venv)])
        if packages:
            _run_uv(["uv", "pip", "install", "--python", str(venv / "bin" / "python"), *packages])
        yield Sandbox(pkg_tuple, venv_path=venv)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def register_stub(packages: list[str], cmd: list[str], result: SandboxResult) -> None:
    """Register a canned ``result`` for ``Sandbox.run(cmd)`` after ``sandbox(packages)``."""
    _stub_mode.register_stub(TOOL, _key(tuple(packages), cmd), result)


def _key(packages: tuple[str, ...], cmd: list[str]) -> Hashable:
    return (packages, tuple(cmd))


def _run_uv(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")


def _env_for(venv: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv)
    env["PATH"] = f"{venv / 'bin'}:{env.get('PATH', '')}"
    return env
