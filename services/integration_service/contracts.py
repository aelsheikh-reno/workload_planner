"""Explicit Integration Service contracts for normalized source intake and write-back."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


BOUND_WRITE_BACK_TRIGGER_STEP = "activation_side_effect_sequencing"
BOUND_WRITE_BACK_ACTION_UPDATE_TASK_FIELDS = "update_task_fields"
BOUND_WRITE_BACK_ACTION_UPDATE_PROJECT_FIELDS = "update_project_fields"

WRITE_BACK_ITEM_STATUS_SUCCEEDED = "succeeded"
WRITE_BACK_ITEM_STATUS_FAILED = "failed"

WRITE_BACK_STATUS_SUCCEEDED = "succeeded"
WRITE_BACK_STATUS_PARTIAL = "partial"
WRITE_BACK_STATUS_FAILED = "failed"

ALLOWED_WRITE_BACK_FIELDS = {
    "task_start_date",
    "task_due_date",
    "milestone_date",
    "project_finish_date",
    "assigned_resource_external_ids",
}


@dataclass(frozen=True)
class SourceArtifact:
    artifact_id: str
    external_artifact_id: str
    source_system: str
    captured_at: str
    payload_digest: str
    raw_payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceSnapshot:
    snapshot_id: str
    artifact_id: str
    source_system: str
    captured_at: str
    project_count: int
    task_count: int
    dependency_count: int
    assignment_count: int
    issue_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceMapping:
    mapping_id: str
    external_id: str
    scope_external_id: Optional[str]
    internal_id: str
    source_system: str
    display_name: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedTaskRecord:
    task_id: str
    source_snapshot_id: str
    source_system: str
    external_task_id: str
    project_id: str
    project_external_id: str
    parent_task_id: Optional[str]
    name: str
    hierarchy_path: List[str]
    hierarchy_depth: int
    effort_hours: Optional[float]
    start_date: Optional[str]
    due_date: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedDependencyRecord:
    dependency_id: str
    source_snapshot_id: str
    source_system: str
    predecessor_task_id: str
    successor_task_id: str
    predecessor_external_task_id: str
    successor_external_task_id: str
    dependency_type: str = "FS"  # FS | FF | SS | SF

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedResourceAssignmentRecord:
    assignment_id: str
    source_snapshot_id: str
    source_system: str
    task_id: str
    task_external_id: str
    resource_id: str
    resource_external_id: str
    allocation_percent: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedResourceRecord:
    resource_id: str
    source_snapshot_id: str
    source_system: str
    external_resource_id: str
    display_name: Optional[str]
    calendar_id: str
    calendar_name: Optional[str]
    default_daily_capacity_hours: Optional[float]
    working_days: List[str]
    availability_ratio: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedResourceExceptionRecord:
    exception_id: str
    source_snapshot_id: str
    source_system: str
    resource_id: str
    resource_external_id: str
    date: str
    available_capacity_hours: float
    reason: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceSetupIssueFact:
    issue_id: str
    source_snapshot_id: str
    source_system: str
    severity: str
    code: str
    message: str
    entity_type: str
    entity_external_id: Optional[str]
    field: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceReadiness:
    state: str
    runnable: bool
    blocking_issue_count: int
    advisory_issue_count: int
    total_issue_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BoundedWriteBackTarget:
    target_id: str
    delta_id: str
    entity_type: str
    entity_external_id: str
    entity_name: str
    project_external_id: Optional[str]
    write_back_action: str
    write_back_fields: List[str]

    def to_dict(self) -> Dict[str, Any]:
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
class BoundedWriteBackRequest:
    request_id: str
    activation_command_id: str
    activation_id: str
    review_context_id: str
    approved_plan_id: str
    source_snapshot_id: str
    orchestrator_workflow_instance_id: str
    orchestrator_step_name: str
    requested_by: str
    requested_at: str
    attempt_number: int
    targets: List[BoundedWriteBackTarget]
    idempotency_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "activation_command_id": self.activation_command_id,
            "activation_id": self.activation_id,
            "review_context_id": self.review_context_id,
            "approved_plan_id": self.approved_plan_id,
            "source_snapshot_id": self.source_snapshot_id,
            "orchestrator_workflow_instance_id": self.orchestrator_workflow_instance_id,
            "orchestrator_step_name": self.orchestrator_step_name,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "attempt_number": self.attempt_number,
            "targets": [target.to_dict() for target in self.targets],
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True)
class BoundedWriteBackItemResult:
    target_id: str
    delta_id: str
    entity_type: str
    entity_external_id: str
    status: str
    applied_fields: List[str]
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "delta_id": self.delta_id,
            "entity_type": self.entity_type,
            "entity_external_id": self.entity_external_id,
            "status": self.status,
            "applied_fields": list(self.applied_fields),
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class BoundedWriteBackExecutionReceipt:
    completed_at: str
    item_results: List[BoundedWriteBackItemResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "completed_at": self.completed_at,
            "item_results": [item_result.to_dict() for item_result in self.item_results],
        }


@dataclass(frozen=True)
class BoundedWriteBackResult:
    request_id: str
    activation_command_id: str
    activation_id: str
    review_context_id: str
    approved_plan_id: str
    source_snapshot_id: str
    source_system: str
    orchestrator_workflow_instance_id: str
    orchestrator_step_name: str
    attempt_number: int
    status: str
    total_target_count: int
    succeeded_target_count: int
    failed_target_count: int
    requested_by: str
    requested_at: str
    completed_at: str
    reused_existing: bool
    item_results: List[BoundedWriteBackItemResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "activation_command_id": self.activation_command_id,
            "activation_id": self.activation_id,
            "review_context_id": self.review_context_id,
            "approved_plan_id": self.approved_plan_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_system": self.source_system,
            "orchestrator_workflow_instance_id": self.orchestrator_workflow_instance_id,
            "orchestrator_step_name": self.orchestrator_step_name,
            "attempt_number": self.attempt_number,
            "status": self.status,
            "total_target_count": self.total_target_count,
            "succeeded_target_count": self.succeeded_target_count,
            "failed_target_count": self.failed_target_count,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "reused_existing": self.reused_existing,
            "item_results": [item_result.to_dict() for item_result in self.item_results],
        }


@dataclass(frozen=True)
class NormalizedSourceBundle:
    artifact: SourceArtifact
    snapshot: SourceSnapshot
    project_mappings: List[SourceMapping]
    task_mappings: List[SourceMapping]
    resource_mappings: List[SourceMapping]
    tasks: List[NormalizedTaskRecord]
    dependencies: List[NormalizedDependencyRecord]
    resource_assignments: List[NormalizedResourceAssignmentRecord]
    resources: List[NormalizedResourceRecord]
    resource_exceptions: List[NormalizedResourceExceptionRecord]
    issue_facts: List[SourceSetupIssueFact]
    source_readiness: SourceReadiness

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "snapshot": self.snapshot.to_dict(),
            "project_mappings": [mapping.to_dict() for mapping in self.project_mappings],
            "task_mappings": [mapping.to_dict() for mapping in self.task_mappings],
            "resource_mappings": [
                mapping.to_dict() for mapping in self.resource_mappings
            ],
            "tasks": [task.to_dict() for task in self.tasks],
            "dependencies": [
                dependency.to_dict() for dependency in self.dependencies
            ],
            "resource_assignments": [
                assignment.to_dict() for assignment in self.resource_assignments
            ],
            "resources": [resource.to_dict() for resource in self.resources],
            "resource_exceptions": [
                exception.to_dict() for exception in self.resource_exceptions
            ],
            "issue_facts": [issue.to_dict() for issue in self.issue_facts],
            "source_readiness": self.source_readiness.to_dict(),
        }
