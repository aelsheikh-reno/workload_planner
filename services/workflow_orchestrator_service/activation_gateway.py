"""Activation execution gateway adapters for post-activation downstream hooks."""

import hashlib

from services.integration_service import (
    BOUND_WRITE_BACK_TRIGGER_STEP,
    BoundedWriteBackRequest,
    BoundedWriteBackTarget,
    IntegrationService,
    WRITE_BACK_STATUS_PARTIAL,
    WRITE_BACK_STATUS_FAILED,
)

from .contracts import (
    ACTIVATION_RECOMPUTATION_STEP,
    ACTIVATION_SIDE_EFFECTS_STEP,
    ActivationExecutionStepReceipt,
    ActivationExecutionStepRequest,
)
from .gateways import ActivationExecutionGateway, ActivationExecutionGatewayError


class IntegrationBackedActivationExecutionGateway(ActivationExecutionGateway):
    """Routes post-activation side effects into Integration-owned write-back."""

    def __init__(self, integration_service: IntegrationService) -> None:
        self._integration_service = integration_service

    def submit_step(
        self, request: ActivationExecutionStepRequest
    ) -> ActivationExecutionStepReceipt:
        if request.step_name == ACTIVATION_RECOMPUTATION_STEP:
            return ActivationExecutionStepReceipt(
                step_name=request.step_name,
                handoff_id=_stable_id(
                    "activation-recompute-handoff",
                    request.workflow_instance_id,
                    str(request.attempt_number),
                ),
                accepted_at=request.requested_at,
            )

        if request.step_name != ACTIVATION_SIDE_EFFECTS_STEP:
            raise ActivationExecutionGatewayError(
                code="unsupported_activation_step",
                message="Unsupported activation execution step: %s"
                % request.step_name,
            )

        if not request.write_back_targets:
            return ActivationExecutionStepReceipt(
                step_name=request.step_name,
                handoff_id=_stable_id(
                    "activation-side-effects-noop",
                    request.workflow_instance_id,
                    str(request.attempt_number),
                ),
                accepted_at=request.requested_at,
            )

        if request.source_snapshot_id is None:
            raise ActivationExecutionGatewayError(
                code="missing_source_snapshot_id",
                message="source_snapshot_id is required for bounded post-activation write-back.",
            )

        try:
            write_back_result = self._integration_service.execute_bounded_external_write_back(
                BoundedWriteBackRequest(
                    request_id=_stable_id(
                        "write-back-request",
                        request.workflow_instance_id,
                        request.step_name,
                        str(request.attempt_number),
                    ),
                    activation_command_id=request.activation_command_id,
                    activation_id=request.activation_id,
                    review_context_id=request.review_context_id,
                    approved_plan_id=request.approved_plan_id,
                    source_snapshot_id=request.source_snapshot_id,
                    orchestrator_workflow_instance_id=request.workflow_instance_id,
                    orchestrator_step_name=BOUND_WRITE_BACK_TRIGGER_STEP,
                    requested_by=request.requested_by,
                    requested_at=request.requested_at,
                    attempt_number=request.attempt_number,
                    targets=[
                        BoundedWriteBackTarget(
                            target_id=target.target_id,
                            delta_id=target.delta_id,
                            entity_type=target.entity_type,
                            entity_external_id=target.entity_external_id,
                            entity_name=target.entity_name,
                            project_external_id=target.project_external_id,
                            write_back_action=target.write_back_action,
                            write_back_fields=list(target.write_back_fields),
                        )
                        for target in request.write_back_targets
                    ],
                    idempotency_key=_stable_id(
                        "write-back-idempotency",
                        request.workflow_instance_id,
                        request.step_name,
                        str(request.attempt_number),
                    ),
                )
            )
        except ValueError as error:
            raise ActivationExecutionGatewayError(
                code="bounded_write_back_rejected",
                message=str(error),
            )

        if write_back_result.status == WRITE_BACK_STATUS_PARTIAL:
            raise ActivationExecutionGatewayError(
                code="bounded_write_back_partial",
                message="Bounded external write-back completed partially for activation %s."
                % request.activation_id,
            )
        if write_back_result.status == WRITE_BACK_STATUS_FAILED:
            raise ActivationExecutionGatewayError(
                code="bounded_write_back_failed",
                message="Bounded external write-back failed for activation %s."
                % request.activation_id,
            )

        return ActivationExecutionStepReceipt(
            step_name=request.step_name,
            handoff_id=write_back_result.request_id,
            accepted_at=write_back_result.completed_at,
        )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:16]
    return "%s_%s" % (prefix, digest)
