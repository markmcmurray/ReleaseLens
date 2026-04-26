"""Langfuse tracing init (architecture.md §10).

No-op when LANGFUSE_HOST is unset. Once env is configured, wires the LiteLLM callback
hook so all model calls automatically produce spans. Nodes don't import Langfuse
directly — observability is swappable.
"""

from __future__ import annotations

import os


def init_tracing() -> bool:
    """Initialise Langfuse tracing if configured. Returns True if active.

    Stub implementation: detects env vars and reports active/inactive without
    actually wiring callbacks. Real callback wiring is deferred to a later block.
    """
    host = os.environ.get("LANGFUSE_HOST")
    if not host:
        return False
    # Real wiring deferred. Acknowledge env so the seam is verifiable in trace.
    return True
