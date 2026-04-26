"""Non-LLM tool wrappers (architecture.md §9).

Each submodule has a uniform stub-mode toggle via ``RELEASELENS_<TOOL>_MODE``.
"""

from releaselens.tools import ripgrep
from releaselens.tools._stub_mode import StubNotRegistered, mode_for, reset_stubs

__all__ = ["StubNotRegistered", "mode_for", "reset_stubs", "ripgrep"]
