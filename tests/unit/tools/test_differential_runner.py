"""Stub-mode tests for the differential runner + legacy alias check."""

from __future__ import annotations

import pytest

from releaselens.schemas import DifferentialTest
from releaselens.tools import StubNotRegistered, differential_runner
from releaselens.tools.differential_runner import DifferentialResult, _resolve_json_path


def _test_obj(test_id: str, kind: str = "static_signature") -> DifferentialTest:
    return DifferentialTest(
        id=test_id,
        claim_id="claim-1",
        test_kind=kind,  # type: ignore[arg-type]
        setup="",
        invocation="",
        expected="",
        differentiator="",
        iteration=0,
    )


def test_stub_returns_registered_result():
    expected = DifferentialResult(test_id="t1", outcome="pass", detail="stubbed")
    differential_runner.register_stub("t1", expected)

    assert differential_runner.run(_test_obj("t1")) == expected


def test_stub_unregistered_raises():
    with pytest.raises(StubNotRegistered):
        differential_runner.run(_test_obj("missing"))


def test_behavioural_probe_rejects_prose_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """When setup carries free-form English (test_author drift), the runner
    must short-circuit with a clean ``error`` outcome rather than hand
    junk to ``uv pip install`` and crash several layers deep."""
    monkeypatch.setenv("RELEASELENS_DIFFERENTIAL_RUNNER_MODE", "real")
    monkeypatch.setenv("RELEASELENS_UV_SANDBOX_MODE", "stub")

    test = DifferentialTest(
        id="t-prose",
        claim_id="claim-1",
        test_kind="behavioural_probe",
        setup="Create a Python package with a 'data-dist-info-metadata' attribute.",
        invocation="pip install some-pkg",
        expected="data-dist-info-metadata",
        differentiator="older pip omits this",
        iteration=0,
    )
    result = differential_runner.run(test)
    assert result.outcome == "error"
    assert "non-pip-installable" in result.detail


def test_legacy_probe_mode_alias(monkeypatch):
    """RELEASELENS_PROBE_MODE=stub should be honoured when canonical var is unset."""
    monkeypatch.delenv("RELEASELENS_DIFFERENTIAL_RUNNER_MODE", raising=False)
    monkeypatch.setenv("RELEASELENS_PROBE_MODE", "stub")
    expected = DifferentialResult(test_id="t-legacy", outcome="pass", detail="legacy")
    differential_runner.register_stub("t-legacy", expected)

    assert differential_runner.run(_test_obj("t-legacy")) == expected


def test_resolve_json_path_object_and_array():
    payload = {"meta": {"versions": ["a", "b", "c"]}}
    assert _resolve_json_path(payload, "$") == payload
    assert _resolve_json_path(payload, "$.meta.versions") == ["a", "b", "c"]
    assert _resolve_json_path(payload, "$.meta.versions[1]") == "b"
