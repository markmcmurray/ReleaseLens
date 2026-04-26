"""Test-wide fixtures.

Forces every non-LLM tool wrapper into stub mode and clears registered stubs
between tests. Keeps unit and integration tests infra-free per AGENTS.md.
"""

from __future__ import annotations

import pytest

from releaselens.tools import reset_stubs

_TOOL_ENV_VARS = (
    "RELEASELENS_RIPGREP_MODE",
    "RELEASELENS_GITHUB_MODE",
    "RELEASELENS_RAG_MODE",
    "RELEASELENS_UV_SANDBOX_MODE",
    "RELEASELENS_DIFFERENTIAL_RUNNER_MODE",
)


@pytest.fixture(autouse=True)
def _force_stub_tool_mode(monkeypatch):
    for var in _TOOL_ENV_VARS:
        monkeypatch.setenv(var, "stub")
    reset_stubs()
    yield
    reset_stubs()
