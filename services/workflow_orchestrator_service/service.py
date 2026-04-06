"""Workflow Orchestrator baseline for planning-run and activation job state."""

import hashlib
from dataclasses import replace
from typing import Optional

from services.integration_service.service import IntegrationService

from .contracts import (
    ACTIVATION_RECOMPUTATION_STEP,
    ACTIVATION_SIDE_EFFECTS_STEP,
    ACTIVATION_WORKFLOW_TYPE,
    PLANNING_ENGINE_EXECUTION_STEP,
    PLANNING_RUN_WORKFLOW_TYPE,
    STEP_STATUS_DISPATCHED,
    STEP_STATUS_FAILED,
    STEP_STATUS_PENDING,
    STEP_STATUS_RETRY_PENDING,
    STEP_STATUS_RUNNING,
    STEP_STATUS_SUCCEEDED,
    WORKFLOW_STATUS_DISPATCHED,
    WORKFLOW_STATUS_FAILED,
    WORKFLOW_STATUS_QUEUED,
    WORKFLOW_STATUS_RETRY_PENDING,
    WORKFLOW_STATUS_RUNNING,
    WORKFLOW_STATUS_SUCCEEDED,
    ActivationExecutionStepRequest,
    ActivationWorkflowInstance,
    ActivationWorkflowStartResult,
    ActivationWorkflowStatusView,
    ActivationWorkflowTrigger,
    PlanningEngineExecutionRequest,
    PlanningRunStartResult,
    PlanningRunStatusView,
    PlanningRunTrigger,
    PlanningRunWorkflowInstance,
    WorkflowStepInstance,
)
from .gateways import (
    ActivationExecutionGateway,
    ActivationExecutionGatewayError,
    PlanningEngineGateway,
    PlanningEngineGatewayError,
)
from .repository import InMemoryWorkflowOrchestratorRepository


class PlanningRunAdmissionError(ValueError):
    """Raised when a planning run cannot be admitted into workflow execution."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ActivationWorkflowAdmissionError(ValueError):
    """Raised when activation cannot be admitted into async workflow execution."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WorkflowTransitionError(ValueError):
    """Raised when a workflow transition would violate the lifecycle model."""


class WorkflowOrchestratorService:
    """Owns workflow/job state and cross-service async execution sequencing."""

    def __init__(
        self,
        integration_service: IntegrationService,
        planning_engine_gateway: PlanningEngineGateway,
        repository: Optional[InMemoryWorkflowOrchestratorRepository] = None,
        activation_execution_gateway: Optional[ActivationExecutionGateway] = None,
    ) -> None:
        self._integration_service = integration_service
        self._planning_engine_gateway = planning_engine_gateway
        self._repository = repository or InMemoryWorkflowOrchestratorRepository()
        self._activation_execution_gateway = activation_execution_gateway

    def start_planning_run(self, trigger: PlanningRunTrigger) -> PlanningRunStartResult:
        self._validate_trigger(trigger)

        existing = self._repository.find_active_workflow_for_context(
            trigger.planning_context_key, trigger.source_snapshot_id
        )
        if existing is not None:
            return PlanningRunStartResult(
                workflow_instance=existing,
                reused_existing=True,
                handoff_request=None,
            )

        bundle = self._integration_service.get_normalized_source_bundle(
            trigger.source_snapshot_id
        )
        readiness = self._integration_service.get_source_readiness(
            trigger.source_snapshot_id
        )
        if bundle is None:
            raise PlanningRunAdmissionError(
                "missing_normalized_source_snapshot",
                "A normalized source snapshot is required before starting a planning run.",
            )
        if readiness is None or not readiness.runnable:
            raise PlanningRunAdmissionError(
                "source_not_runnable",
                "Planning runs may start only when the normalized source snapshot is runnable.",
            )

        workflow_instance_id = self._stable_id(
            "workflow",
            trigger.planning_context_key,
            trigger.requested_at,
            trigger.idempotency_key or "no-idempotency-key",
        )
        workflow = PlanningRunWorkflowInstance(
            workflow_instance_id=workflow_instance_id,
            workflow_type=PLANNING_RUN_WORKFLOW_TYPE,
            planning_context_key=trigger.planning_context_key,
            source_snapshot_id=trigger.source_snapshot_id,
            source_artifact_id=bundle.artifact.artifact_id,
            current_status=WORKFLOW_STATUS_QUEUED,
            current_step=PLANNING_ENGINE_EXECUTION_STEP,
            current_attempt=1,
            max_attempts=trigger.max_attempts,
            requested_by=trigger.requested_by,
            requested_at=trigger.requested_at,
            idempotency_key=trigger.idempotency_key,
            planning_engine_run_id=None,
            last_transition_at=trigger.requested_at,
            completed_at=None,
            last_error_code=None,
            last_error_message=None,
        )
        step = WorkflowStepInstance(
            workflow_instance_id=workflow.workflow_instance_id,
            step_name=PLANNING_ENGINE_EXECUTION_STEP,
            status=STEP_STATUS_PENDING,
            attempt_number=1,
            last_updated_at=trigger.requested_at,
        )
        self._repository.save_workflow(workflow)
        self._repository.save_step(step)
        self._repository.append_transition(
            workflow_instance_id=workflow.workflow_instance_id,
            from_status=None,
            to_status=WORKFLOW_STATUS_QUEUED,
            occurred_at=trigger.requested_at,
            reason="planning_run_requested",
        )

        handoff_request = PlanningEngineExecutionRequest(
            workflow_instance_id=workflow.workflow_instance_id,
            planning_context_key=workflow.planning_context_key,
            source_snapshot_id=workflow.source_snapshot_id,
            source_artifact_id=workflow.source_artifact_id,
            requested_by=workflow.requested_by,
            requested_at=workflow.requested_at,
            attempt_number=workflow.current_attempt,
        )

        try:
            receipt = self._planning_engine_gateway.submit_planning_run(handoff_request)
        except PlanningEngineGatewayError as error:
            failed_workflow = self._apply_failure_transition(
                workflow=workflow,
                step=step,
                occurred_at=trigger.requested_at,
                error_code=error.code,
                error_message=error.message,
                retryable=workflow.current_attempt < workflow.max_attempts,
            )
            return PlanningRunStartResult(
                workflow_instance=failed_workflow,
                reused_existing=False,
                handoff_request=handoff_request,
            )

        dispatched_workflow = replace(
            workflow,
            current_status=WORKFLOW_STATUS_DISPATCHED,
            planning_engine_run_id=receipt.planning_run_id,
            last_transition_at=receipt.accepted_at,
        )
        dispatched_step = replace(
            step,
            status=STEP_STATUS_DISPATCHED,
            last_updated_at=receipt.accepted_at,
        )
        self._repository.save_workflow(dispatched_workflow)
        self._repository.save_step(dispatched_step)
        self._repository.append_transition(
            workflow_instance_id=workflow.workflow_instance_id,
            from_status=WORKFLOW_STATUS_QUEUED,
            to_status=WORKFLOW_STATUS_DISPATCHED,
            occurred_at=receipt.accepted_at,
            reason="planning_engine_handoff_accepted",
        )
        return PlanningRunStartResult(
            workflow_instance=dispatched_workflow,
            reused_existing=False,
            handoff_request=handoff_request,
        )

    def mark_planning_run_running(
        self, workflow_instance_id: str, occurred_at: str
    ) -> PlanningRunWorkflowInstance:
        workflow = self._require_workflow(workflow_instance_id)
        step = self._require_step(workflow_instance_id)
        self._assert_status(workflow.current_status, (WORKFLOW_STATUS_DISPATCHED,))

        updated_workflow = replace(
            workflow,
            current_status=WORKFLOW_STATUS_RUNNING,
            last_transition_at=occurred_at,
        )
        updated_step = replace(
            step,
            status=STEP_STATUS_RUNNING,
            last_updated_at=occurred_at,
        )
        self._repository.save_workflow(updated_workflow)
        self._repository.save_step(updated_step)
        self._repository.append_transition(
            workflow_instance_id=workflow_instance_id,
            from_status=workflow.current_status,
            to_status=WORKFLOW_STATUS_RUNNING,
            occurred_at=occurred_at,
            reason="planning_engine_execution_started",
        )
        return updated_workflow

    def mark_planning_run_succeeded(
        self, workflow_instance_id: str, occurred_at: str
    ) -> PlanningRunWorkflowInstance:
        workflow = self._require_workflow(workflow_instance_id)
        step = self._require_step(workflow_instance_id)
        self._assert_status(workflow.current_status, (WORKFLOW_STATUS_RUNNING,))

        updated_workflow = replace(
            workflow,
            current_status=WORKFLOW_STATUS_SUCCEEDED,
            last_transition_at=occurred_at,
            completed_at=occurred_at,
            last_error_code=None,
            last_error_message=None,
        )
        updated_step = replace(
            step,
            status=STEP_STATUS_SUCCEEDED,
            last_updated_at=occurred_at,
        )
        self._repository.save_workflow(updated_workflow)
        self._repository.save_step(updated_step)
        self._repository.append_transition(
            workflow_instance_id=workflow_instance_id,
            from_status=workflow.current_status,
            to_status=WORKFLOW_STATUS_SUCCEEDED,
            occurred_at=occurred_at,
            reason="planning_engine_execution_succeeded",
        )
        return updated_workflow

    def mark_planning_run_failed(
        self,
        workflow_instance_id: str,
        occurred_at: str,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> PlanningRunWorkflowInstance:
        workflow = self._require_workflow(workflow_instance_id)
        step = self._require_step(workflow_instance_id)
        self._assert_status(
            workflow.current_status,
            (WORKFLOW_STATUS_DISPATCHED, WORKFLOW_STATUS_RUNNING),
        )
        return self._apply_failure_transition(
            workflow=workflow,
            step=step,
            occurred_at=occurred_at,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable and workflow.current_attempt < workflow.max_attempts,
        )

    def retry_planning_run(
        self, workflow_instance_id: str, retried_at: str
    ) -> PlanningRunWorkflowInstance:
        workflow = self._require_workflow(workflow_instance_id)
        step = self._require_step(workflow_instance_id)
        self._assert_status(workflow.current_status, (WORKFLOW_STATUS_RETRY_PENDING,))

        next_attempt = workflow.current_attempt + 1
        handoff_request = PlanningEngineExecutionRequest(
            workflow_instance_id=workflow.workflow_instance_id,
            planning_context_key=workflow.planning_context_key,
            source_snapshot_id=workflow.source_snapshot_id,
            source_artifact_id=workflow.source_artifact_id,
            requested_by=workflow.requested_by,
            requested_at=retried_at,
            attempt_number=next_attempt,
        )
        try:
            receipt = self._planning_engine_gateway.submit_planning_run(handoff_request)
        except PlanningEngineGatewayError as error:
            retry_pending_workflow = replace(workflow, current_attempt=next_attempt)
            self._repository.save_workflow(retry_pending_workflow)
            return self._apply_failure_transition(
                workflow=retry_pending_workflow,
                step=step,
                occurred_at=retried_at,
                error_code=error.code,
                error_message=error.message,
                retryable=next_attempt < workflow.max_attempts,
            )

        updated_workflow = replace(
            workflow,
            current_status=WORKFLOW_STATUS_DISPATCHED,
            current_attempt=next_attempt,
            planning_engine_run_id=receipt.planning_run_id,
            last_transition_at=receipt.accepted_at,
        )
        updated_step = replace(
            step,
            status=STEP_STATUS_DISPATCHED,
            attempt_number=next_attempt,
            last_updated_at=receipt.accepted_at,
        )
        self._repository.save_workflow(updated_workflow)
        self._repository.save_step(updated_step)
        self._repository.append_transition(
            workflow_instance_id=workflow_instance_id,
            from_status=workflow.current_status,
            to_status=WORKFLOW_STATUS_DISPATCHED,
            occurred_at=receipt.accepted_at,
            reason="planning_engine_retry_dispatched",
        )
        return updated_workflow

    def get_planning_run_status(
        self,
        workflow_instance_id: Optional[str] = None,
        planning_context_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
    ) -> Optional[PlanningRunStatusView]:
        workflow = None
        if workflow_instance_id is not None:
            workflow = self._repository.get_workflow(workflow_instance_id)
        elif planning_context_key is not None and source_snapshot_id is not None:
            workflow = self._repository.get_latest_workflow_for_context_and_snapshot(
                planning_context_key,
                source_snapshot_id,
            )
        elif planning_context_key is not None:
            workflow = self._repository.get_latest_workflow_for_context(
                planning_context_key
            )
        elif source_snapshot_id is not None:
            workflow = self._repository.get_latest_workflow_for_snapshot(
                source_snapshot_id
            )
        else:
            workflow = self._repository.get_latest_workflow()

        if workflow is None:
            return None
        return PlanningRunStatusView(
            workflow_instance_id=workflow.workflow_instance_id,
            planning_context_key=workflow.planning_context_key,
            source_snapshot_id=workflow.source_snapshot_id,
            source_artifact_id=workflow.source_artifact_id,
            planning_engine_run_id=workflow.planning_engine_run_id,
            status=workflow.current_status,
            current_step=workflow.current_step,
            current_attempt=workflow.current_attempt,
            max_attempts=workflow.max_attempts,
            requested_by=workflow.requested_by,
            requested_at=workflow.requested_at,
            last_transition_at=workflow.last_transition_at,
            completed_at=workflow.completed_at,
            last_error_code=workflow.last_error_code,
            last_error_message=workflow.last_error_message,
        )

    def start_activation_workflow(
        self, trigger: ActivationWorkflowTrigger
    ) -> ActivationWorkflowStartResult:
        self._validate_activation_trigger(trigger)
        self._require_activation_gateway()

        existing = self._repository.get_latest_activation_workflow_for_activation(
            trigger.activation_id
        )
        if existing is not None:
            return ActivationWorkflowStartResult(
                workflow_instance=existing,
                reused_existing=True,
                handoff_request=None,
            )

        workflow_instance_id = self._stable_id(
            "activation-workflow",
            trigger.activation_id,
            trigger.requested_at,
            trigger.idempotency_key or "no-idempotency-key",
        )
        workflow = ActivationWorkflowInstance(
            workflow_instance_id=workflow_instance_id,
            workflow_type=ACTIVATION_WORKFLOW_TYPE,
            activation_command_id=trigger.activation_command_id,
            activation_id=trigger.activation_id,
            review_context_id=trigger.review_context_id,
            approved_plan_id=trigger.approved_plan_id,
            current_status=WORKFLOW_STATUS_QUEUED,
            current_step=ACTIVATION_RECOMPUTATION_STEP,
            current_attempt=1,
            max_attempts=trigger.max_attempts,
            requested_by=trigger.requested_by,
            requested_at=trigger.requested_at,
            idempotency_key=trigger.idempotency_key,
            last_transition_at=trigger.requested_at,
            completed_at=None,
            last_error_code=None,
            last_error_message=None,
        )
        recomputation_step = WorkflowStepInstance(
            workflow_instance_id=workflow.workflow_instance_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            status=STEP_STATUS_PENDING,
            attempt_number=1,
            last_updated_at=trigger.requested_at,
        )
        side_effect_step = WorkflowStepInstance(
            workflow_instance_id=workflow.workflow_instance_id,
            step_name=ACTIVATION_SIDE_EFFECTS_STEP,
            status=STEP_STATUS_PENDING,
            attempt_number=1,
            last_updated_at=trigger.requested_at,
        )
        self._repository.save_activation_workflow(workflow)
        self._repository.save_activation_step(recomputation_step)
        self._repository.save_activation_step(side_effect_step)
        self._repository.append_activation_transition(
            workflow_instance_id=workflow.workflow_instance_id,
            from_status=None,
            to_status=WORKFLOW_STATUS_QUEUED,
            occurred_at=trigger.requested_at,
            reason="activation_workflow_requested",
        )

        handoff_request = self._build_activation_step_request(
            workflow=workflow,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            requested_at=trigger.requested_at,
            attempt_number=workflow.current_attempt,
        )
        try:
            receipt = self._submit_activation_step(handoff_request)
        except ActivationExecutionGatewayError as error:
            failed_workflow = self._apply_activation_failure_transition(
                workflow=workflow,
                step=recomputation_step,
                occurred_at=trigger.requested_at,
                error_code=error.code,
                error_message=error.message,
                retryable=workflow.current_attempt < workflow.max_attempts,
                reason="activation_recomputation_failed",
            )
            return ActivationWorkflowStartResult(
                workflow_instance=failed_workflow,
                reused_existing=False,
                handoff_request=handoff_request,
            )

        dispatched_workflow = replace(
            workflow,
            current_status=WORKFLOW_STATUS_DISPATCHED,
            last_transition_at=receipt.accepted_at,
        )
        dispatched_step = replace(
            recomputation_step,
            status=STEP_STATUS_DISPATCHED,
            last_updated_at=receipt.accepted_at,
            handoff_id=receipt.handoff_id,
        )
        self._repository.save_activation_workflow(dispatched_workflow)
        self._repository.save_activation_step(dispatched_step)
        self._repository.append_activation_transition(
            workflow_instance_id=workflow.workflow_instance_id,
            from_status=WORKFLOW_STATUS_QUEUED,
            to_status=WORKFLOW_STATUS_DISPATCHED,
            occurred_at=receipt.accepted_at,
            reason="activation_recomputation_handoff_accepted",
        )
        return ActivationWorkflowStartResult(
            workflow_instance=dispatched_workflow,
            reused_existing=False,
            handoff_request=handoff_request,
        )

    def mark_activation_step_running(
        self,
        workflow_instance_id: str,
        step_name: str,
        occurred_at: str,
    ) -> ActivationWorkflowInstance:
        workflow = self._require_activation_workflow(workflow_instance_id)
        step = self._require_activation_step(workflow_instance_id, step_name)
        self._assert_current_activation_step(workflow, step_name)
        self._assert_status(workflow.current_status, (WORKFLOW_STATUS_DISPATCHED,))

        updated_workflow = replace(
            workflow,
            current_status=WORKFLOW_STATUS_RUNNING,
            last_transition_at=occurred_at,
        )
        updated_step = replace(
            step,
            status=STEP_STATUS_RUNNING,
            last_updated_at=occurred_at,
        )
        self._repository.save_activation_workflow(updated_workflow)
        self._repository.save_activation_step(updated_step)
        self._repository.append_activation_transition(
            workflow_instance_id=workflow_instance_id,
            from_status=workflow.current_status,
            to_status=WORKFLOW_STATUS_RUNNING,
            occurred_at=occurred_at,
            reason="%s_started" % step_name,
        )
        return updated_workflow

    def mark_activation_step_succeeded(
        self,
        workflow_instance_id: str,
        step_name: str,
        occurred_at: str,
    ) -> ActivationWorkflowInstance:
        workflow = self._require_activation_workflow(workflow_instance_id)
        step = self._require_activation_step(workflow_instance_id, step_name)
        self._assert_current_activation_step(workflow, step_name)
        self._assert_status(workflow.current_status, (WORKFLOW_STATUS_RUNNING,))

        updated_step = replace(
            step,
            status=STEP_STATUS_SUCCEEDED,
            last_updated_at=occurred_at,
        )
        self._repository.save_activation_step(updated_step)

        if step_name == ACTIVATION_RECOMPUTATION_STEP:
            next_step = self._require_activation_step(
                workflow_instance_id,
                ACTIVATION_SIDE_EFFECTS_STEP,
            )
            handoff_request = self._build_activation_step_request(
                workflow=workflow,
                step_name=ACTIVATION_SIDE_EFFECTS_STEP,
                requested_at=occurred_at,
                attempt_number=workflow.current_attempt,
            )
            try:
                receipt = self._submit_activation_step(handoff_request)
            except ActivationExecutionGatewayError as error:
                pending_workflow = replace(
                    workflow,
                    current_step=ACTIVATION_SIDE_EFFECTS_STEP,
                )
                self._repository.save_activation_workflow(pending_workflow)
                return self._apply_activation_failure_transition(
                    workflow=pending_workflow,
                    step=next_step,
                    occurred_at=occurred_at,
                    error_code=error.code,
                    error_message=error.message,
                    retryable=workflow.current_attempt < workflow.max_attempts,
                    reason="activation_side_effect_sequencing_failed",
                )

            dispatched_workflow = replace(
                workflow,
                current_status=WORKFLOW_STATUS_DISPATCHED,
                current_step=ACTIVATION_SIDE_EFFECTS_STEP,
                last_transition_at=receipt.accepted_at,
                last_error_code=None,
                last_error_message=None,
            )
            dispatched_next_step = replace(
                next_step,
                status=STEP_STATUS_DISPATCHED,
                attempt_number=workflow.current_attempt,
                last_updated_at=receipt.accepted_at,
                handoff_id=receipt.handoff_id,
            )
            self._repository.save_activation_workflow(dispatched_workflow)
            self._repository.save_activation_step(dispatched_next_step)
            self._repository.append_activation_transition(
                workflow_instance_id=workflow_instance_id,
                from_status=workflow.current_status,
                to_status=WORKFLOW_STATUS_DISPATCHED,
                occurred_at=receipt.accepted_at,
                reason="activation_side_effect_sequencing_handoff_accepted",
            )
            return dispatched_workflow

        updated_workflow = replace(
            workflow,
            current_status=WORKFLOW_STATUS_SUCCEEDED,
            last_transition_at=occurred_at,
            completed_at=occurred_at,
            last_error_code=None,
            last_error_message=None,
        )
        self._repository.save_activation_workflow(updated_workflow)
        self._repository.append_activation_transition(
            workflow_instance_id=workflow_instance_id,
            from_status=workflow.current_status,
            to_status=WORKFLOW_STATUS_SUCCEEDED,
            occurred_at=occurred_at,
            reason="%s_succeeded" % step_name,
        )
        return updated_workflow

    def mark_activation_step_failed(
        self,
        workflow_instance_id: str,
        step_name: str,
        occurred_at: str,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> ActivationWorkflowInstance:
        workflow = self._require_activation_workflow(workflow_instance_id)
        step = self._require_activation_step(workflow_instance_id, step_name)
        self._assert_current_activation_step(workflow, step_name)
        self._assert_status(
            workflow.current_status,
            (WORKFLOW_STATUS_DISPATCHED, WORKFLOW_STATUS_RUNNING),
        )
        return self._apply_activation_failure_transition(
            workflow=workflow,
            step=step,
            occurred_at=occurred_at,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable and workflow.current_attempt < workflow.max_attempts,
            reason="%s_failed" % step_name,
        )

    def retry_activation_workflow(
        self, workflow_instance_id: str, retried_at: str
    ) -> ActivationWorkflowInstance:
        self._require_activation_gateway()
        workflow = self._require_activation_workflow(workflow_instance_id)
        step = self._require_activation_step(
            workflow_instance_id,
            workflow.current_step,
        )
        self._assert_status(workflow.current_status, (WORKFLOW_STATUS_RETRY_PENDING,))

        next_attempt = workflow.current_attempt + 1
        handoff_request = self._build_activation_step_request(
            workflow=workflow,
            step_name=workflow.current_step,
            requested_at=retried_at,
            attempt_number=next_attempt,
        )
        try:
            receipt = self._submit_activation_step(handoff_request)
        except ActivationExecutionGatewayError as error:
            retry_pending_workflow = replace(workflow, current_attempt=next_attempt)
            self._repository.save_activation_workflow(retry_pending_workflow)
            return self._apply_activation_failure_transition(
                workflow=retry_pending_workflow,
                step=step,
                occurred_at=retried_at,
                error_code=error.code,
                error_message=error.message,
                retryable=next_attempt < workflow.max_attempts,
                reason="%s_failed" % workflow.current_step,
            )

        updated_workflow = replace(
            workflow,
            current_status=WORKFLOW_STATUS_DISPATCHED,
            current_attempt=next_attempt,
            last_transition_at=receipt.accepted_at,
            last_error_code=None,
            last_error_message=None,
        )
        updated_step = replace(
            step,
            status=STEP_STATUS_DISPATCHED,
            attempt_number=next_attempt,
            last_updated_at=receipt.accepted_at,
            handoff_id=receipt.handoff_id,
        )
        self._repository.save_activation_workflow(updated_workflow)
        self._repository.save_activation_step(updated_step)
        self._repository.append_activation_transition(
            workflow_instance_id=workflow_instance_id,
            from_status=workflow.current_status,
            to_status=WORKFLOW_STATUS_DISPATCHED,
            occurred_at=receipt.accepted_at,
            reason="%s_retry_dispatched" % workflow.current_step,
        )
        return updated_workflow

    def get_activation_workflow_status(
        self,
        workflow_instance_id: Optional[str] = None,
        review_context_id: Optional[str] = None,
        activation_id: Optional[str] = None,
    ) -> Optional[ActivationWorkflowStatusView]:
        workflow = None
        if workflow_instance_id is not None:
            workflow = self._repository.get_activation_workflow(workflow_instance_id)
        elif activation_id is not None:
            workflow = self._repository.get_latest_activation_workflow_for_activation(
                activation_id
            )
        elif review_context_id is not None:
            workflow = self._repository.get_latest_activation_workflow_for_review_context(
                review_context_id
            )
        else:
            workflow = self._repository.get_latest_activation_workflow()

        if workflow is None:
            return None
        return ActivationWorkflowStatusView(
            workflow_instance_id=workflow.workflow_instance_id,
            activation_command_id=workflow.activation_command_id,
            activation_id=workflow.activation_id,
            review_context_id=workflow.review_context_id,
            approved_plan_id=workflow.approved_plan_id,
            status=workflow.current_status,
            current_step=workflow.current_step,
            current_attempt=workflow.current_attempt,
            max_attempts=workflow.max_attempts,
            requested_by=workflow.requested_by,
            requested_at=workflow.requested_at,
            last_transition_at=workflow.last_transition_at,
            completed_at=workflow.completed_at,
            last_error_code=workflow.last_error_code,
            last_error_message=workflow.last_error_message,
            step_states=self._repository.list_activation_steps(
                workflow.workflow_instance_id
            ),
        )

    def list_workflow_transitions(self, workflow_instance_id: str):
        return self._repository.list_transitions(workflow_instance_id)

    def list_activation_workflow_transitions(self, workflow_instance_id: str):
        return self._repository.list_activation_transitions(workflow_instance_id)

    def _apply_failure_transition(
        self,
        workflow: PlanningRunWorkflowInstance,
        step: WorkflowStepInstance,
        occurred_at: str,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> PlanningRunWorkflowInstance:
        next_status = (
            WORKFLOW_STATUS_RETRY_PENDING if retryable else WORKFLOW_STATUS_FAILED
        )
        next_step_status = STEP_STATUS_RETRY_PENDING if retryable else STEP_STATUS_FAILED
        completed_at = None if retryable else occurred_at
        updated_workflow = replace(
            workflow,
            current_status=next_status,
            last_transition_at=occurred_at,
            completed_at=completed_at,
            last_error_code=error_code,
            last_error_message=error_message,
        )
        updated_step = replace(
            step,
            status=next_step_status,
            last_updated_at=occurred_at,
        )
        self._repository.save_workflow(updated_workflow)
        self._repository.save_step(updated_step)
        self._repository.append_transition(
            workflow_instance_id=workflow.workflow_instance_id,
            from_status=workflow.current_status,
            to_status=next_status,
            occurred_at=occurred_at,
            reason="planning_engine_execution_failed",
        )
        return updated_workflow

    def _apply_activation_failure_transition(
        self,
        workflow: ActivationWorkflowInstance,
        step: WorkflowStepInstance,
        occurred_at: str,
        error_code: str,
        error_message: str,
        retryable: bool,
        reason: str,
    ) -> ActivationWorkflowInstance:
        next_status = (
            WORKFLOW_STATUS_RETRY_PENDING if retryable else WORKFLOW_STATUS_FAILED
        )
        next_step_status = STEP_STATUS_RETRY_PENDING if retryable else STEP_STATUS_FAILED
        completed_at = None if retryable else occurred_at
        updated_workflow = replace(
            workflow,
            current_status=next_status,
            last_transition_at=occurred_at,
            completed_at=completed_at,
            last_error_code=error_code,
            last_error_message=error_message,
        )
        updated_step = replace(
            step,
            status=next_step_status,
            last_updated_at=occurred_at,
        )
        self._repository.save_activation_workflow(updated_workflow)
        self._repository.save_activation_step(updated_step)
        self._repository.append_activation_transition(
            workflow_instance_id=workflow.workflow_instance_id,
            from_status=workflow.current_status,
            to_status=next_status,
            occurred_at=occurred_at,
            reason=reason,
        )
        return updated_workflow

    def _validate_trigger(self, trigger: PlanningRunTrigger) -> None:
        if trigger.max_attempts < 1:
            raise PlanningRunAdmissionError(
                "invalid_max_attempts",
                "max_attempts must be at least 1.",
            )
        if not trigger.planning_context_key:
            raise PlanningRunAdmissionError(
                "missing_planning_context_key",
                "planning_context_key is required for idempotent planning-run orchestration.",
            )

    def _validate_activation_trigger(self, trigger: ActivationWorkflowTrigger) -> None:
        if trigger.max_attempts < 1:
            raise ActivationWorkflowAdmissionError(
                "invalid_max_attempts",
                "max_attempts must be at least 1.",
            )
        if not trigger.activation_command_id:
            raise ActivationWorkflowAdmissionError(
                "missing_activation_command_id",
                "activation_command_id is required for activation workflow orchestration.",
            )
        if not trigger.activation_id:
            raise ActivationWorkflowAdmissionError(
                "missing_activation_id",
                "activation_id is required for activation workflow orchestration.",
            )
        if not trigger.review_context_id:
            raise ActivationWorkflowAdmissionError(
                "missing_review_context_id",
                "review_context_id is required for activation workflow orchestration.",
            )
        if not trigger.approved_plan_id:
            raise ActivationWorkflowAdmissionError(
                "missing_approved_plan_id",
                "approved_plan_id is required for activation workflow orchestration.",
            )

    def _require_workflow(self, workflow_instance_id: str) -> PlanningRunWorkflowInstance:
        workflow = self._repository.get_workflow(workflow_instance_id)
        if workflow is None:
            raise WorkflowTransitionError(
                "Unknown workflow_instance_id: %s" % workflow_instance_id
            )
        return workflow

    def _require_step(self, workflow_instance_id: str) -> WorkflowStepInstance:
        step = self._repository.get_step(workflow_instance_id)
        if step is None:
            raise WorkflowTransitionError(
                "Missing workflow step for workflow_instance_id: %s"
                % workflow_instance_id
            )
        return step

    def _require_activation_gateway(self) -> None:
        if self._activation_execution_gateway is None:
            raise ActivationWorkflowAdmissionError(
                "missing_activation_execution_gateway",
                "An activation execution gateway is required before starting activation workflow execution.",
            )

    def _require_activation_workflow(
        self, workflow_instance_id: str
    ) -> ActivationWorkflowInstance:
        workflow = self._repository.get_activation_workflow(workflow_instance_id)
        if workflow is None:
            raise WorkflowTransitionError(
                "Unknown activation workflow_instance_id: %s" % workflow_instance_id
            )
        return workflow

    def _require_activation_step(
        self, workflow_instance_id: str, step_name: str
    ) -> WorkflowStepInstance:
        step = self._repository.get_activation_step(workflow_instance_id, step_name)
        if step is None:
            raise WorkflowTransitionError(
                "Missing activation workflow step %s for workflow_instance_id: %s"
                % (step_name, workflow_instance_id)
            )
        return step

    def _assert_current_activation_step(
        self, workflow: ActivationWorkflowInstance, step_name: str
    ) -> None:
        if workflow.current_step != step_name:
            raise WorkflowTransitionError(
                "Invalid activation step transition for %s. Current step is %s"
                % (step_name, workflow.current_step)
            )

    def _build_activation_step_request(
        self,
        workflow: ActivationWorkflowInstance,
        step_name: str,
        requested_at: str,
        attempt_number: int,
    ) -> ActivationExecutionStepRequest:
        return ActivationExecutionStepRequest(
            workflow_instance_id=workflow.workflow_instance_id,
            activation_command_id=workflow.activation_command_id,
            activation_id=workflow.activation_id,
            review_context_id=workflow.review_context_id,
            approved_plan_id=workflow.approved_plan_id,
            step_name=step_name,
            requested_by=workflow.requested_by,
            requested_at=requested_at,
            attempt_number=attempt_number,
        )

    def _submit_activation_step(self, request: ActivationExecutionStepRequest):
        assert self._activation_execution_gateway is not None
        return self._activation_execution_gateway.submit_step(request)

    def _assert_status(self, current_status: str, allowed_statuses) -> None:
        if current_status not in allowed_statuses:
            raise WorkflowTransitionError(
                "Invalid transition from status %s. Allowed: %s"
                % (current_status, ", ".join(allowed_statuses))
            )

    def _stable_id(self, prefix: str, *parts: str) -> str:
        joined = "::".join(parts)
        digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
        return "%s_%s" % (prefix, digest)
