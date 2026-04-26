"""RegistryTarget Protocol — structural typing for registry-backed target codebases.

See architecture.md §5 and ADR-0006. Connectors satisfy this Protocol by attribute
shape; no inheritance required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from releaselens.schemas import (
    RegistryCapabilities,
    ResolvedTarget,
    TargetRef,
)


@runtime_checkable
class RegistryTarget(Protocol):
    """A registry-backed source of target codebases for impact analysis."""

    name: str

    def resolve(self, ref: TargetRef) -> ResolvedTarget:
        """Pin ref to a concrete version and assert it exists. Raises TargetNotFound."""
        ...

    def fetch_source(self, resolved: ResolvedTarget, dest: Path) -> Path:
        """Materialise the source tree. Returns the directory it was extracted into."""
        ...

    def fetch_metadata(self, resolved: ResolvedTarget) -> dict:
        """Return registry-served metadata (PEP 658 sidecars, etc.)."""
        ...

    def registry_capabilities(self) -> RegistryCapabilities:
        """What does the registry itself expose? PEP 691 JSON, PEP 658 metadata, etc."""
        ...


class TargetNotFound(Exception):
    """Raised when a TargetRef cannot be resolved against the connector."""
