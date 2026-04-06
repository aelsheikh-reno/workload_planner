"""Planning Engine baseline for capacity modeling and draft scheduling."""

import hashlib
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from services.integration_service import (
    NormalizedDependencyRecord,
    NormalizedResourceAssignmentRecord,
    NormalizedResourceExceptionRecord,
    NormalizedResourceRecord,
    NormalizedSourceBundle,
    NormalizedTaskRecord,
)

from .contracts import (
    CAPACITY_INPUT_STATE_BLOCKED,
    CAPACITY_INPUT_STATE_READY,
    CAPACITY_INPUT_STATE_READY_WITH_ADVISORIES,
    COMPARISON_CONTEXT_SOURCE_BASELINE_ONLY,
    DRAFT_SCHEDULE_STATE_PARTIALLY_SCHEDULABLE,
    DRAFT_SCHEDULE_STATE_SCHEDULED,
    DRAFT_SCHEDULE_STATE_UNSCHEDULABLE,
    TASK_SCHEDULE_STATUS_PARTIALLY_SCHEDULED,
    TASK_SCHEDULE_STATUS_SCHEDULED,
    TASK_SCHEDULE_STATUS_UNSCHEDULABLE,
    CapacityInputIssue,
    CapacityInputReadiness,
    CapacityModelResult,
    CriticalityFact,
    DailyCapacityOutput,
    PlanningDiagnosticsResult,
    PlanningIssueFact,
    DraftScheduleIssue,
    DraftScheduleResult,
    DraftTaskSchedule,
    PlanningRunExecutionRecord,
    PlanningRunExecutionResult,
    ResourceCapacitySummary,
    TaskAllocationOutput,
    VarianceFact,
)
from .repository import InMemoryPlanningEngineRepository


class PlanningEngineService:
    """Owns deterministic capacity and draft scheduling outputs."""

    def __init__(
        self,
        repository: Optional[InMemoryPlanningEngineRepository] = None,
    ) -> None:
        self._repository = repository or InMemoryPlanningEngineRepository()

    def build_daily_capacity_model(
        self, bundle: NormalizedSourceBundle
    ) -> CapacityModelResult:
        result = _build_capacity_model(bundle)
        self._repository.save_capacity_model(result)
        return result

    def build_draft_schedule(
        self,
        bundle: NormalizedSourceBundle,
        capacity_result: Optional[CapacityModelResult] = None,
        planning_run_id: Optional[str] = None,
    ) -> DraftScheduleResult:
        if capacity_result is None:
            capacity_result = self.build_daily_capacity_model(bundle)
        draft_result = _build_draft_schedule(
            bundle=bundle,
            capacity_result=capacity_result,
            planning_run_id=planning_run_id
            or _stable_id("planning-run", bundle.snapshot.snapshot_id),
        )
        self._repository.save_draft_schedule(draft_result)
        return draft_result

    def execute_planning_run(
        self,
        bundle: NormalizedSourceBundle,
        workflow_instance_id: str,
        planning_context_key: str,
        source_snapshot_id: str,
        source_artifact_id: str,
        requested_by: str,
        requested_at: str,
        attempt_number: int,
    ) -> PlanningRunExecutionResult:
        if bundle.snapshot.snapshot_id != source_snapshot_id:
            raise ValueError("source_snapshot_id does not match the provided bundle.")
        if bundle.artifact.artifact_id != source_artifact_id:
            raise ValueError("source_artifact_id does not match the provided bundle.")

        planning_run_id = _stable_id(
            "planning-run",
            workflow_instance_id,
            planning_context_key,
            source_snapshot_id,
            str(attempt_number),
        )
        capacity_result = self.build_daily_capacity_model(bundle)
        draft_result = self.build_draft_schedule(
            bundle=bundle,
            capacity_result=capacity_result,
            planning_run_id=planning_run_id,
        )
        diagnostics_result = self.build_planning_diagnostics(
            bundle=bundle,
            draft_schedule_result=draft_result,
            capacity_result=capacity_result,
        )
        execution_record = PlanningRunExecutionRecord(
            planning_run_id=planning_run_id,
            workflow_instance_id=workflow_instance_id,
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
            source_artifact_id=source_artifact_id,
            attempt_number=attempt_number,
            accepted_at=requested_at,
            capacity_snapshot_id=capacity_result.capacity_snapshot_id,
            draft_schedule_id=draft_result.draft_schedule_id,
            draft_schedule_state=draft_result.schedule_state,
        )
        execution_result = PlanningRunExecutionResult(
            execution_record=execution_record,
            capacity_result=capacity_result,
            draft_schedule_result=draft_result,
            diagnostics_result=diagnostics_result,
        )
        self._repository.save_execution_result(execution_result)
        return execution_result

    def get_capacity_model(
        self, source_snapshot_id: Optional[str] = None
    ) -> Optional[CapacityModelResult]:
        return self._repository.get_capacity_model(source_snapshot_id=source_snapshot_id)

    def get_capacity_input_readiness(
        self, source_snapshot_id: Optional[str] = None
    ) -> Optional[CapacityInputReadiness]:
        result = self.get_capacity_model(source_snapshot_id=source_snapshot_id)
        if result is None:
            return None
        return result.input_readiness

    def get_draft_schedule(
        self, planning_run_id: Optional[str] = None
    ) -> Optional[DraftScheduleResult]:
        return self._repository.get_draft_schedule(planning_run_id=planning_run_id)

    def build_planning_diagnostics(
        self,
        bundle: NormalizedSourceBundle,
        draft_schedule_result: DraftScheduleResult,
        capacity_result: Optional[CapacityModelResult] = None,
    ) -> PlanningDiagnosticsResult:
        if capacity_result is None:
            capacity_result = self.build_daily_capacity_model(bundle)
        diagnostics_result = _build_planning_diagnostics(
            bundle=bundle,
            draft_schedule_result=draft_schedule_result,
            capacity_result=capacity_result,
        )
        self._repository.save_diagnostics_result(diagnostics_result)
        return diagnostics_result

    def get_planning_diagnostics(
        self, planning_run_id: Optional[str] = None
    ) -> Optional[PlanningDiagnosticsResult]:
        return self._repository.get_diagnostics_result(planning_run_id=planning_run_id)

    def get_execution_result(
        self, planning_run_id: Optional[str] = None
    ) -> Optional[PlanningRunExecutionResult]:
        return self._repository.get_execution_result(planning_run_id=planning_run_id)


def _build_capacity_model(bundle: NormalizedSourceBundle) -> CapacityModelResult:
    issues: List[CapacityInputIssue] = []
    resource_summaries: List[ResourceCapacitySummary] = []
    daily_capacity_outputs: List[DailyCapacityOutput] = []

    if not bundle.source_readiness.runnable:
        issues.append(
            _build_capacity_issue(
                source_snapshot_id=bundle.snapshot.snapshot_id,
                severity="blocking",
                code="source_snapshot_not_runnable",
                message="Capacity modeling requires a runnable normalized source snapshot.",
                resource_external_id=None,
                field="source_readiness",
            )
        )
        readiness = _build_capacity_readiness(issues)
        return CapacityModelResult(
            capacity_snapshot_id=_stable_id(
                "capacity-snapshot",
                bundle.snapshot.snapshot_id,
                readiness.state,
                "blocked",
            ),
            source_snapshot_id=bundle.snapshot.snapshot_id,
            source_artifact_id=bundle.artifact.artifact_id,
            input_readiness=readiness,
            resource_summaries=[],
            daily_capacity_outputs=[],
            input_issues=issues,
        )

    resources_by_id = {resource.resource_id: resource for resource in bundle.resources}
    exceptions_by_resource_date = {
        (exception.resource_id, exception.date): exception
        for exception in bundle.resource_exceptions
    }
    assignments_by_resource: Dict[str, List[NormalizedResourceAssignmentRecord]] = {}
    for assignment in bundle.resource_assignments:
        assignments_by_resource.setdefault(assignment.resource_id, []).append(assignment)

    tasks_by_id = {task.task_id: task for task in bundle.tasks}
    candidate_resource_ids = sorted(
        set(assignments_by_resource.keys()) | set(resources_by_id.keys())
    )

    for resource_id in candidate_resource_ids:
        assignments = sorted(
            assignments_by_resource.get(resource_id, []),
            key=lambda assignment: assignment.assignment_id,
        )
        resource = resources_by_id.get(resource_id)
        resource_external_id = (
            resource.external_resource_id
            if resource is not None
            else assignments[0].resource_external_id
            if assignments
            else None
        )

        blocking_issue = _validate_resource_inputs(
            bundle=bundle,
            resource=resource,
            resource_external_id=resource_external_id,
            assignments=assignments,
            issues=issues,
        )
        if blocking_issue or resource is None:
            continue

        task_window = _derive_resource_window(assignments=assignments, tasks_by_id=tasks_by_id)
        if task_window is None:
            resource_summaries.append(
                ResourceCapacitySummary(
                    resource_id=resource.resource_id,
                    resource_external_id=resource.external_resource_id,
                    resource_display_name=resource.display_name,
                    assignment_input_count=len(assignments),
                    assigned_effort_hours=_sum_assignment_effort_hours(
                        assignments=assignments,
                        tasks_by_id=tasks_by_id,
                    ),
                    window_start_date=None,
                    window_end_date=None,
                    total_productive_capacity_hours=0.0,
                    days_modeled=0,
                )
            )
            continue

        window_start, window_end = task_window
        resource_outputs: List[DailyCapacityOutput] = []
        for current_date in _date_range(window_start, window_end):
            active_assignment_count = _count_active_assignments(
                current_date=current_date,
                assignments=assignments,
                tasks_by_id=tasks_by_id,
            )
            output = _build_daily_capacity_output(
                bundle=bundle,
                resource=resource,
                current_date=current_date,
                active_assignment_count=active_assignment_count,
                resource_exception=exceptions_by_resource_date.get(
                    (resource.resource_id, current_date)
                ),
            )
            resource_outputs.append(output)

        daily_capacity_outputs.extend(resource_outputs)
        resource_summaries.append(
            ResourceCapacitySummary(
                resource_id=resource.resource_id,
                resource_external_id=resource.external_resource_id,
                resource_display_name=resource.display_name,
                assignment_input_count=len(assignments),
                assigned_effort_hours=_sum_assignment_effort_hours(
                    assignments=assignments,
                    tasks_by_id=tasks_by_id,
                ),
                window_start_date=window_start,
                window_end_date=window_end,
                total_productive_capacity_hours=round(
                    sum(output.productive_capacity_hours for output in resource_outputs), 4
                ),
                days_modeled=len(resource_outputs),
            )
        )

    issues.sort(
        key=lambda issue: (
            issue.severity,
            issue.code,
            issue.resource_external_id or "",
        )
    )
    resource_summaries.sort(key=lambda summary: summary.resource_external_id)
    daily_capacity_outputs.sort(
        key=lambda output: (output.resource_external_id, output.date)
    )

    readiness = _build_capacity_readiness(issues)
    return CapacityModelResult(
        capacity_snapshot_id=_stable_id(
            "capacity-snapshot",
            bundle.snapshot.snapshot_id,
            *[output.output_id for output in daily_capacity_outputs],
            *[issue.issue_id for issue in issues],
        ),
        source_snapshot_id=bundle.snapshot.snapshot_id,
        source_artifact_id=bundle.artifact.artifact_id,
        input_readiness=readiness,
        resource_summaries=resource_summaries,
        daily_capacity_outputs=daily_capacity_outputs,
        input_issues=issues,
    )


def _build_draft_schedule(
    bundle: NormalizedSourceBundle,
    capacity_result: CapacityModelResult,
    planning_run_id: str,
) -> DraftScheduleResult:
    draft_schedule_id = _stable_id(
        "draft-schedule",
        planning_run_id,
        capacity_result.capacity_snapshot_id,
    )
    task_schedules: List[DraftTaskSchedule] = []
    allocation_outputs: List[TaskAllocationOutput] = []
    schedule_issues: List[DraftScheduleIssue] = []

    task_order = _topologically_order_tasks(bundle.tasks, bundle.dependencies)
    tasks_by_id = {task.task_id: task for task in bundle.tasks}
    assignments_by_task: Dict[str, List[NormalizedResourceAssignmentRecord]] = {}
    for assignment in bundle.resource_assignments:
        assignments_by_task.setdefault(assignment.task_id, []).append(assignment)

    predecessors_by_task: Dict[str, List[str]] = {task.task_id: [] for task in bundle.tasks}
    for dependency in bundle.dependencies:
        predecessors_by_task.setdefault(dependency.successor_task_id, []).append(
            dependency.predecessor_task_id
        )
    for task_id, predecessor_ids in predecessors_by_task.items():
        predecessor_ids.sort()

    if not capacity_result.input_readiness.runnable:
        for task in task_order:
            task_schedule = _build_task_schedule(
                planning_run_id=planning_run_id,
                draft_schedule_id=draft_schedule_id,
                source_snapshot_id=bundle.snapshot.snapshot_id,
                task=task,
                assigned_resource_ids=sorted(
                    {
                        assignment.resource_id
                        for assignment in assignments_by_task.get(task.task_id, [])
                    }
                ),
                predecessor_task_ids=predecessors_by_task.get(task.task_id, []),
                status=TASK_SCHEDULE_STATUS_UNSCHEDULABLE,
                scheduled_start_date=None,
                scheduled_end_date=None,
                scheduled_effort_hours=0.0,
            )
            task_schedules.append(task_schedule)
            schedule_issues.append(
                _build_schedule_issue(
                    planning_run_id=planning_run_id,
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    code="capacity_input_not_runnable",
                    message="Draft scheduling requires runnable daily capacity outputs.",
                    task_external_id=task.external_task_id,
                    field="capacity_result.input_readiness",
                )
            )
        return DraftScheduleResult(
            draft_schedule_id=draft_schedule_id,
            planning_run_id=planning_run_id,
            source_snapshot_id=bundle.snapshot.snapshot_id,
            source_artifact_id=bundle.artifact.artifact_id,
            capacity_snapshot_id=capacity_result.capacity_snapshot_id,
            schedule_state=DRAFT_SCHEDULE_STATE_UNSCHEDULABLE,
            task_schedules=task_schedules,
            allocation_outputs=[],
            schedule_issues=sorted(
                schedule_issues,
                key=lambda issue: (issue.code, issue.task_external_id or ""),
            ),
        )

    remaining_capacity = {
        (output.resource_id, output.date): output.productive_capacity_hours
        for output in capacity_result.daily_capacity_outputs
    }
    task_schedule_index: Dict[str, DraftTaskSchedule] = {}

    for task in task_order:
        assignments = sorted(
            assignments_by_task.get(task.task_id, []),
            key=lambda assignment: (assignment.resource_external_id, assignment.assignment_id),
        )
        predecessor_task_ids = predecessors_by_task.get(task.task_id, [])
        predecessor_schedules = [
            task_schedule_index.get(predecessor_id)
            for predecessor_id in predecessor_task_ids
        ]

        if task.effort_hours is None:
            task_schedule = _build_task_schedule(
                planning_run_id=planning_run_id,
                draft_schedule_id=draft_schedule_id,
                source_snapshot_id=bundle.snapshot.snapshot_id,
                task=task,
                assigned_resource_ids=[assignment.resource_id for assignment in assignments],
                predecessor_task_ids=predecessor_task_ids,
                status=TASK_SCHEDULE_STATUS_UNSCHEDULABLE,
                scheduled_start_date=None,
                scheduled_end_date=None,
                scheduled_effort_hours=0.0,
            )
            task_schedules.append(task_schedule)
            task_schedule_index[task.task_id] = task_schedule
            schedule_issues.append(
                _build_schedule_issue(
                    planning_run_id=planning_run_id,
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    code="missing_task_effort",
                    message="Draft scheduling requires normalized task effort.",
                    task_external_id=task.external_task_id,
                    field="tasks[].effort_hours",
                )
            )
            continue

        if task.start_date is None or task.due_date is None:
            task_schedule = _build_task_schedule(
                planning_run_id=planning_run_id,
                draft_schedule_id=draft_schedule_id,
                source_snapshot_id=bundle.snapshot.snapshot_id,
                task=task,
                assigned_resource_ids=[assignment.resource_id for assignment in assignments],
                predecessor_task_ids=predecessor_task_ids,
                status=TASK_SCHEDULE_STATUS_UNSCHEDULABLE,
                scheduled_start_date=None,
                scheduled_end_date=None,
                scheduled_effort_hours=0.0,
            )
            task_schedules.append(task_schedule)
            task_schedule_index[task.task_id] = task_schedule
            schedule_issues.append(
                _build_schedule_issue(
                    planning_run_id=planning_run_id,
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    code="missing_schedule_window",
                    message="Draft scheduling requires both start and due dates.",
                    task_external_id=task.external_task_id,
                    field="tasks[].dates",
                )
            )
            continue

        if not assignments:
            task_schedule = _build_task_schedule(
                planning_run_id=planning_run_id,
                draft_schedule_id=draft_schedule_id,
                source_snapshot_id=bundle.snapshot.snapshot_id,
                task=task,
                assigned_resource_ids=[],
                predecessor_task_ids=predecessor_task_ids,
                status=TASK_SCHEDULE_STATUS_UNSCHEDULABLE,
                scheduled_start_date=None,
                scheduled_end_date=None,
                scheduled_effort_hours=0.0,
            )
            task_schedules.append(task_schedule)
            task_schedule_index[task.task_id] = task_schedule
            schedule_issues.append(
                _build_schedule_issue(
                    planning_run_id=planning_run_id,
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    code="missing_task_assignment",
                    message="Draft scheduling requires at least one normalized assignment.",
                    task_external_id=task.external_task_id,
                    field="resource_assignments",
                )
            )
            continue

        if any(
            predecessor_schedule is None
            or predecessor_schedule.status != TASK_SCHEDULE_STATUS_SCHEDULED
            for predecessor_schedule in predecessor_schedules
        ):
            task_schedule = _build_task_schedule(
                planning_run_id=planning_run_id,
                draft_schedule_id=draft_schedule_id,
                source_snapshot_id=bundle.snapshot.snapshot_id,
                task=task,
                assigned_resource_ids=[assignment.resource_id for assignment in assignments],
                predecessor_task_ids=predecessor_task_ids,
                status=TASK_SCHEDULE_STATUS_UNSCHEDULABLE,
                scheduled_start_date=None,
                scheduled_end_date=None,
                scheduled_effort_hours=0.0,
            )
            task_schedules.append(task_schedule)
            task_schedule_index[task.task_id] = task_schedule
            schedule_issues.append(
                _build_schedule_issue(
                    planning_run_id=planning_run_id,
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    code="predecessor_not_fully_scheduled",
                    message="Successor placement requires all predecessors to be fully scheduled first.",
                    task_external_id=task.external_task_id,
                    field="dependencies",
                )
            )
            continue

        earliest_start = task.start_date
        if predecessor_schedules:
            predecessor_finish = max(
                predecessor_schedule.scheduled_end_date
                for predecessor_schedule in predecessor_schedules
                if predecessor_schedule is not None
                and predecessor_schedule.scheduled_end_date is not None
            )
            earliest_start = max(earliest_start, _next_date(predecessor_finish))

        if earliest_start > task.due_date:
            task_schedule = _build_task_schedule(
                planning_run_id=planning_run_id,
                draft_schedule_id=draft_schedule_id,
                source_snapshot_id=bundle.snapshot.snapshot_id,
                task=task,
                assigned_resource_ids=[assignment.resource_id for assignment in assignments],
                predecessor_task_ids=predecessor_task_ids,
                status=TASK_SCHEDULE_STATUS_UNSCHEDULABLE,
                scheduled_start_date=None,
                scheduled_end_date=None,
                scheduled_effort_hours=0.0,
            )
            task_schedules.append(task_schedule)
            task_schedule_index[task.task_id] = task_schedule
            schedule_issues.append(
                _build_schedule_issue(
                    planning_run_id=planning_run_id,
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    code="dependency_pushes_past_due_date",
                    message="Dependency-respecting placement pushed the task past its due date.",
                    task_external_id=task.external_task_id,
                    field="dependencies",
                )
            )
            continue

        task_allocations: List[TaskAllocationOutput] = []
        assignment_shares = _build_assignment_shares(assignments, task.effort_hours)
        for assignment, share_hours in assignment_shares:
            assignment_allocations, remaining_share_hours = _schedule_assignment_share(
                planning_run_id=planning_run_id,
                draft_schedule_id=draft_schedule_id,
                source_snapshot_id=bundle.snapshot.snapshot_id,
                task=task,
                assignment=assignment,
                share_hours=share_hours,
                earliest_start=earliest_start,
                due_date=task.due_date,
                remaining_capacity=remaining_capacity,
            )
            task_allocations.extend(assignment_allocations)
            if remaining_share_hours > 0:
                continue

        task_allocations.sort(key=lambda allocation: (allocation.date, allocation.resource_external_id))
        allocation_outputs.extend(task_allocations)
        scheduled_effort_hours = round(
            sum(allocation.allocated_hours for allocation in task_allocations), 4
        )
        allocation_dates = [allocation.date for allocation in task_allocations]
        if scheduled_effort_hours >= task.effort_hours:
            status = TASK_SCHEDULE_STATUS_SCHEDULED
        elif scheduled_effort_hours > 0:
            status = TASK_SCHEDULE_STATUS_PARTIALLY_SCHEDULED
            schedule_issues.append(
                _build_schedule_issue(
                    planning_run_id=planning_run_id,
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    code="task_partially_scheduled",
                    message="Available daily capacity was not enough to fully place the task within its window.",
                    task_external_id=task.external_task_id,
                    field="allocation_outputs",
                )
            )
        else:
            status = TASK_SCHEDULE_STATUS_UNSCHEDULABLE
            schedule_issues.append(
                _build_schedule_issue(
                    planning_run_id=planning_run_id,
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    code="task_unschedulable_within_window",
                    message="No authoritative daily capacity remained to place the task within its window.",
                    task_external_id=task.external_task_id,
                    field="allocation_outputs",
                )
            )

        task_schedule = _build_task_schedule(
            planning_run_id=planning_run_id,
            draft_schedule_id=draft_schedule_id,
            source_snapshot_id=bundle.snapshot.snapshot_id,
            task=task,
            assigned_resource_ids=[assignment.resource_id for assignment in assignments],
            predecessor_task_ids=predecessor_task_ids,
            status=status,
            scheduled_start_date=min(allocation_dates) if allocation_dates else None,
            scheduled_end_date=max(allocation_dates) if allocation_dates else None,
            scheduled_effort_hours=scheduled_effort_hours,
        )
        task_schedules.append(task_schedule)
        task_schedule_index[task.task_id] = task_schedule

    task_schedules.sort(key=lambda task_schedule: _task_schedule_sort_key(task_schedule, tasks_by_id))
    allocation_outputs.sort(
        key=lambda allocation: (
            allocation.task_external_id,
            allocation.date,
            allocation.resource_external_id,
        )
    )
    schedule_issues.sort(key=lambda issue: (issue.code, issue.task_external_id or ""))

    schedule_state = _build_schedule_state(task_schedules)
    return DraftScheduleResult(
        draft_schedule_id=draft_schedule_id,
        planning_run_id=planning_run_id,
        source_snapshot_id=bundle.snapshot.snapshot_id,
        source_artifact_id=bundle.artifact.artifact_id,
        capacity_snapshot_id=capacity_result.capacity_snapshot_id,
        schedule_state=schedule_state,
        task_schedules=task_schedules,
        allocation_outputs=allocation_outputs,
        schedule_issues=schedule_issues,
    )


def _build_planning_diagnostics(
    bundle: NormalizedSourceBundle,
    draft_schedule_result: DraftScheduleResult,
    capacity_result: CapacityModelResult,
) -> PlanningDiagnosticsResult:
    tasks_by_id = {task.task_id: task for task in bundle.tasks}
    task_schedules_by_id = {
        task_schedule.task_id: task_schedule
        for task_schedule in draft_schedule_result.task_schedules
    }
    direct_predecessors: Dict[str, List[str]] = {task.task_id: [] for task in bundle.tasks}
    direct_successors: Dict[str, List[str]] = {task.task_id: [] for task in bundle.tasks}
    for dependency in bundle.dependencies:
        direct_predecessors.setdefault(dependency.successor_task_id, []).append(
            dependency.predecessor_task_id
        )
        direct_successors.setdefault(dependency.predecessor_task_id, []).append(
            dependency.successor_task_id
        )

    for task_id in direct_predecessors:
        direct_predecessors[task_id].sort()
    for task_id in direct_successors:
        direct_successors[task_id].sort()

    ordered_task_ids = [task.task_id for task in _topologically_order_tasks(bundle.tasks, bundle.dependencies)]
    dependency_depths = _build_dependency_depths(
        ordered_task_ids=ordered_task_ids,
        direct_predecessors=direct_predecessors,
    )
    downstream_dependency_counts = _build_downstream_dependency_counts(
        ordered_task_ids=ordered_task_ids,
        direct_successors=direct_successors,
    )

    variance_facts: List[VarianceFact] = []
    criticality_facts_by_task_id: Dict[str, CriticalityFact] = {}
    criticality_facts: List[CriticalityFact] = []
    planning_issue_facts: List[PlanningIssueFact] = []

    for task_id in ordered_task_ids:
        task = tasks_by_id[task_id]
        task_schedule = task_schedules_by_id[task_id]
        variance_facts.append(
            _build_variance_fact(
                draft_schedule_result=draft_schedule_result,
                task=task,
                task_schedule=task_schedule,
            )
        )

    for task_id in reversed(ordered_task_ids):
        task = tasks_by_id[task_id]
        task_schedule = task_schedules_by_id[task_id]
        successor_ids = direct_successors.get(task_id, [])
        successor_facts = [
            criticality_facts_by_task_id[successor_id]
            for successor_id in successor_ids
            if successor_id in criticality_facts_by_task_id
        ]
        criticality_fact = _build_criticality_fact(
            draft_schedule_result=draft_schedule_result,
            task=task,
            task_schedule=task_schedule,
            direct_predecessor_count=len(direct_predecessors.get(task_id, [])),
            direct_successor_count=len(successor_ids),
            dependency_chain_depth=dependency_depths.get(task_id, 0),
            downstream_dependency_count=downstream_dependency_counts.get(task_id, 0),
            blocked_by_unscheduled_predecessor=any(
                task_schedules_by_id[predecessor_id].status != TASK_SCHEDULE_STATUS_SCHEDULED
                for predecessor_id in direct_predecessors.get(task_id, [])
            ),
            successor_facts=successor_facts,
        )
        criticality_facts_by_task_id[task_id] = criticality_fact

    criticality_facts = sorted(
        criticality_facts_by_task_id.values(),
        key=lambda fact: _task_sort_key(tasks_by_id[fact.task_id]),
    )

    variance_facts_by_task_id = {fact.task_id: fact for fact in variance_facts}
    for task_id in ordered_task_ids:
        task = tasks_by_id[task_id]
        task_schedule = task_schedules_by_id[task_id]
        variance_fact = variance_facts_by_task_id[task_id]
        criticality_fact = criticality_facts_by_task_id[task_id]
        planning_issue_facts.extend(
            _build_planning_issue_facts(
                draft_schedule_result=draft_schedule_result,
                task=task,
                task_schedule=task_schedule,
                variance_fact=variance_fact,
                criticality_fact=criticality_fact,
            )
        )

    variance_facts.sort(key=lambda fact: _task_sort_key(tasks_by_id[fact.task_id]))
    planning_issue_facts.sort(
        key=lambda fact: (fact.severity, fact.code, fact.entity_external_id)
    )

    return PlanningDiagnosticsResult(
        diagnostics_id=_stable_id(
            "planning-diagnostics",
            draft_schedule_result.planning_run_id,
            draft_schedule_result.draft_schedule_id,
            capacity_result.capacity_snapshot_id,
        ),
        planning_run_id=draft_schedule_result.planning_run_id,
        draft_schedule_id=draft_schedule_result.draft_schedule_id,
        source_snapshot_id=draft_schedule_result.source_snapshot_id,
        source_artifact_id=draft_schedule_result.source_artifact_id,
        capacity_snapshot_id=capacity_result.capacity_snapshot_id,
        comparison_context=COMPARISON_CONTEXT_SOURCE_BASELINE_ONLY,
        approved_comparison_available=False,
        variance_facts=variance_facts,
        criticality_facts=criticality_facts,
        planning_issue_facts=planning_issue_facts,
    )


def _validate_resource_inputs(
    bundle: NormalizedSourceBundle,
    resource: Optional[NormalizedResourceRecord],
    resource_external_id: Optional[str],
    assignments: List[NormalizedResourceAssignmentRecord],
    issues: List[CapacityInputIssue],
) -> bool:
    if resource is None:
        if assignments:
            issues.append(
                _build_capacity_issue(
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    severity="blocking",
                    code="missing_resource_capacity_profile",
                    message="Assigned resources require a normalized capacity profile before scheduling begins.",
                    resource_external_id=resource_external_id,
                    field="resources",
                )
            )
            return True
        return False

    if resource.default_daily_capacity_hours is None:
        issues.append(
            _build_capacity_issue(
                source_snapshot_id=bundle.snapshot.snapshot_id,
                severity="blocking",
                code="missing_default_daily_capacity_hours",
                message="Resource calendar daily_capacity_hours is required for daily capacity modeling.",
                resource_external_id=resource.external_resource_id,
                field="resources[].calendar.daily_capacity_hours",
            )
        )
        return True

    if resource.availability_ratio is None:
        issues.append(
            _build_capacity_issue(
                source_snapshot_id=bundle.snapshot.snapshot_id,
                severity="blocking",
                code="missing_availability_ratio",
                message="Resource availability fte_ratio is required for daily capacity modeling.",
                resource_external_id=resource.external_resource_id,
                field="resources[].availability.fte_ratio",
            )
        )
        return True

    if not resource.working_days:
        issues.append(
            _build_capacity_issue(
                source_snapshot_id=bundle.snapshot.snapshot_id,
                severity="blocking",
                code="missing_working_days",
                message="Resource calendar working_days is required for daily capacity modeling.",
                resource_external_id=resource.external_resource_id,
                field="resources[].calendar.working_days",
            )
        )
        return True

    return False


def _derive_resource_window(
    assignments: List[NormalizedResourceAssignmentRecord],
    tasks_by_id: Dict[str, NormalizedTaskRecord],
) -> Optional[Tuple[str, str]]:
    window_starts: List[str] = []
    window_ends: List[str] = []
    for assignment in assignments:
        task = tasks_by_id.get(assignment.task_id)
        if task is None or task.start_date is None or task.due_date is None:
            continue
        window_starts.append(task.start_date)
        window_ends.append(task.due_date)

    if not window_starts or not window_ends:
        return None
    return min(window_starts), max(window_ends)


def _count_active_assignments(
    current_date: str,
    assignments: List[NormalizedResourceAssignmentRecord],
    tasks_by_id: Dict[str, NormalizedTaskRecord],
) -> int:
    active_assignment_count = 0
    for assignment in assignments:
        task = tasks_by_id.get(assignment.task_id)
        if task is None or task.start_date is None or task.due_date is None:
            continue
        if task.start_date <= current_date <= task.due_date:
            active_assignment_count += 1
    return active_assignment_count


def _sum_assignment_effort_hours(
    assignments: List[NormalizedResourceAssignmentRecord],
    tasks_by_id: Dict[str, NormalizedTaskRecord],
) -> float:
    total_effort_hours = 0.0
    seen_task_ids = set()
    for assignment in assignments:
        if assignment.task_id in seen_task_ids:
            continue
        seen_task_ids.add(assignment.task_id)
        task = tasks_by_id.get(assignment.task_id)
        if task is None or task.effort_hours is None:
            continue
        total_effort_hours += task.effort_hours
    return round(total_effort_hours, 4)


def _build_daily_capacity_output(
    bundle: NormalizedSourceBundle,
    resource: NormalizedResourceRecord,
    current_date: str,
    active_assignment_count: int,
    resource_exception: Optional[NormalizedResourceExceptionRecord],
) -> DailyCapacityOutput:
    working_day = _day_name(current_date) in set(resource.working_days)
    calendar_capacity_hours = (
        resource.default_daily_capacity_hours if working_day else 0.0
    )
    productive_capacity_hours = round(
        calendar_capacity_hours * resource.availability_ratio, 4
    )
    exception_reason = None
    if resource_exception is not None:
        productive_capacity_hours = resource_exception.available_capacity_hours
        exception_reason = resource_exception.reason

    return DailyCapacityOutput(
        output_id=_stable_id(
            "capacity-output", bundle.snapshot.snapshot_id, resource.resource_id, current_date
        ),
        source_snapshot_id=bundle.snapshot.snapshot_id,
        resource_id=resource.resource_id,
        resource_external_id=resource.external_resource_id,
        resource_display_name=resource.display_name,
        date=current_date,
        working_day=working_day,
        calendar_capacity_hours=round(calendar_capacity_hours, 4),
        availability_ratio=resource.availability_ratio,
        active_assignment_count=active_assignment_count,
        productive_capacity_hours=round(productive_capacity_hours, 4),
        exception_reason=exception_reason,
    )


def _topologically_order_tasks(
    tasks: List[NormalizedTaskRecord],
    dependencies: List[NormalizedDependencyRecord],
) -> List[NormalizedTaskRecord]:
    tasks_by_id = {task.task_id: task for task in tasks}
    indegree = {task.task_id: 0 for task in tasks}
    successors: Dict[str, List[str]] = {task.task_id: [] for task in tasks}
    for dependency in dependencies:
        indegree[dependency.successor_task_id] = indegree.get(
            dependency.successor_task_id, 0
        ) + 1
        successors.setdefault(dependency.predecessor_task_id, []).append(
            dependency.successor_task_id
        )

    ordered_tasks: List[NormalizedTaskRecord] = []
    available = sorted(
        [task for task in tasks if indegree.get(task.task_id, 0) == 0],
        key=_task_sort_key,
    )
    while available:
        task = available.pop(0)
        ordered_tasks.append(task)
        for successor_id in sorted(
            successors.get(task.task_id, []),
            key=lambda task_id: _task_sort_key(tasks_by_id[task_id]),
        ):
            indegree[successor_id] -= 1
            if indegree[successor_id] == 0:
                available.append(tasks_by_id[successor_id])
                available.sort(key=_task_sort_key)

    if len(ordered_tasks) != len(tasks):
        seen_ids = {task.task_id for task in ordered_tasks}
        remaining = sorted(
            [task for task in tasks if task.task_id not in seen_ids],
            key=_task_sort_key,
        )
        ordered_tasks.extend(remaining)
    return ordered_tasks


def _build_assignment_shares(
    assignments: List[NormalizedResourceAssignmentRecord],
    total_effort_hours: float,
) -> List[Tuple[NormalizedResourceAssignmentRecord, float]]:
    if not assignments:
        return []

    if any(assignment.allocation_percent is not None for assignment in assignments):
        default_weight = round(100.0 / len(assignments), 4)
        weights = [
            float(assignment.allocation_percent)
            if assignment.allocation_percent is not None
            else default_weight
            for assignment in assignments
        ]
    else:
        weights = [1.0 for _ in assignments]
    total_weight = sum(weights)

    shares: List[Tuple[NormalizedResourceAssignmentRecord, float]] = []
    remaining_effort = round(total_effort_hours, 4)
    for index, assignment in enumerate(assignments):
        if index == len(assignments) - 1:
            share_hours = remaining_effort
        else:
            share_hours = round(total_effort_hours * weights[index] / total_weight, 4)
            remaining_effort = round(remaining_effort - share_hours, 4)
        shares.append((assignment, share_hours))
    return shares


def _schedule_assignment_share(
    planning_run_id: str,
    draft_schedule_id: str,
    source_snapshot_id: str,
    task: NormalizedTaskRecord,
    assignment: NormalizedResourceAssignmentRecord,
    share_hours: float,
    earliest_start: str,
    due_date: str,
    remaining_capacity: Dict[Tuple[str, str], float],
) -> Tuple[List[TaskAllocationOutput], float]:
    allocations: List[TaskAllocationOutput] = []
    remaining_share_hours = round(share_hours, 4)
    for current_date in _date_range(earliest_start, due_date):
        available_capacity = remaining_capacity.get((assignment.resource_id, current_date), 0.0)
        if available_capacity <= 0:
            continue
        allocated_hours = round(min(available_capacity, remaining_share_hours), 4)
        if allocated_hours <= 0:
            continue
        remaining_capacity[(assignment.resource_id, current_date)] = round(
            available_capacity - allocated_hours, 4
        )
        remaining_share_hours = round(remaining_share_hours - allocated_hours, 4)
        allocations.append(
            TaskAllocationOutput(
                allocation_id=_stable_id(
                    "task-allocation",
                    planning_run_id,
                    task.task_id,
                    assignment.resource_id,
                    current_date,
                ),
                planning_run_id=planning_run_id,
                draft_schedule_id=draft_schedule_id,
                source_snapshot_id=source_snapshot_id,
                task_id=task.task_id,
                task_external_id=task.external_task_id,
                resource_id=assignment.resource_id,
                resource_external_id=assignment.resource_external_id,
                date=current_date,
                allocated_hours=allocated_hours,
            )
        )
        if remaining_share_hours <= 0:
            break
    return allocations, remaining_share_hours


def _build_task_schedule(
    planning_run_id: str,
    draft_schedule_id: str,
    source_snapshot_id: str,
    task: NormalizedTaskRecord,
    assigned_resource_ids: List[str],
    predecessor_task_ids: List[str],
    status: str,
    scheduled_start_date: Optional[str],
    scheduled_end_date: Optional[str],
    scheduled_effort_hours: float,
) -> DraftTaskSchedule:
    required_effort_hours = round(task.effort_hours or 0.0, 4)
    return DraftTaskSchedule(
        planning_run_id=planning_run_id,
        draft_schedule_id=draft_schedule_id,
        source_snapshot_id=source_snapshot_id,
        task_id=task.task_id,
        task_external_id=task.external_task_id,
        task_name=task.name,
        project_id=task.project_id,
        project_external_id=task.project_external_id,
        parent_task_id=task.parent_task_id,
        status=status,
        requested_start_date=task.start_date,
        requested_due_date=task.due_date,
        scheduled_start_date=scheduled_start_date,
        scheduled_end_date=scheduled_end_date,
        required_effort_hours=required_effort_hours,
        scheduled_effort_hours=round(scheduled_effort_hours, 4),
        unscheduled_effort_hours=round(required_effort_hours - scheduled_effort_hours, 4),
        assigned_resource_ids=sorted(assigned_resource_ids),
        predecessor_task_ids=sorted(predecessor_task_ids),
    )


def _build_schedule_state(task_schedules: List[DraftTaskSchedule]) -> str:
    statuses = {task_schedule.status for task_schedule in task_schedules}
    if statuses == {TASK_SCHEDULE_STATUS_SCHEDULED}:
        return DRAFT_SCHEDULE_STATE_SCHEDULED
    if TASK_SCHEDULE_STATUS_SCHEDULED in statuses or TASK_SCHEDULE_STATUS_PARTIALLY_SCHEDULED in statuses:
        return DRAFT_SCHEDULE_STATE_PARTIALLY_SCHEDULABLE
    return DRAFT_SCHEDULE_STATE_UNSCHEDULABLE


def _build_dependency_depths(
    ordered_task_ids: List[str],
    direct_predecessors: Dict[str, List[str]],
) -> Dict[str, int]:
    dependency_depths: Dict[str, int] = {}
    for task_id in ordered_task_ids:
        predecessor_ids = direct_predecessors.get(task_id, [])
        if not predecessor_ids:
            dependency_depths[task_id] = 0
            continue
        dependency_depths[task_id] = 1 + max(
            dependency_depths[predecessor_id] for predecessor_id in predecessor_ids
        )
    return dependency_depths


def _build_downstream_dependency_counts(
    ordered_task_ids: List[str],
    direct_successors: Dict[str, List[str]],
) -> Dict[str, int]:
    downstream_task_sets: Dict[str, set] = {task_id: set() for task_id in ordered_task_ids}
    for task_id in reversed(ordered_task_ids):
        successor_ids = direct_successors.get(task_id, [])
        for successor_id in successor_ids:
            downstream_task_sets[task_id].add(successor_id)
            downstream_task_sets[task_id].update(
                downstream_task_sets.get(successor_id, set())
            )
    return {
        task_id: len(downstream_task_sets.get(task_id, set()))
        for task_id in ordered_task_ids
    }


def _build_variance_fact(
    draft_schedule_result: DraftScheduleResult,
    task: NormalizedTaskRecord,
    task_schedule: DraftTaskSchedule,
) -> VarianceFact:
    start_variance_days = _date_delta_days(
        baseline_value=task.start_date,
        scheduled_value=task_schedule.scheduled_start_date,
    )
    finish_variance_days = _date_delta_days(
        baseline_value=task.due_date,
        scheduled_value=task_schedule.scheduled_end_date,
    )
    slippage_detected = bool(
        (start_variance_days is not None and start_variance_days > 0)
        or (finish_variance_days is not None and finish_variance_days > 0)
        or task_schedule.unscheduled_effort_hours > 0
    )
    return VarianceFact(
        fact_id=_stable_id(
            "variance-fact",
            draft_schedule_result.planning_run_id,
            task.task_id,
        ),
        planning_run_id=draft_schedule_result.planning_run_id,
        draft_schedule_id=draft_schedule_result.draft_schedule_id,
        source_snapshot_id=draft_schedule_result.source_snapshot_id,
        task_id=task.task_id,
        task_external_id=task.external_task_id,
        task_name=task.name,
        baseline_start_date=task.start_date,
        baseline_due_date=task.due_date,
        scheduled_start_date=task_schedule.scheduled_start_date,
        scheduled_end_date=task_schedule.scheduled_end_date,
        start_variance_days=start_variance_days,
        finish_variance_days=finish_variance_days,
        slippage_detected=slippage_detected,
        unscheduled_effort_hours=task_schedule.unscheduled_effort_hours,
    )


def _build_criticality_fact(
    draft_schedule_result: DraftScheduleResult,
    task: NormalizedTaskRecord,
    task_schedule: DraftTaskSchedule,
    direct_predecessor_count: int,
    direct_successor_count: int,
    dependency_chain_depth: int,
    downstream_dependency_count: int,
    blocked_by_unscheduled_predecessor: bool,
    successor_facts: List[CriticalityFact],
) -> CriticalityFact:
    slack_days = _calculate_slack_days(
        due_date=task_schedule.requested_due_date,
        scheduled_end_date=task_schedule.scheduled_end_date,
    )
    zero_slack = slack_days == 0
    own_pressure = (
        task_schedule.status != TASK_SCHEDULE_STATUS_SCHEDULED
        or zero_slack
    )
    successor_pressure = any(fact.critical for fact in successor_facts)
    return CriticalityFact(
        fact_id=_stable_id(
            "criticality-fact",
            draft_schedule_result.planning_run_id,
            task.task_id,
        ),
        planning_run_id=draft_schedule_result.planning_run_id,
        draft_schedule_id=draft_schedule_result.draft_schedule_id,
        source_snapshot_id=draft_schedule_result.source_snapshot_id,
        task_id=task.task_id,
        task_external_id=task.external_task_id,
        task_name=task.name,
        direct_predecessor_count=direct_predecessor_count,
        direct_successor_count=direct_successor_count,
        dependency_chain_depth=dependency_chain_depth,
        downstream_dependency_count=downstream_dependency_count,
        slack_days=slack_days,
        zero_slack=zero_slack,
        blocked_by_unscheduled_predecessor=blocked_by_unscheduled_predecessor,
        critical=own_pressure or successor_pressure,
    )


def _build_planning_issue_facts(
    draft_schedule_result: DraftScheduleResult,
    task: NormalizedTaskRecord,
    task_schedule: DraftTaskSchedule,
    variance_fact: VarianceFact,
    criticality_fact: CriticalityFact,
) -> List[PlanningIssueFact]:
    issue_facts: List[PlanningIssueFact] = []

    if variance_fact.start_variance_days is not None and variance_fact.start_variance_days > 0:
        issue_facts.append(
            _build_planning_issue_fact(
                planning_run_id=draft_schedule_result.planning_run_id,
                draft_schedule_id=draft_schedule_result.draft_schedule_id,
                source_snapshot_id=draft_schedule_result.source_snapshot_id,
                severity="advisory",
                code="baseline_start_slip",
                message="Draft placement starts later than the imported baseline start date.",
                entity_type="task",
                entity_id=task.task_id,
                entity_external_id=task.external_task_id,
            )
        )

    if task_schedule.status == TASK_SCHEDULE_STATUS_PARTIALLY_SCHEDULED:
        issue_facts.append(
            _build_planning_issue_fact(
                planning_run_id=draft_schedule_result.planning_run_id,
                draft_schedule_id=draft_schedule_result.draft_schedule_id,
                source_snapshot_id=draft_schedule_result.source_snapshot_id,
                severity="advisory",
                code="draft_partially_schedulable",
                message="Draft scheduling placed only part of the required effort within the available window.",
                entity_type="task",
                entity_id=task.task_id,
                entity_external_id=task.external_task_id,
            )
        )

    if task_schedule.status == TASK_SCHEDULE_STATUS_UNSCHEDULABLE:
        issue_facts.append(
            _build_planning_issue_fact(
                planning_run_id=draft_schedule_result.planning_run_id,
                draft_schedule_id=draft_schedule_result.draft_schedule_id,
                source_snapshot_id=draft_schedule_result.source_snapshot_id,
                severity="blocking",
                code="draft_unschedulable",
                message="Draft scheduling could not place this task within the current dependency and capacity constraints.",
                entity_type="task",
                entity_id=task.task_id,
                entity_external_id=task.external_task_id,
            )
        )

    if criticality_fact.zero_slack:
        issue_facts.append(
            _build_planning_issue_fact(
                planning_run_id=draft_schedule_result.planning_run_id,
                draft_schedule_id=draft_schedule_result.draft_schedule_id,
                source_snapshot_id=draft_schedule_result.source_snapshot_id,
                severity="advisory",
                code="criticality_zero_slack",
                message="Draft placement left no slack between scheduled finish and the imported baseline due date.",
                entity_type="task",
                entity_id=task.task_id,
                entity_external_id=task.external_task_id,
            )
        )

    if criticality_fact.blocked_by_unscheduled_predecessor:
        issue_facts.append(
            _build_planning_issue_fact(
                planning_run_id=draft_schedule_result.planning_run_id,
                draft_schedule_id=draft_schedule_result.draft_schedule_id,
                source_snapshot_id=draft_schedule_result.source_snapshot_id,
                severity="advisory",
                code="dependency_chain_pressure",
                message="An unscheduled predecessor kept this task from participating in a clean dependency chain.",
                entity_type="task",
                entity_id=task.task_id,
                entity_external_id=task.external_task_id,
            )
        )

    return issue_facts


def _build_capacity_issue(
    source_snapshot_id: str,
    severity: str,
    code: str,
    message: str,
    resource_external_id: Optional[str],
    field: Optional[str],
) -> CapacityInputIssue:
    return CapacityInputIssue(
        issue_id=_stable_id(
            "capacity-issue",
            source_snapshot_id,
            severity,
            code,
            resource_external_id or "global",
            field or "none",
        ),
        source_snapshot_id=source_snapshot_id,
        severity=severity,
        code=code,
        message=message,
        resource_external_id=resource_external_id,
        field=field,
    )


def _build_schedule_issue(
    planning_run_id: str,
    source_snapshot_id: str,
    code: str,
    message: str,
    task_external_id: Optional[str],
    field: Optional[str],
) -> DraftScheduleIssue:
    return DraftScheduleIssue(
        issue_id=_stable_id(
            "schedule-issue",
            planning_run_id,
            code,
            task_external_id or "global",
            field or "none",
        ),
        planning_run_id=planning_run_id,
        source_snapshot_id=source_snapshot_id,
        severity="advisory",
        code=code,
        message=message,
        task_external_id=task_external_id,
        field=field,
    )


def _build_planning_issue_fact(
    planning_run_id: str,
    draft_schedule_id: str,
    source_snapshot_id: str,
    severity: str,
    code: str,
    message: str,
    entity_type: str,
    entity_id: str,
    entity_external_id: str,
) -> PlanningIssueFact:
    return PlanningIssueFact(
        fact_id=_stable_id(
            "planning-issue-fact",
            planning_run_id,
            code,
            entity_id,
        ),
        planning_run_id=planning_run_id,
        draft_schedule_id=draft_schedule_id,
        source_snapshot_id=source_snapshot_id,
        severity=severity,
        code=code,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_external_id=entity_external_id,
    )


def _build_capacity_readiness(
    issues: List[CapacityInputIssue],
) -> CapacityInputReadiness:
    blocking_issue_count = len(
        [issue for issue in issues if issue.severity == "blocking"]
    )
    advisory_issue_count = len(
        [issue for issue in issues if issue.severity == "advisory"]
    )
    if blocking_issue_count:
        state = CAPACITY_INPUT_STATE_BLOCKED
        runnable = False
    elif advisory_issue_count:
        state = CAPACITY_INPUT_STATE_READY_WITH_ADVISORIES
        runnable = True
    else:
        state = CAPACITY_INPUT_STATE_READY
        runnable = True

    return CapacityInputReadiness(
        state=state,
        runnable=runnable,
        blocking_issue_count=blocking_issue_count,
        advisory_issue_count=advisory_issue_count,
        total_issue_count=len(issues),
    )


def _task_sort_key(task: NormalizedTaskRecord) -> Tuple[str, List[str], str]:
    return (task.project_external_id, task.hierarchy_path, task.external_task_id)


def _task_schedule_sort_key(
    task_schedule: DraftTaskSchedule,
    tasks_by_id: Dict[str, NormalizedTaskRecord],
) -> Tuple[str, List[str], str]:
    task = tasks_by_id[task_schedule.task_id]
    return _task_sort_key(task)


def _date_delta_days(
    baseline_value: Optional[str],
    scheduled_value: Optional[str],
) -> Optional[int]:
    if baseline_value is None or scheduled_value is None:
        return None
    return (date.fromisoformat(scheduled_value) - date.fromisoformat(baseline_value)).days


def _calculate_slack_days(
    due_date: Optional[str],
    scheduled_end_date: Optional[str],
) -> Optional[int]:
    if due_date is None or scheduled_end_date is None:
        return None
    return (date.fromisoformat(due_date) - date.fromisoformat(scheduled_end_date)).days


def _date_range(start_date: str, end_date: str) -> Iterable[str]:
    current = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    while current <= end:
        yield current.isoformat()
        current += timedelta(days=1)


def _next_date(value: str) -> str:
    return (date.fromisoformat(value) + timedelta(days=1)).isoformat()


def _day_name(value: str) -> str:
    return date.fromisoformat(value).strftime("%A").lower()


def _stable_id(prefix: str, *parts: str) -> str:
    digest_source = "::".join((prefix,) + parts).encode("utf-8")
    return hashlib.sha256(digest_source).hexdigest()[:16]
