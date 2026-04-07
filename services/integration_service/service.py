"""Application service for fixture-driven source intake, normalization, and write-back."""

from dataclasses import replace
from typing import Any, Dict, List, Optional

from .contracts import (
    ALLOWED_WRITE_BACK_FIELDS,
    BOUND_WRITE_BACK_ACTION_UPDATE_PROJECT_FIELDS,
    BOUND_WRITE_BACK_ACTION_UPDATE_TASK_FIELDS,
    BOUND_WRITE_BACK_TRIGGER_STEP,
    WRITE_BACK_ITEM_STATUS_FAILED,
    WRITE_BACK_ITEM_STATUS_SUCCEEDED,
    WRITE_BACK_STATUS_FAILED,
    WRITE_BACK_STATUS_PARTIAL,
    WRITE_BACK_STATUS_SUCCEEDED,
    BoundedWriteBackExecutionReceipt,
    BoundedWriteBackItemResult,
    BoundedWriteBackRequest,
    BoundedWriteBackResult,
    NormalizedSourceBundle,
    SourceReadiness,
)
from .gateways import ExternalWriteBackGateway, ExternalWriteBackGatewayError
from .normalizer import normalize_source_plan
from .repository import InMemoryIntegrationRepository


class IntegrationService:
    """Owns source intake, normalization, artifacts, mappings, and write-back."""

    def __init__(
        self,
        repository: Optional[InMemoryIntegrationRepository] = None,
        external_write_back_gateway: Optional[ExternalWriteBackGateway] = None,
    ) -> None:
        self._repository = repository or InMemoryIntegrationRepository()
        self._external_write_back_gateway = external_write_back_gateway

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

    def execute_bounded_external_write_back(
        self,
        request: BoundedWriteBackRequest,
    ) -> BoundedWriteBackResult:
        self._validate_bounded_write_back_request(request)
        existing_result = self._repository.get_write_back_result(request_id=request.request_id)
        if existing_result is not None:
            return replace(existing_result, reused_existing=True)

        if request.idempotency_key is not None:
            existing_by_idempotency = self._repository.get_write_back_result(
                idempotency_key=request.idempotency_key
            )
            if existing_by_idempotency is not None:
                return replace(existing_by_idempotency, reused_existing=True)

        if self._external_write_back_gateway is None:
            raise ValueError(
                "A bounded external write-back gateway is required before executing write-back."
            )

        bundle = self._repository.get_bundle(request.source_snapshot_id)
        if bundle is None:
            raise ValueError(
                "A normalized source snapshot is required before bounded external write-back."
            )

        self._repository.save_write_back_request(request)
        try:
            receipt = self._external_write_back_gateway.execute_write_back(request)
        except ExternalWriteBackGatewayError as error:
            receipt = BoundedWriteBackExecutionReceipt(
                completed_at=request.requested_at,
                item_results=[
                    BoundedWriteBackItemResult(
                        target_id=target.target_id,
                        delta_id=target.delta_id,
                        entity_type=target.entity_type,
                        entity_external_id=target.entity_external_id,
                        status=WRITE_BACK_ITEM_STATUS_FAILED,
                        applied_fields=[],
                        error_code=error.code,
                        error_message=error.message,
                    )
                    for target in request.targets
                ],
            )

        item_results = _normalize_item_results(
            request=request,
            item_results=receipt.item_results,
        )
        result = _build_write_back_result(
            request=request,
            source_system=bundle.snapshot.source_system,
            completed_at=receipt.completed_at,
            item_results=item_results,
        )
        self._repository.save_write_back_result(result)
        return result

    def get_write_back_result(
        self,
        request_id: Optional[str] = None,
        activation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[BoundedWriteBackResult]:
        return self._repository.get_write_back_result(
            request_id=request_id,
            activation_id=activation_id,
            idempotency_key=idempotency_key,
        )

    def _validate_bounded_write_back_request(
        self,
        request: BoundedWriteBackRequest,
    ) -> None:
        if not request.request_id:
            raise ValueError("request_id is required for bounded external write-back.")
        if not request.activation_command_id:
            raise ValueError(
                "activation_command_id is required for bounded external write-back."
            )
        if not request.activation_id:
            raise ValueError("activation_id is required for bounded external write-back.")
        if not request.review_context_id:
            raise ValueError(
                "review_context_id is required for bounded external write-back."
            )
        if not request.approved_plan_id:
            raise ValueError(
                "approved_plan_id is required for bounded external write-back."
            )
        if not request.source_snapshot_id:
            raise ValueError(
                "source_snapshot_id is required for bounded external write-back."
            )
        if not request.orchestrator_workflow_instance_id:
            raise ValueError(
                "orchestrator_workflow_instance_id is required for bounded external write-back."
            )
        if request.orchestrator_step_name != BOUND_WRITE_BACK_TRIGGER_STEP:
            raise ValueError(
                "Bounded external write-back must be triggered from the activation side-effect sequencing step."
            )
        if request.attempt_number < 1:
            raise ValueError(
                "attempt_number must be positive for bounded external write-back."
            )
        if not request.targets:
            raise ValueError(
                "At least one approved write-back target is required for bounded external write-back."
            )

        for target in request.targets:
            if target.write_back_action not in (
                BOUND_WRITE_BACK_ACTION_UPDATE_TASK_FIELDS,
                BOUND_WRITE_BACK_ACTION_UPDATE_PROJECT_FIELDS,
            ):
                raise ValueError(
                    "Unsupported bounded external write-back action: %s"
                    % target.write_back_action
                )
            unsupported_fields = [
                field_name
                for field_name in target.write_back_fields
                if field_name not in ALLOWED_WRITE_BACK_FIELDS
            ]
            if unsupported_fields:
                raise ValueError(
                    "Unsupported bounded external write-back fields: %s"
                    % ",".join(sorted(unsupported_fields))
                )


def _normalize_item_results(
    request: BoundedWriteBackRequest,
    item_results: List[BoundedWriteBackItemResult],
) -> List[BoundedWriteBackItemResult]:
    results_by_target_id = {
        item_result.target_id: item_result for item_result in item_results
    }
    if len(results_by_target_id) != len(item_results):
        raise ValueError("Bounded external write-back returned duplicate target results.")

    normalized_results: List[BoundedWriteBackItemResult] = []
    for target in request.targets:
        if target.target_id not in results_by_target_id:
            raise ValueError(
                "Bounded external write-back did not return a result for target_id: %s"
                % target.target_id
            )
        item_result = results_by_target_id[target.target_id]
        if item_result.status not in (
            WRITE_BACK_ITEM_STATUS_SUCCEEDED,
            WRITE_BACK_ITEM_STATUS_FAILED,
        ):
            raise ValueError(
                "Unsupported bounded external write-back item status: %s"
                % item_result.status
            )
        normalized_results.append(
            BoundedWriteBackItemResult(
                target_id=item_result.target_id,
                delta_id=item_result.delta_id,
                entity_type=item_result.entity_type,
                entity_external_id=item_result.entity_external_id,
                status=item_result.status,
                applied_fields=sorted(item_result.applied_fields),
                error_code=item_result.error_code,
                error_message=item_result.error_message,
            )
        )
    return normalized_results


def _build_write_back_result(
    request: BoundedWriteBackRequest,
    source_system: str,
    completed_at: str,
    item_results: List[BoundedWriteBackItemResult],
) -> BoundedWriteBackResult:
    succeeded_target_count = sum(
        1
        for item_result in item_results
        if item_result.status == WRITE_BACK_ITEM_STATUS_SUCCEEDED
    )
    failed_target_count = sum(
        1
        for item_result in item_results
        if item_result.status == WRITE_BACK_ITEM_STATUS_FAILED
    )
    if failed_target_count == 0:
        status = WRITE_BACK_STATUS_SUCCEEDED
    elif succeeded_target_count == 0:
        status = WRITE_BACK_STATUS_FAILED
    else:
        status = WRITE_BACK_STATUS_PARTIAL

    return BoundedWriteBackResult(
        request_id=request.request_id,
        activation_command_id=request.activation_command_id,
        activation_id=request.activation_id,
        review_context_id=request.review_context_id,
        approved_plan_id=request.approved_plan_id,
        source_snapshot_id=request.source_snapshot_id,
        source_system=source_system,
        orchestrator_workflow_instance_id=request.orchestrator_workflow_instance_id,
        orchestrator_step_name=request.orchestrator_step_name,
        attempt_number=request.attempt_number,
        status=status,
        total_target_count=len(item_results),
        succeeded_target_count=succeeded_target_count,
        failed_target_count=failed_target_count,
        requested_by=request.requested_by,
        requested_at=request.requested_at,
        completed_at=completed_at,
        reused_existing=False,
        item_results=item_results,
    )
