"""DevpiPublicConnector — public devpi target connector.

Scaffold stub: returns deterministic synthetic data. Real implementation deferred.
Satisfies the RegistryTarget Protocol via attribute shape (architecture.md §5, ADR-0006).
"""

from __future__ import annotations

from pathlib import Path

from releaselens.schemas import RegistryCapabilities, ResolvedTarget, TargetRef


class DevpiPublicConnector:
    name = "devpi-public"

    def __init__(self, base_url: str = "https://m.devpi.net") -> None:
        self.base_url = base_url

    def resolve(self, ref: TargetRef) -> ResolvedTarget:
        pinned = ref.version or "0.0.0-stub"
        return ResolvedTarget(
            ref=ref,
            pinned_version=pinned,
            artefact_url=f"{self.base_url}/{ref.package}/{pinned}-stub.tar.gz",
        )

    def fetch_source(self, resolved: ResolvedTarget, dest: Path) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def fetch_metadata(self, resolved: ResolvedTarget) -> dict:
        return {"stub": True, "package": resolved.ref.package}

    def registry_capabilities(self) -> RegistryCapabilities:
        return RegistryCapabilities(
            serves_pep_691_json=True,
            serves_pep_658_metadata=False,
            serves_pep_740_attestations=False,
            notes="STUB",
        )
