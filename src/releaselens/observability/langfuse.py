"""Langfuse tracing wiring (architecture.md §10).

Three seams keep tracing observable everywhere without any node importing
Langfuse directly:

- :func:`init_tracing` registers Langfuse as a LiteLLM callback so every
  generation produced via ``llm.call`` becomes a span automatically.
- :func:`get_callback_handler` returns a LangChain ``CallbackHandler`` to
  attach to ``graph.invoke``; this produces one span per LangGraph node.
- :func:`tool_span` is a context manager used by tool wrappers to emit a
  span around a real-mode call. No-op when tracing is inactive.

All three become no-ops when the ``LANGFUSE_*`` env vars are absent, so the
test suite stays infra-free. Targets Langfuse SDK v2 (paired with the v2
self-host server in ``infra/langfuse/``); v3+ is OTEL-based and requires the
heavier Clickhouse/Redis/MinIO server stack.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

current_run_id: ContextVar[str | None] = ContextVar("releaselens_run_id", default=None)

_REQUIRED_ENV = ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
_active = False


def tracing_active() -> bool:
    return _active


def init_tracing() -> bool:
    """Register Langfuse as a LiteLLM callback. Returns True if tracing is live."""
    global _active
    if not all(os.environ.get(k) for k in _REQUIRED_ENV):
        _active = False
        return False

    import litellm

    if "langfuse" not in (litellm.success_callback or []):
        litellm.success_callback = [*(litellm.success_callback or []), "langfuse"]
    if "langfuse" not in (litellm.failure_callback or []):
        litellm.failure_callback = [*(litellm.failure_callback or []), "langfuse"]
    _active = True
    return True


def get_callback_handler(run_id: str, *, tags: list[str] | None = None) -> Any | None:
    """Return a LangChain callback bound to this run; None when tracing inactive."""
    if not _active:
        return None
    from langfuse.callback import CallbackHandler

    return CallbackHandler(session_id=run_id, user_id="cli", tags=tags or [])


@contextmanager
def tool_span(name: str, **attrs: Any) -> Iterator[None]:
    """Emit a free-standing tool span attached to the current run; no-op if inactive.

    v2 has no shared OTEL context with the LangChain callback handler, so this
    span is sibling to (not nested under) the LangGraph node that triggered it.
    Both are grouped in the UI by the run's session_id, which is the
    walkability bar architecture §10.1 actually requires.
    """
    if not _active:
        yield
        return

    from langfuse import Langfuse

    rid = current_run_id.get()
    client = Langfuse()
    span = client.span(
        trace_id=rid,
        name=name,
        metadata={"run_id": rid, **attrs},
    )
    try:
        yield
    except Exception as exc:
        span.update(level="ERROR", status_message=str(exc))
        raise
    finally:
        span.end()
        client.flush()
