"""In-memory persistence for the Integration Service baseline."""

from typing import Dict, Optional

from .contracts import (
    BoundedWriteBackRequest,
    BoundedWriteBackResult,
    NormalizedSourceBundle,
    SourceReadiness,
)


class InMemoryIntegrationRepository:
    """Small persistence seam so downstream consumers do not depend on internals."""

    def __init__(self) -> None:
        self._bundles_by_snapshot_id: Dict[str, NormalizedSourceBundle] = {}
        self._latest_snapshot_id: Optional[str] = None
        self._write_back_requests_by_request_id: Dict[str, BoundedWriteBackRequest] = {}
        self._write_back_results_by_request_id: Dict[str, BoundedWriteBackResult] = {}
        self._latest_write_back_request_id_by_activation_id: Dict[str, str] = {}
        self._write_back_request_id_by_idempotency_key: Dict[str, str] = {}

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

    def save_write_back_request(self, request: BoundedWriteBackRequest) -> None:
        self._write_back_requests_by_request_id[request.request_id] = request
        if request.idempotency_key:
            self._write_back_request_id_by_idempotency_key[request.idempotency_key] = (
                request.request_id
            )

    def get_write_back_request(
        self,
        request_id: Optional[str] = None,
        activation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[BoundedWriteBackRequest]:
        resolved_request_id = self._resolve_write_back_request_id(
            request_id=request_id,
            activation_id=activation_id,
            idempotency_key=idempotency_key,
        )
        if resolved_request_id is None:
            return None
        return self._write_back_requests_by_request_id.get(resolved_request_id)

    def save_write_back_result(self, result: BoundedWriteBackResult) -> None:
        self._write_back_results_by_request_id[result.request_id] = result
        self._latest_write_back_request_id_by_activation_id[result.activation_id] = (
            result.request_id
        )

    def get_write_back_result(
        self,
        request_id: Optional[str] = None,
        activation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[BoundedWriteBackResult]:
        resolved_request_id = self._resolve_write_back_request_id(
            request_id=request_id,
            activation_id=activation_id,
            idempotency_key=idempotency_key,
        )
        if resolved_request_id is None:
            return None
        return self._write_back_results_by_request_id.get(resolved_request_id)

    def _resolve_write_back_request_id(
        self,
        request_id: Optional[str],
        activation_id: Optional[str],
        idempotency_key: Optional[str],
    ) -> Optional[str]:
        if request_id is not None:
            return request_id
        if idempotency_key is not None:
            return self._write_back_request_id_by_idempotency_key.get(idempotency_key)
        if activation_id is not None:
            return self._latest_write_back_request_id_by_activation_id.get(activation_id)
        return None
