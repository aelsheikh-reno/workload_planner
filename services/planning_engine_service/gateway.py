"""Workflow Orchestrator gateway adapter for Planning Engine execution."""

from services.integration_service.service import IntegrationService
from services.workflow_orchestrator_service.gateways import (
    PlanningEngineGateway,
    PlanningEngineGatewayError,
)
from services.workflow_orchestrator_service.contracts import (
    PlanningEngineExecutionReceipt,
    PlanningEngineExecutionRequest,
)

from .service import PlanningEngineService


class PlanningEngineWorkflowGateway(PlanningEngineGateway):
    """Adapts the Orchestrator handoff contract into Planning Engine execution."""

    def __init__(
        self,
        integration_service: IntegrationService,
        planning_engine_service: PlanningEngineService,
    ) -> None:
        self._integration_service = integration_service
        self._planning_engine_service = planning_engine_service

    def submit_planning_run(
        self, request: PlanningEngineExecutionRequest
    ) -> PlanningEngineExecutionReceipt:
        bundle = self._integration_service.get_normalized_source_bundle(
            snapshot_id=request.source_snapshot_id
        )
        if bundle is None:
            raise PlanningEngineGatewayError(
                code="missing_normalized_source_snapshot",
                message="Planning Engine requires a normalized source snapshot to execute.",
            )
        if bundle.artifact.artifact_id != request.source_artifact_id:
            raise PlanningEngineGatewayError(
                code="source_artifact_mismatch",
                message="Planning Engine handoff source_artifact_id did not match the normalized source bundle.",
            )

        try:
            execution_result = self._planning_engine_service.execute_planning_run(
                bundle=bundle,
                workflow_instance_id=request.workflow_instance_id,
                planning_context_key=request.planning_context_key,
                source_snapshot_id=request.source_snapshot_id,
                source_artifact_id=request.source_artifact_id,
                requested_by=request.requested_by,
                requested_at=request.requested_at,
                attempt_number=request.attempt_number,
            )
        except ValueError as error:
            raise PlanningEngineGatewayError(
                code="planning_run_execution_rejected",
                message=str(error),
            )

        return PlanningEngineExecutionReceipt(
            planning_run_id=execution_result.execution_record.planning_run_id,
            accepted_at=execution_result.execution_record.accepted_at,
        )
