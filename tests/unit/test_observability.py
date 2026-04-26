"""Tracing helpers must be no-ops when LANGFUSE_* env vars are absent."""

from __future__ import annotations

from releaselens.observability import langfuse as obs


def test_init_tracing_returns_false_without_env(monkeypatch):
    for key in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert obs.init_tracing() is False
    assert obs.tracing_active() is False


def test_get_callback_handler_returns_none_when_inactive(monkeypatch):
    for key in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    obs.init_tracing()
    assert obs.get_callback_handler("run-id") is None


def test_tool_span_is_noop_when_inactive(monkeypatch):
    for key in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    obs.init_tracing()
    with obs.tool_span("tool.example", x=1):
        pass
