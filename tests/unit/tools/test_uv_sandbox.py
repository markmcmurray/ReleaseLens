"""Stub-mode tests for the uv_sandbox wrapper."""

from __future__ import annotations

import pytest

from releaselens.tools import StubNotRegistered, uv_sandbox
from releaselens.tools.uv_sandbox import SandboxResult


def test_stub_run_returns_registered_result():
    expected = SandboxResult(stdout="ok\n", stderr="", exit_code=0)
    uv_sandbox.register_stub(["pip"], ["pip", "--version"], expected)

    with uv_sandbox.sandbox(["pip"]) as sbx:
        result = sbx.run(["pip", "--version"])

    assert result == expected


def test_stub_unregistered_raises():
    with uv_sandbox.sandbox(["uv"]) as sbx:
        with pytest.raises(StubNotRegistered):
            sbx.run(["uv", "version"])
