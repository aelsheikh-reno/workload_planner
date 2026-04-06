"""In-memory persistence for the Integration Service baseline."""

from typing import Dict, Optional

from .contracts import NormalizedSourceBundle, SourceReadiness


class InMemoryIntegrationRepository:
    """Small persistence seam so downstream consumers do not depend on internals."""

    def __init__(self) -> None:
        self._bundles_by_snapshot_id: Dict[str, NormalizedSourceBundle] = {}
        self._latest_snapshot_id: Optional[str] = None

    def save_bundle(self, bundle: NormalizedSourceBundle) -> None:
        self._bundles_by_snapshot_id[bundle.snapshot.snapshot_id] = bundle
        self._latest_snapshot_id = bundle.snapshot.snapshot_id

    def get_bundle(self, snapshot_id: str) -> Optional[NormalizedSourceBundle]:
        return self._bundles_by_snapshot_id.get(snapshot_id)

    def get_latest_bundle(self) -> Optional[NormalizedSourceBundle]:
        if self._latest_snapshot_id is None:
            return None
        return self._bundles_by_snapshot_id[self._latest_snapshot_id]

    def get_source_readiness(
        self, snapshot_id: Optional[str] = None
    ) -> Optional[SourceReadiness]:
        if snapshot_id is None:
            bundle = self.get_latest_bundle()
        else:
            bundle = self.get_bundle(snapshot_id)
        if bundle is None:
            return None
        return bundle.source_readiness
