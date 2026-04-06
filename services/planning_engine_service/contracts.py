"""Planning Engine contracts for baseline daily capacity modeling."""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


CAPACITY_INPUT_STATE_READY = "ready"
CAPACITY_INPUT_STATE_READY_WITH_ADVISORIES = "ready_with_advisories"
CAPACITY_INPUT_STATE_BLOCKED = "blocked"

DRAFT_SCHEDULE_STATE_SCHEDULED = "scheduled"
DRAFT_SCHEDULE_STATE_PARTIALLY_SCHEDULABLE = "partially_schedulable"
DRAFT_SCHEDULE_STATE_UNSCHEDULABLE = "unschedulable"

TASK_SCHEDULE_STATUS_SCHEDULED = "scheduled"
TASK_SCHEDULE_STATUS_PARTIALLY_SCHEDULED = "partially_scheduled"
TASK_SCHEDULE_STATUS_UNSCHEDULABLE = "unschedulable"

COMPARISON_CONTEXT_SOURCE_BASELINE_ONLY = "source_baseline_only"


@dataclass(frozen=True)
class CapacityInputIssue:
    issue_id: str
    source_snapshot_id: str
    severity: str
    code: str
    message: str
    resource_external_id: Optional[str]
    field: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CapacityInputReadiness:
    state: str
    runnable: bool
    blocking_issue_count: int
    advisory_issue_count: int
    total_issue_count: int

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DailyCapacityOutput:
    output_id: str
    source_snapshot_id: str
    resource_id: str
    resource_external_id: str
    resource_display_name: Optional[str]
    date: str
    working_day: bool
    calendar_capacity_hours: float
    availability_ratio: float
    active_assignment_count: int
    productive_capacity_hours: float
    exception_reason: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ResourceCapacitySummary:
    resource_id: str
    resource_external_id: str
    resource_display_name: Optional[str]
    assignment_input_count: int
    assigned_effort_hours: float
    window_start_date: Optional[str]
    window_end_date: Optional[str]
    total_productive_capacity_hours: float
    days_modeled: int

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CapacityModelResult:
    capacity_snapshot_id: str
    source_snapshot_id: str
    source_artifact_id: str
    input_readiness: CapacityInputReadiness
    resource_summaries: List[ResourceCapacitySummary]
    daily_capacity_outputs: List[DailyCapacityOutput]
    input_issues: List[CapacityInputIssue]

    def to_dict(self) -> Dict[str, object]:
        return {
            "capacity_snapshot_id": self.capacity_snapshot_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_artifact_id": self.source_artifact_id,
            "input_readiness": self.input_readiness.to_dict(),
            "resource_summaries": [
                summary.to_dict() for summary in self.resource_summaries
            ],
            "daily_capacity_outputs": [
                output.to_dict() for output in self.daily_capacity_outputs
            ],
            "input_issues": [issue.to_dict() for issue in self.input_issues],
        }


@dataclass(frozen=True)
class DraftScheduleIssue:
    issue_id: str
    planning_run_id: str
    source_snapshot_id: str
    severity: str
    code: str
    message: str
    task_external_id: Optional[str]
    field: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TaskAllocationOutput:
    allocation_id: str
    planning_run_id: str
    draft_schedule_id: str
    source_snapshot_id: str
    task_id: str
    task_external_id: str
    resource_id: str
    resource_external_id: str
    date: str
    allocated_hours: float

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DraftTaskSchedule:
    planning_run_id: str
    draft_schedule_id: str
    source_snapshot_id: str
    task_id: str
    task_external_id: str
    task_name: str
    project_id: str
    project_external_id: str
    parent_task_id: Optional[str]
    status: str
    requested_start_date: Optional[str]
    requested_due_date: Optional[str]
    scheduled_start_date: Optional[str]
    scheduled_end_date: Optional[str]
    required_effort_hours: float
    scheduled_effort_hours: float
    unscheduled_effort_hours: float
    assigned_resource_ids: List[str]
    predecessor_task_ids: List[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DraftScheduleResult:
    draft_schedule_id: str
    planning_run_id: str
    source_snapshot_id: str
    source_artifact_id: str
    capacity_snapshot_id: str
    schedule_state: str
    task_schedules: List[DraftTaskSchedule]
    allocation_outputs: List[TaskAllocationOutput]
    schedule_issues: List[DraftScheduleIssue]

    def to_dict(self) -> Dict[str, object]:
        return {
            "draft_schedule_id": self.draft_schedule_id,
            "planning_run_id": self.planning_run_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_artifact_id": self.source_artifact_id,
            "capacity_snapshot_id": self.capacity_snapshot_id,
            "schedule_state": self.schedule_state,
            "task_schedules": [task.to_dict() for task in self.task_schedules],
            "allocation_outputs": [
                allocation.to_dict() for allocation in self.allocation_outputs
            ],
            "schedule_issues": [issue.to_dict() for issue in self.schedule_issues],
        }


@dataclass(frozen=True)
class VarianceFact:
    fact_id: str
    planning_run_id: str
    draft_schedule_id: str
    source_snapshot_id: str
    task_id: str
    task_external_id: str
    task_name: str
    baseline_start_date: Optional[str]
    baseline_due_date: Optional[str]
    scheduled_start_date: Optional[str]
    scheduled_end_date: Optional[str]
    start_variance_days: Optional[int]
    finish_variance_days: Optional[int]
    slippage_detected: bool
    unscheduled_effort_hours: float

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CriticalityFact:
    fact_id: str
    planning_run_id: str
    draft_schedule_id: str
    source_snapshot_id: str
    task_id: str
    task_external_id: str
    task_name: str
    direct_predecessor_count: int
    direct_successor_count: int
    dependency_chain_depth: int
    downstream_dependency_count: int
    slack_days: Optional[int]
    zero_slack: bool
    blocked_by_unscheduled_predecessor: bool
    critical: bool

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlanningIssueFact:
    fact_id: str
    planning_run_id: str
    draft_schedule_id: str
    source_snapshot_id: str
    severity: str
    code: str
    message: str
    entity_type: str
    entity_id: str
    entity_external_id: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlanningDiagnosticsResult:
    diagnostics_id: str
    planning_run_id: str
    draft_schedule_id: str
    source_snapshot_id: str
    source_artifact_id: str
    capacity_snapshot_id: str
    comparison_context: str
    approved_comparison_available: bool
    variance_facts: List[VarianceFact]
    criticality_facts: List[CriticalityFact]
    planning_issue_facts: List[PlanningIssueFact]

    def to_dict(self) -> Dict[str, object]:
        return {
            "diagnostics_id": self.diagnostics_id,
            "planning_run_id": self.planning_run_id,
            "draft_schedule_id": self.draft_schedule_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_artifact_id": self.source_artifact_id,
            "capacity_snapshot_id": self.capacity_snapshot_id,
            "comparison_context": self.comparison_context,
            "approved_comparison_available": self.approved_comparison_available,
            "variance_facts": [fact.to_dict() for fact in self.variance_facts],
            "criticality_facts": [
                fact.to_dict() for fact in self.criticality_facts
            ],
            "planning_issue_facts": [
                fact.to_dict() for fact in self.planning_issue_facts
            ],
        }


@dataclass(frozen=True)
class PlanningRunExecutionRecord:
    planning_run_id: str
    workflow_instance_id: str
    planning_context_key: str
    source_snapshot_id: str
    source_artifact_id: str
    attempt_number: int
    accepted_at: str
    capacity_snapshot_id: str
    draft_schedule_id: str
    draft_schedule_state: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlanningRunExecutionResult:
    execution_record: PlanningRunExecutionRecord
    capacity_result: CapacityModelResult
    draft_schedule_result: DraftScheduleResult
    diagnostics_result: PlanningDiagnosticsResult

    def to_dict(self) -> Dict[str, object]:
        return {
            "execution_record": self.execution_record.to_dict(),
            "capacity_result": self.capacity_result.to_dict(),
            "draft_schedule_result": self.draft_schedule_result.to_dict(),
            "diagnostics_result": self.diagnostics_result.to_dict(),
        }
