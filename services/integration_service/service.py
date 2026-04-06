"""Application service for fixture-driven source intake and normalization."""

from typing import Any, Dict, Optional

from .contracts import NormalizedSourceBundle, SourceReadiness
from .normalizer import normalize_source_plan
from .repository import InMemoryIntegrationRepository


class IntegrationService:
    """Owns source intake, normalization, artifacts, and mappings for EPIC-01."""

    def __init__(self, repository: Optional[InMemoryIntegrationRepository] = None) -> None:
        self._repository = repository or InMemoryIntegrationRepository()

    def import_source_plan(self, raw_payload: Dict[str, Any]) -> NormalizedSourceBundle:
        bundle = normalize_source_plan(raw_payload)
        self._repository.save_bundle(bundle)
        return bundle

    def get_normalized_source_bundle(
        self, snapshot_id: Optional[str] = None
    ) -> Optional[NormalizedSourceBundle]:
        if snapshot_id is None:
            return self._repository.get_latest_bundle()
        return self._repository.get_bundle(snapshot_id)

    def get_source_readiness(
        self, snapshot_id: Optional[str] = None
    ) -> Optional[SourceReadiness]:
        return self._repository.get_source_readiness(snapshot_id=snapshot_id)
