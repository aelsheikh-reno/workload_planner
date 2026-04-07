"""Review & Approval contracts for delta review and issue-fact emission."""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


ISSUE_FACT_SCOPE_REVIEW_CONTEXT = "review_context"
ISSUE_FACT_SCOPE_ACTIVATION = "activation"

ISSUE_FACT_TYPE_DEPENDENCY_SAFE_BLOCKER = "dependency_safe_blocker"
ISSUE_FACT_TYPE_CONNECTED_SET_REQUIRED = "connected_set_required"
ISSUE_FACT_TYPE_ACTIVATION_BLOCKER = "activation_blocker"
ISSUE_FACT_TYPE_ACTIVATION_OUTCOME = "activation_outcome"

ISSUE_FACT_SEVERITY_BLOCKING = "blocking"
ISSUE_FACT_SEVERITY_INFO = "info"

ACTIVATION_STATUS_NOT_REQUESTED = "not_requested"
ACTIVATION_STATUS_BLOCKED = "blocked"
ACTIVATION_STATUS_ACTIVATED = "activated"

ACTIVATION_WORKFLOW_STATE_NOT_STARTED = "not_started"

DELTA_SCOPE_ATTRIBUTE_TASK_START_DATE = "task_start_date"
DELTA_SCOPE_ATTRIBUTE_TASK_DUE_DATE = "task_due_date"
DELTA_SCOPE_ATTRIBUTE_MILESTONE_DATE = "milestone_date"
DELTA_SCOPE_ATTRIBUTE_PROJECT_FINISH_DATE = "project_finish_date"
DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS = (
    "assigned_resource_external_ids"
)

REVIEW_DELTA_ENTITY_TYPE_TASK = "task"
REVIEW_DELTA_ENTITY_TYPE_MILESTONE = "milestone"
REVIEW_DELTA_ENTITY_TYPE_PROJECT = "project"

REVIEW_COMPARISON_CONTEXT_DRAFT_VS_APPROVED = "draft_vs_current_approved_plan"

ACCEPTANCE_SELECTION_SCOPE_DELTA_ITEM = "delta_item"
ACCEPTANCE_SELECTION_SCOPE_CONNECTED_CHANGE_SET = "connected_change_set"

ACCEPTANCE_SELECTION_ACTION_SELECT = "select"
ACCEPTANCE_SELECTION_ACTION_DESELECT = "deselect"

ACCEPTANCE_SELECTION_STATUS_APPLIED = "applied"
ACCEPTANCE_SELECTION_STATUS_BLOCKED = "blocked"


@dataclass(frozen=True)
class RecommendationOriginReference:
    recommendation_id: str
    origin_screen_id: str
    task_external_id: str
    requires_review_handoff: bool
    project_external_id: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ApprovedPlanProjectRecord:
    project_external_id: str
    project_name: str
    finish_date: Optional[str]
    project_id: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ApprovedPlanTaskRecord:
    task_external_id: str
    task_name: str
    project_external_id: str
    approved_start_date: Optional[str]
    approved_due_date: Optional[str]
    assigned_resource_external_ids: List[str]
    item_type: str = REVIEW_DELTA_ENTITY_TYPE_TASK
    task_id: Optional[str] = None
    project_id: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "task_external_id": self.task_external_id,
            "task_name": self.task_name,
            "project_external_id": self.project_external_id,
            "approved_start_date": self.approved_start_date,
            "approved_due_date": self.approved_due_date,
            "assigned_resource_external_ids": sorted(
                self.assigned_resource_external_ids
            ),
            "item_type": self.item_type,
            "task_id": self.task_id,
            "project_id": self.project_id,
        }


@dataclass(frozen=True)
class ApprovedOperatingPlanSnapshot:
    approved_plan_id: str
    tasks: List[ApprovedPlanTaskRecord]
    projects: List[ApprovedPlanProjectRecord]

    def to_dict(self) -> Dict[str, object]:
        return {
            "approved_plan_id": self.approved_plan_id,
            "tasks": [task.to_dict() for task in self.tasks],
            "projects": [project.to_dict() for project in self.projects],
        }


@dataclass(frozen=True)
class ReviewableDeltaAttributeChange:
    attribute_name: str
    before_value: object
    after_value: object

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ConnectedChangeSet:
    connected_set_id: str
    review_context_id: str
    member_delta_ids: List[str]
    member_entity_external_ids: List[str]
    minimal_for_dependency_safety: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {
            "connected_set_id": self.connected_set_id,
            "review_context_id": self.review_context_id,
            "member_delta_ids": sorted(self.member_delta_ids),
            "member_entity_external_ids": sorted(self.member_entity_external_ids),
            "minimal_for_dependency_safety": self.minimal_for_dependency_safety,
        }


@dataclass(frozen=True)
class ConnectedChangeSetResolution:
    resolution_id: str
    review_context_id: str
    requested_delta_id: str
    isolated_acceptance_safe: bool
    blocking_reason_code: Optional[str]
    blocking_reason_message: Optional[str]
    connected_change_set: Optional[ConnectedChangeSet]

    def to_dict(self) -> Dict[str, object]:
        return {
            "resolution_id": self.resolution_id,
            "review_context_id": self.review_context_id,
            "requested_delta_id": self.requested_delta_id,
            "isolated_acceptance_safe": self.isolated_acceptance_safe,
            "blocking_reason_code": self.blocking_reason_code,
            "blocking_reason_message": self.blocking_reason_message,
            "connected_change_set": (
                None
                if self.connected_change_set is None
                else self.connected_change_set.to_dict()
            ),
        }


@dataclass(frozen=True)
class ReviewableDeltaItem:
    delta_id: str
    entity_type: str
    entity_id: str
    entity_external_id: str
    entity_name: str
    dependency_delta_ids: List[str] = field(default_factory=list)
    connected_set_id: Optional[str] = None
    selected_for_acceptance: bool = False
    task_id: Optional[str] = None
    task_external_id: Optional[str] = None
    task_name: Optional[str] = None
    project_id: Optional[str] = None
    project_external_id: Optional[str] = None
    delta_scope_attributes: List[str] = field(default_factory=list)
    attribute_changes: List[ReviewableDeltaAttributeChange] = field(default_factory=list)
    recommendation_origin_refs: List[RecommendationOriginReference] = field(
        default_factory=list
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "delta_id": self.delta_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "entity_external_id": self.entity_external_id,
            "entity_name": self.entity_name,
            "dependency_delta_ids": sorted(self.dependency_delta_ids),
            "connected_set_id": self.connected_set_id,
            "selected_for_acceptance": self.selected_for_acceptance,
            "task_id": self.task_id,
            "task_external_id": self.task_external_id,
            "task_name": self.task_name,
            "project_id": self.project_id,
            "project_external_id": self.project_external_id,
            "delta_scope_attributes": list(self.delta_scope_attributes),
            "attribute_changes": [
                attribute_change.to_dict()
                for attribute_change in self.attribute_changes
            ],
            "recommendation_origin_refs": [
                recommendation_ref.to_dict()
                for recommendation_ref in self.recommendation_origin_refs
            ],
        }


@dataclass(frozen=True)
class ReviewContextState:
    review_context_id: str
    planning_run_id: str
    source_snapshot_id: str
    approved_plan_id: str
    draft_schedule_id: Optional[str] = None
    comparison_context: str = REVIEW_COMPARISON_CONTEXT_DRAFT_VS_APPROVED
    delta_set_id: Optional[str] = None
    delta_items: List[ReviewableDeltaItem] = field(default_factory=list)
    connected_change_sets: List[ConnectedChangeSet] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "review_context_id": self.review_context_id,
            "planning_run_id": self.planning_run_id,
            "source_snapshot_id": self.source_snapshot_id,
            "approved_plan_id": self.approved_plan_id,
            "draft_schedule_id": self.draft_schedule_id,
            "comparison_context": self.comparison_context,
            "delta_set_id": self.delta_set_id,
            "delta_items": [delta.to_dict() for delta in self.delta_items],
            "connected_change_sets": [
                connected_set.to_dict()
                for connected_set in self.connected_change_sets
            ],
        }


@dataclass(frozen=True)
class AcceptanceSelectionResult:
    command_id: str
    review_context_id: str
    selection_scope: str
    requested_delta_id: str
    connected_set_id: Optional[str]
    action: str
    status: str
    blocked_reason_code: Optional[str]
    blocked_reason_message: Optional[str]
    review_context: ReviewContextState
    connected_set_resolution: Optional[ConnectedChangeSetResolution]

    def to_dict(self) -> Dict[str, object]:
        return {
            "command_id": self.command_id,
            "review_context_id": self.review_context_id,
            "selection_scope": self.selection_scope,
            "requested_delta_id": self.requested_delta_id,
            "connected_set_id": self.connected_set_id,
            "action": self.action,
            "status": self.status,
            "blocked_reason_code": self.blocked_reason_code,
            "blocked_reason_message": self.blocked_reason_message,
            "review_context": self.review_context.to_dict(),
            "connected_set_resolution": (
                None
                if self.connected_set_resolution is None
                else self.connected_set_resolution.to_dict()
            ),
        }


@dataclass(frozen=True)
class ActivationBusinessRuleBlocker:
    rule_id: str
    code: str
    message: str
    entity_type: str
    entity_id: str
    entity_external_id: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ActivationOutcome:
    code: str
    message: str
    activated_delta_ids: List[str]
    resulting_approved_plan_id: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ActivationState:
    activation_id: str
    status: str
    business_rule_blockers: List[ActivationBusinessRuleBlocker]
    outcome: Optional[ActivationOutcome]
    review_context_id: Optional[str] = None
    approved_plan_id_before: Optional[str] = None
    approved_plan_id_after: Optional[str] = None
    requested_by: Optional[str] = None
    requested_at: Optional[str] = None
    selected_delta_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "activation_id": self.activation_id,
            "status": self.status,
            "business_rule_blockers": [
                blocker.to_dict() for blocker in self.business_rule_blockers
            ],
            "outcome": None if self.outcome is None else self.outcome.to_dict(),
            "review_context_id": self.review_context_id,
            "approved_plan_id_before": self.approved_plan_id_before,
            "approved_plan_id_after": self.approved_plan_id_after,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
            "selected_delta_ids": list(self.selected_delta_ids),
        }


@dataclass(frozen=True)
class ActivationWriteBackTarget:
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
class ActivationDownstreamHandoff:
    owner_service: str
    handoff_required: bool
    workflow_state: str
    workflow_instance_id: Optional[str] = None
    source_snapshot_id: Optional[str] = None
    write_back_targets: List[ActivationWriteBackTarget] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "owner_service": self.owner_service,
            "handoff_required": self.handoff_required,
            "workflow_state": self.workflow_state,
            "workflow_instance_id": self.workflow_instance_id,
            "source_snapshot_id": self.source_snapshot_id,
            "write_back_targets": [
                target.to_dict() for target in self.write_back_targets
            ],
        }


@dataclass(frozen=True)
class ActivationCommandResult:
    command_id: str
    review_context_id: str
    activation_state: ActivationState
    resulting_approved_plan_snapshot: Optional[ApprovedOperatingPlanSnapshot]
    reused_existing: bool
    downstream_handoff: ActivationDownstreamHandoff

    def to_dict(self) -> Dict[str, object]:
        return {
            "command_id": self.command_id,
            "review_context_id": self.review_context_id,
            "activation_state": self.activation_state.to_dict(),
            "resulting_approved_plan_snapshot": (
                None
                if self.resulting_approved_plan_snapshot is None
                else self.resulting_approved_plan_snapshot.to_dict()
            ),
            "reused_existing": self.reused_existing,
            "downstream_handoff": self.downstream_handoff.to_dict(),
        }


@dataclass(frozen=True)
class ReviewApprovalIssueFact:
    fact_id: str
    emitted_by_service: str
    context_scope: str
    fact_type: str
    review_context_id: str
    planning_run_id: str
    source_snapshot_id: str
    approved_plan_id: str
    activation_id: Optional[str]
    severity: str
    code: str
    message: str
    entity_type: str
    entity_id: str
    entity_external_id: Optional[str]
    related_delta_ids: List[str]
    related_connected_set_id: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewApprovalIssueFactEmission:
    emission_id: str
    review_context_id: str
    planning_run_id: str
    source_snapshot_id: str
    approved_plan_id: str
    activation_id: Optional[str]
    blocking_fact_count: int
    informational_fact_count: int
    total_fact_count: int
    issue_facts: List[ReviewApprovalIssueFact]

    def to_dict(self) -> Dict[str, object]:
        return {
            "emission_id": self.emission_id,
            "review_context_id": self.review_context_id,
            "planning_run_id": self.planning_run_id,
            "source_snapshot_id": self.source_snapshot_id,
            "approved_plan_id": self.approved_plan_id,
            "activation_id": self.activation_id,
            "blocking_fact_count": self.blocking_fact_count,
            "informational_fact_count": self.informational_fact_count,
            "total_fact_count": self.total_fact_count,
            "issue_facts": [fact.to_dict() for fact in self.issue_facts],
        }
