"""Integration Service baseline for source intake and normalization."""

from .contracts import (
    NormalizedDependencyRecord,
    NormalizedResourceExceptionRecord,
    NormalizedResourceRecord,
    NormalizedResourceAssignmentRecord,
    NormalizedSourceBundle,
    NormalizedTaskRecord,
    SourceArtifact,
    SourceMapping,
    SourceReadiness,
    SourceSetupIssueFact,
    SourceSnapshot,
)
from .repository import InMemoryIntegrationRepository
from .service import IntegrationService

__all__ = [
    "IntegrationService",
    "InMemoryIntegrationRepository",
    "NormalizedDependencyRecord",
    "NormalizedResourceExceptionRecord",
    "NormalizedResourceRecord",
    "NormalizedResourceAssignmentRecord",
    "NormalizedSourceBundle",
    "NormalizedTaskRecord",
    "SourceArtifact",
    "SourceMapping",
    "SourceReadiness",
    "SourceSetupIssueFact",
    "SourceSnapshot",
]
