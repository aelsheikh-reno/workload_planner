"""Workflow Orchestrator contracts for async workflow/job execution state."""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


PLANNING_RUN_WORKFLOW_TYPE = "planning_run"
PLANNING_ENGINE_EXECUTION_STEP = "planning_engine_execution"
IMPORT_SYNC_WORKFLOW_TYPE = "import_sync"
INTEGRATION_IMPORT_SYNC_STEP = "integration_import_sync"
ACTIVATION_WORKFLOW_TYPE = "activation_post_commit"
ACTIVATION_RECOMPUTATION_STEP = "activation_recomputation"
ACTIVATION_SIDE_EFFECTS_STEP = "activation_side_effect_sequencing"

WORKFLOW_STATUS_QUEUED = "queued"
WORKFLOW_STATUS_DISPATCHED = "dispatched"
WORKFLOW_STATUS_RUNNING = "running"
WORKFLOW_STATUS_RETRY_PENDING = "retry_pending"
WORKFLOW_STATUS_FAILED = "failed"
WORKFLOW_STATUS_SUCCEEDED = "succeeded"

ACTIVE_WORKFLOW_STATUSES = (
    WORKFLOW_STATUS_QUEUED,
    WORKFLOW_STATUS_DISPATCHED,
    WORKFLOW_STATUS_RUNNING,
    WORKFLOW_STATUS_RETRY_PENDING,
)

TERMINAL_WORKFLOW_STATUSES = (
    WORKFLOW_STATUS_FAILED,
    WORKFLOW_STATUS_SUCCEEDED,
)

STEP_STATUS_PENDING = "pending"
STEP_STATUS_DISPATCHED = "dispatched"
STEP_STATUS_RUNNING = "running"
STEP_STATUS_RETRY_PENDING = "retry_pending"
STEP_STATUS_FAILED = "failed"
STEP_STATUS_SUCCEEDED = "succeeded"


@dataclass(frozen=True)
class PlanningRunTrigger:
    planning_context_key: str
    source_snapshot_id: str
    requested_by: str
    requested_at: str
    idempotency_key: Optional[str] = None
    max_attempts: int = 2

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ImportSyncTrigger:
    raw_payload: Dict[str, object]
    requested_by: str
    requested_at: str
    idempotency_key: Optional[str] = None
    max_attempts: int = 1

    def to_dict(self) -> Dict[str, object]:
        return {
            "raw_payload": dict(self.raw_payload),
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "idempotency_key": self.idempotency_key,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True)
class ImportSyncExecutionRequest:
    workflow_instance_id: str
    source_system: Optional[str]
    raw_payload: Dict[str, object]
    requested_by: str
    requested_at: str
    attempt_number: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "workflow_instance_id": self.workflow_instance_id,
            "source_system": self.source_system,
            "raw_payload": dict(self.raw_payload),
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "attempt_number": self.attempt_number,
        }


@dataclass(frozen=True)
class ImportSyncExecutionReceipt:
    handoff_id: str
    accepted_at: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ImportSyncWorkflowInstance:
    workflow_instance_id: str
    workflow_type: str
    source_system: Optional[str]
    source_artifact_id: Optional[str]
    source_snapshot_id: Optional[str]
    current_status: str
    current_step: str
    current_attempt: int
    max_attempts: int
    requested_by: str
    requested_at: str
    idempotency_key: Optional[str]
    last_transition_at: str
    completed_at: Optional[str]
    last_error_code: Optional[str]
    last_error_message: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ImportSyncStartResult:
    workflow_instance: ImportSyncWorkflowInstance
    reused_existing: bool
    handoff_request: Optional[ImportSyncExecutionRequest]
    source_snapshot_id: Optional[str]
    source_artifact_id: Optional[str]
    source_readiness: Optional[Dict[str, object]]

    def to_dict(self) -> Dict[str, object]:
        return {
            "workflow_instance": self.workflow_instance.to_dict(),
            "reused_existing": self.reused_existing,
            "handoff_request": None
            if self.handoff_request is None
            else self.handoff_request.to_dict(),
            "source_snapshot_id": self.source_snapshot_id,
            "source_artifact_id": self.source_artifact_id,
            "source_readiness": None
            if self.source_readiness is None
            else dict(self.source_readiness),
        }


@dataclass(frozen=True)
class PlanningEngineExecutionRequest:
    workflow_instance_id: str
    planning_context_key: str
    source_snapshot_id: str
    source_artifact_id: str
    requested_by: str
    requested_at: str
    attempt_number: int

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlanningEngineExecutionReceipt:
    planning_run_id: str
    accepted_at: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlanningRunWorkflowInstance:
    workflow_instance_id: str
    workflow_type: str
    planning_context_key: str
    source_snapshot_id: str
    source_artifact_id: str
    current_status: str
    current_step: str
    current_attempt: int
    max_attempts: int
    requested_by: str
    requested_at: str
    idempotency_key: Optional[str]
    planning_engine_run_id: Optional[str]
    last_transition_at: str
    completed_at: Optional[str]
    last_error_code: Optional[str]
    last_error_message: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowStepInstance:
    workflow_instance_id: str
    step_name: str
    status: str
    attempt_number: int
    last_updated_at: str
    handoff_id: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowTransitionRecord:
    workflow_instance_id: str
    transition_index: int
    from_status: Optional[str]
    to_status: str
    occurred_at: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlanningRunStatusView:
    workflow_instance_id: str
    planning_context_key: str
    source_snapshot_id: str
    source_artifact_id: str
    planning_engine_run_id: Optional[str]
    status: str
    current_step: str
    current_attempt: int
    max_attempts: int
    requested_by: str
    requested_at: str
    last_transition_at: str
    completed_at: Optional[str]
    last_error_code: Optional[str]
    last_error_message: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlanningRunStartResult:
    workflow_instance: PlanningRunWorkflowInstance
    reused_existing: bool
    handoff_request: Optional[PlanningEngineExecutionRequest]

    def to_dict(self) -> Dict[str, object]:
        return {
            "workflow_instance": self.workflow_instance.to_dict(),
            "reused_existing": self.reused_existing,
            "handoff_request": None
            if self.handoff_request is None
            else self.handoff_request.to_dict(),
        }


@dataclass(frozen=True)
class ActivationWriteBackTargetReference:
    target_id: str
    delta_id: str
    entity_type: str
    entity_external_id: str
    entity_name: str
    project_external_id: Optional[str]
    write_back_action: str
    write_back_fields: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "target_id": self.target_id,
            "delta_id": self.delta_id,
            "entity_type": self.entity_type,
            "entity_external_id": self.entity_external_id,
            "entity_name": self.entity_name,
            "project_external_id": self.project_external_id,
            "write_back_action": self.write_back_action,
            "write_back_fields": list(self.write_back_fields),
        }


@dataclass(frozen=True)
class ActivationWorkflowTrigger:
    activation_command_id: str
    activation_id: str
    review_context_id: str
    approved_plan_id: str
    source_snapshot_id: Optional[str]
    write_back_targets: List[ActivationWriteBackTargetReference]
    requested_by: str
    requested_at: str
    idempotency_key: Optional[str] = None
    max_attempts: int = 2

    def to_dict(self) -> Dict[str, object]:
        return {
            "activation_command_id": self.activation_command_id,
            "activation_id": self.activation_id,
            "review_context_id": self.review_context_id,
            "approved_plan_id": self.approved_plan_id,
            "source_snapshot_id": self.source_snapshot_id,
            "write_back_targets": [
                target.to_dict() for target in self.write_back_targets
            ],
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "idempotency_key": self.idempotency_key,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True)
class ActivationExecutionStepRequest:
    workflow_instance_id: str
    activation_command_id: str
    activation_id: str
    review_context_id: str
    approved_plan_id: str
    source_snapshot_id: Optional[str]
    write_back_targets: List[ActivationWriteBackTargetReference]
    step_name: str
    requested_by: str
    requested_at: str
    attempt_number: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "workflow_instance_id": self.workflow_instance_id,
            "activation_command_id": self.activation_command_id,
            "activation_id": self.activation_id,
            "review_context_id": self.review_context_id,
            "approved_plan_id": self.approved_plan_id,
            "source_snapshot_id": self.source_snapshot_id,
            "write_back_targets": [
                target.to_dict() for target in self.write_back_targets
            ],
            "step_name": self.step_name,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "attempt_number": self.attempt_number,
        }


@dataclass(frozen=True)
class ActivationExecutionStepReceipt:
    step_name: str
    handoff_id: str
    accepted_at: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ActivationWorkflowInstance:
    workflow_instance_id: str
    workflow_type: str
    activation_command_id: str
    activation_id: str
    review_context_id: str
    approved_plan_id: str
    source_snapshot_id: Optional[str]
    write_back_targets: List[ActivationWriteBackTargetReference]
    current_status: str
    current_step: str
    current_attempt: int
    max_attempts: int
    requested_by: str
    requested_at: str
    idempotency_key: Optional[str]
    last_transition_at: str
    completed_at: Optional[str]
    last_error_code: Optional[str]
    last_error_message: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ActivationWorkflowStatusView:
    workflow_instance_id: str
    activation_command_id: str
    activation_id: str
    review_context_id: str
    approved_plan_id: str
    status: str
    current_step: str
    current_attempt: int
    max_attempts: int
    requested_by: str
    requested_at: str
    last_transition_at: str
    completed_at: Optional[str]
    last_error_code: Optional[str]
    last_error_message: Optional[str]
    step_states: List[WorkflowStepInstance]

    def to_dict(self) -> Dict[str, object]:
        return {
            "workflow_instance_id": self.workflow_instance_id,
            "activation_command_id": self.activation_command_id,
            "activation_id": self.activation_id,
            "review_context_id": self.review_context_id,
            "approved_plan_id": self.approved_plan_id,
            "status": self.status,
            "current_step": self.current_step,
            "current_attempt": self.current_attempt,
            "max_attempts": self.max_attempts,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "last_transition_at": self.last_transition_at,
            "completed_at": self.completed_at,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "step_states": [step.to_dict() for step in self.step_states],
        }


@dataclass(frozen=True)
class ActivationWorkflowStartResult:
    workflow_instance: ActivationWorkflowInstance
    reused_existing: bool
    handoff_request: Optional[ActivationExecutionStepRequest]

    def to_dict(self) -> Dict[str, object]:
        return {
            "workflow_instance": self.workflow_instance.to_dict(),
            "reused_existing": self.reused_existing,
            "handoff_request": None
            if self.handoff_request is None
            else self.handoff_request.to_dict(),
        }
