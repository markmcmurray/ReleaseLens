"""Re-exports for schemas (architecture.md §4)."""

from releaselens.schemas.evidence import (
    FeatureMatrix,
    FeatureMatrixRow,
    ImplementationEvidence,
    Method,
    Tool,
)
from releaselens.schemas.feature import Feature, SpecClaim
from releaselens.schemas.impact import ImpactFinding, TargetRef
from releaselens.schemas.report import FeatureReport, ReportSummary
from releaselens.schemas.support import (
    ErrorRecord,
    PEPSource,
    RegistryCapabilities,
    ResolvedTarget,
)
from releaselens.schemas.tests import (
    DifferentialTest,
    TestAuthoringResult,
    TestCritique,
)
from releaselens.schemas.verification import ClaimEvidenceLink, VerificationResult

__all__ = [
    "ClaimEvidenceLink",
    "DifferentialTest",
    "ErrorRecord",
    "Feature",
    "FeatureMatrix",
    "FeatureMatrixRow",
    "FeatureReport",
    "ImpactFinding",
    "ImplementationEvidence",
    "Method",
    "PEPSource",
    "RegistryCapabilities",
    "ReportSummary",
    "ResolvedTarget",
    "SpecClaim",
    "TargetRef",
    "TestAuthoringResult",
    "TestCritique",
    "Tool",
    "VerificationResult",
]
