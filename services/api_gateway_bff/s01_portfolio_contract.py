"""S01 and D01 read-model composition adapters."""

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from services.planning_engine_service.service import PlanningEngineService


S01_SCREEN = {"id": "S01", "label": "Portfolio Swimlane Home"}
D01_SCREEN = {
    "id": "D01",
    "label": "Swimlane Task Drill-Down Drawer",
    "ownerScreenId": "S01",
}
S02_LINK = {"id": "S02", "label": "Planning Setup"}


def build_s01_portfolio_contract(
    planning_engine_service: PlanningEngineService,
    planning_run_id: Optional[str] = None,
    source_snapshot_id: Optional[str] = None,
    is_refreshing: bool = False,
) -> Dict[str, Any]:
    """Compose the S01 portfolio swimlane contract from Planning Engine outputs."""

    execution_result = _resolve_execution_result(
        planning_engine_service=planning_engine_service,
        planning_run_id=planning_run_id,
        source_snapshot_id=source_snapshot_id,
    )
    if execution_result is None:
        return _build_s01_empty_or_unavailable_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=planning_run_id,
            source_snapshot_id=source_snapshot_id,
            is_refreshing=is_refreshing,
        )

    data = _build_projection_data(execution_result)
    daily_swimlanes = _build_daily_swimlanes(data)
    indicator_summary = _build_s01_indicator_summary(daily_swimlanes)
    screen_state = "indicator_present" if indicator_summary["indicatorPresent"] else "ready"

    return {
        "screen": dict(S01_SCREEN),
        "queryContext": {
            "planningRunId": execution_result.execution_record.planning_run_id,
            "sourceSnapshotId": execution_result.execution_record.source_snapshot_id,
        },
        "viewState": {
            "screenState": screen_state,
            "isRefreshing": is_refreshing,
            "unavailableReason": None,
        },
        "portfolioSummary": {
            "planningRunId": execution_result.execution_record.planning_run_id,
            "workflowInstanceId": execution_result.execution_record.workflow_instance_id,
            "planningContextKey": execution_result.execution_record.planning_context_key,
            "sourceSnapshotId": execution_result.execution_record.source_snapshot_id,
            "sourceArtifactId": execution_result.execution_record.source_artifact_id,
            "capacitySnapshotId": execution_result.capacity_result.capacity_snapshot_id,
            "draftScheduleId": execution_result.draft_schedule_result.draft_schedule_id,
            "scheduleState": execution_result.draft_schedule_result.schedule_state,
            "diagnosticsId": execution_result.diagnostics_result.diagnostics_id,
            "comparisonContext": execution_result.diagnostics_result.comparison_context,
            "approvedComparisonAvailable": execution_result.diagnostics_result.approved_comparison_available,
        },
        "dailySwimlanes": daily_swimlanes,
        "indicatorSummary": indicator_summary,
        "unavailableState": None,
    }


def build_d01_task_drilldown_contract(
    planning_engine_service: PlanningEngineService,
    planning_run_id: Optional[str] = None,
    source_snapshot_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_external_id: Optional[str] = None,
    task_id: Optional[str] = None,
    task_external_id: Optional[str] = None,
    date: Optional[str] = None,
    week_start_date: Optional[str] = None,
    is_refreshing: bool = False,
) -> Dict[str, Any]:
    """Compose the D01 task drill-down contract for a selected swimlane context."""

    execution_result = _resolve_execution_result(
        planning_engine_service=planning_engine_service,
        planning_run_id=planning_run_id,
        source_snapshot_id=source_snapshot_id,
    )
    if execution_result is None:
        return _build_d01_empty_or_unavailable_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=planning_run_id,
            source_snapshot_id=source_snapshot_id,
            resource_id=resource_id,
            resource_external_id=resource_external_id,
            task_id=task_id,
            task_external_id=task_external_id,
            selected_date=date,
            week_start_date=week_start_date,
            is_refreshing=is_refreshing,
        )

    data = _build_projection_data(execution_result)
    selected_tasks = _select_drilldown_tasks(
        data=data,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        task_id=task_id,
        task_external_id=task_external_id,
        selected_date=date,
        week_start_date=week_start_date,
    )
    task_details = [
        _build_drilldown_task_detail(
            task_id_value=selected_task_id,
            data=data,
            resource_id=resource_id,
            resource_external_id=resource_external_id,
            selected_date=date,
            week_start_date=week_start_date,
        )
        for selected_task_id in selected_tasks
    ]
    indicator_present = any(
        task_detail["movementIndicator"]["present"]
        or task_detail["riskIndicator"]["present"]
        or task_detail["ghostVisible"]
        for task_detail in task_details
    )

    return {
        "drawer": dict(D01_SCREEN),
        "queryContext": {
            "planningRunId": execution_result.execution_record.planning_run_id,
            "sourceSnapshotId": execution_result.execution_record.source_snapshot_id,
            "resourceId": resource_id,
            "resourceExternalId": resource_external_id,
            "taskId": task_id,
            "taskExternalId": task_external_id,
            "date": date,
            "weekStartDate": week_start_date,
        },
        "viewState": {
            "screenState": (
                "indicator_present"
                if task_details and indicator_present
                else "ready"
                if task_details
                else "empty"
            ),
            "isRefreshing": is_refreshing,
            "unavailableReason": None,
        },
        "segmentContext": {
            "resourceId": resource_id,
            "resourceExternalId": resource_external_id,
            "date": date,
            "weekStartDate": week_start_date,
            "selectedTaskCount": len(task_details),
        },
        "tasks": task_details,
        "segmentSummary": _build_d01_segment_summary(task_details),
        "unavailableState": None,
    }


def _resolve_execution_result(
    planning_engine_service: PlanningEngineService,
    planning_run_id: Optional[str],
    source_snapshot_id: Optional[str],
):
    execution_result = planning_engine_service.get_execution_result(
        planning_run_id=planning_run_id
    )
    if execution_result is None:
        return None
    if (
        source_snapshot_id is not None
        and execution_result.execution_record.source_snapshot_id != source_snapshot_id
    ):
        return None
    return execution_result


def _build_s01_empty_or_unavailable_contract(
    planning_engine_service: PlanningEngineService,
    planning_run_id: Optional[str],
    source_snapshot_id: Optional[str],
    is_refreshing: bool,
) -> Dict[str, Any]:
    unavailable_state = _build_unavailable_state(
        planning_engine_service=planning_engine_service,
        source_snapshot_id=source_snapshot_id,
    )
    screen_state = "unavailable" if unavailable_state is not None else "no_data"
    return {
        "screen": dict(S01_SCREEN),
        "queryContext": {
            "planningRunId": planning_run_id,
            "sourceSnapshotId": source_snapshot_id,
        },
        "viewState": {
            "screenState": screen_state,
            "isRefreshing": is_refreshing,
            "unavailableReason": None if unavailable_state is None else unavailable_state["reason"],
        },
        "portfolioSummary": None,
        "dailySwimlanes": [],
        "indicatorSummary": _empty_indicator_summary(),
        "unavailableState": unavailable_state,
    }


def _build_d01_empty_or_unavailable_contract(
    planning_engine_service: PlanningEngineService,
    planning_run_id: Optional[str],
    source_snapshot_id: Optional[str],
    resource_id: Optional[str],
    resource_external_id: Optional[str],
    task_id: Optional[str],
    task_external_id: Optional[str],
    selected_date: Optional[str],
    week_start_date: Optional[str],
    is_refreshing: bool,
) -> Dict[str, Any]:
    unavailable_state = _build_unavailable_state(
        planning_engine_service=planning_engine_service,
        source_snapshot_id=source_snapshot_id,
    )
    screen_state = "unavailable" if unavailable_state is not None else "no_data"
    return {
        "drawer": dict(D01_SCREEN),
        "queryContext": {
            "planningRunId": planning_run_id,
            "sourceSnapshotId": source_snapshot_id,
            "resourceId": resource_id,
            "resourceExternalId": resource_external_id,
            "taskId": task_id,
            "taskExternalId": task_external_id,
            "date": selected_date,
            "weekStartDate": week_start_date,
        },
        "viewState": {
            "screenState": screen_state,
            "isRefreshing": is_refreshing,
            "unavailableReason": None if unavailable_state is None else unavailable_state["reason"],
        },
        "segmentContext": {
            "resourceId": resource_id,
            "resourceExternalId": resource_external_id,
            "date": selected_date,
            "weekStartDate": week_start_date,
            "selectedTaskCount": 0,
        },
        "tasks": [],
        "segmentSummary": _build_d01_segment_summary([]),
        "unavailableState": unavailable_state,
    }


def _build_unavailable_state(
    planning_engine_service: PlanningEngineService,
    source_snapshot_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if source_snapshot_id is None:
        return None
    capacity_result = planning_engine_service.get_capacity_model(
        source_snapshot_id=source_snapshot_id
    )
    if capacity_result is None or capacity_result.input_readiness.runnable:
        return None
    return {
        "reason": "no_runnable_plan",
        "targetScreen": dict(S02_LINK),
        "capacityInputReadiness": {
            "state": capacity_result.input_readiness.state,
            "runnable": capacity_result.input_readiness.runnable,
            "blockingIssueCount": capacity_result.input_readiness.blocking_issue_count,
            "advisoryIssueCount": capacity_result.input_readiness.advisory_issue_count,
            "totalIssueCount": capacity_result.input_readiness.total_issue_count,
        },
    }


def _build_projection_data(execution_result) -> Dict[str, Any]:
    capacity_result = execution_result.capacity_result
    draft_result = execution_result.draft_schedule_result
    diagnostics_result = execution_result.diagnostics_result
    resource_external_ids_by_resource_id = {
        summary.resource_id: summary.resource_external_id
        for summary in capacity_result.resource_summaries
    }

    task_schedules_by_id = {
        task_schedule.task_id: task_schedule
        for task_schedule in draft_result.task_schedules
    }
    variance_by_task_id = {
        variance_fact.task_id: variance_fact
        for variance_fact in diagnostics_result.variance_facts
    }
    criticality_by_task_id = {
        criticality_fact.task_id: criticality_fact
        for criticality_fact in diagnostics_result.criticality_facts
    }
    issues_by_task_id: Dict[str, List[Any]] = defaultdict(list)
    for issue_fact in diagnostics_result.planning_issue_facts:
        issues_by_task_id[issue_fact.entity_id].append(issue_fact)

    allocations_by_resource_date: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
    allocations_by_task_id: Dict[str, List[Any]] = defaultdict(list)
    for allocation_output in draft_result.allocation_outputs:
        allocations_by_resource_date[
            (allocation_output.resource_id, allocation_output.date)
        ].append(allocation_output)
        allocations_by_task_id[allocation_output.task_id].append(allocation_output)

    ghost_by_resource_id = _build_ghost_summary_by_resource_id(task_schedules_by_id)

    return {
        "execution_result": execution_result,
        "capacity_result": capacity_result,
        "draft_result": draft_result,
        "diagnostics_result": diagnostics_result,
        "resource_external_ids_by_resource_id": resource_external_ids_by_resource_id,
        "task_schedules_by_id": task_schedules_by_id,
        "variance_by_task_id": variance_by_task_id,
        "criticality_by_task_id": criticality_by_task_id,
        "issues_by_task_id": issues_by_task_id,
        "allocations_by_resource_date": allocations_by_resource_date,
        "allocations_by_task_id": allocations_by_task_id,
        "ghost_by_resource_id": ghost_by_resource_id,
    }


def _build_ghost_summary_by_resource_id(task_schedules_by_id) -> Dict[str, Dict[str, Any]]:
    ghost_summary_by_resource_id: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "hasGhostLoad": False,
            "partiallyPlacedTaskCount": 0,
            "unschedulableTaskCount": 0,
            "ghostUnscheduledEffortHours": 0.0,
            "taskRefs": [],
        }
    )

    for task_schedule in task_schedules_by_id.values():
        if task_schedule.unscheduled_effort_hours <= 0:
            continue
        assigned_resource_ids = task_schedule.assigned_resource_ids or []
        if not assigned_resource_ids:
            continue
        per_resource_ghost_hours = round(
            task_schedule.unscheduled_effort_hours / len(assigned_resource_ids),
            4,
        )
        for resource_id in assigned_resource_ids:
            summary = ghost_summary_by_resource_id[resource_id]
            summary["hasGhostLoad"] = True
            summary["ghostUnscheduledEffortHours"] = round(
                summary["ghostUnscheduledEffortHours"] + per_resource_ghost_hours,
                4,
            )
            if task_schedule.status == "partially_scheduled":
                summary["partiallyPlacedTaskCount"] += 1
            if task_schedule.status == "unschedulable":
                summary["unschedulableTaskCount"] += 1
            summary["taskRefs"].append(
                {
                    "taskId": task_schedule.task_id,
                    "taskExternalId": task_schedule.task_external_id,
                    "taskName": task_schedule.task_name,
                    "status": task_schedule.status,
                    "ghostUnscheduledEffortHours": per_resource_ghost_hours,
                }
            )

    for summary in ghost_summary_by_resource_id.values():
        summary["taskRefs"].sort(
            key=lambda task_ref: (task_ref["taskName"], task_ref["taskExternalId"])
        )

    return ghost_summary_by_resource_id


def _build_daily_swimlanes(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    capacity_result = data["capacity_result"]
    task_schedules_by_id = data["task_schedules_by_id"]
    variance_by_task_id = data["variance_by_task_id"]
    criticality_by_task_id = data["criticality_by_task_id"]
    issues_by_task_id = data["issues_by_task_id"]
    allocations_by_resource_date = data["allocations_by_resource_date"]
    ghost_by_resource_id = data["ghost_by_resource_id"]

    grouped_outputs: Dict[str, List[Any]] = defaultdict(list)
    for daily_capacity_output in capacity_result.daily_capacity_outputs:
        grouped_outputs[daily_capacity_output.resource_id].append(daily_capacity_output)

    daily_swimlanes: List[Dict[str, Any]] = []
    for resource_id in sorted(
        grouped_outputs.keys(),
        key=lambda value: (
            grouped_outputs[value][0].resource_display_name or "",
            grouped_outputs[value][0].resource_external_id,
        ),
    ):
        resource_outputs = sorted(
            grouped_outputs[resource_id],
            key=lambda output: output.date,
        )
        daily_segments = []
        for output in resource_outputs:
            allocations = sorted(
                allocations_by_resource_date.get((resource_id, output.date), []),
                key=lambda allocation: allocation.task_external_id,
            )
            task_refs = []
            movement_task_ids: Set[str] = set()
            risk_task_ids: Set[str] = set()
            for allocation in allocations:
                task_schedule = task_schedules_by_id[allocation.task_id]
                variance_fact = variance_by_task_id.get(allocation.task_id)
                criticality_fact = criticality_by_task_id.get(allocation.task_id)
                issue_facts = issues_by_task_id.get(allocation.task_id, [])
                movement_present = _movement_indicator_present(variance_fact)
                risk_present = _risk_indicator_present(criticality_fact, issue_facts)
                if movement_present:
                    movement_task_ids.add(allocation.task_id)
                if risk_present:
                    risk_task_ids.add(allocation.task_id)
                task_refs.append(
                    {
                        "taskId": task_schedule.task_id,
                        "taskExternalId": task_schedule.task_external_id,
                        "taskName": task_schedule.task_name,
                        "allocatedHours": allocation.allocated_hours,
                        "status": task_schedule.status,
                        "ghostVisible": task_schedule.unscheduled_effort_hours > 0,
                        "movementIndicatorPresent": movement_present,
                        "riskIndicatorPresent": risk_present,
                    }
                )
            task_refs.sort(key=lambda task_ref: (task_ref["taskName"], task_ref["taskExternalId"]))
            allocated_hours = round(
                sum(allocation.allocated_hours for allocation in allocations),
                4,
            )
            productive_capacity_hours = output.productive_capacity_hours
            overload_hours = round(
                max(allocated_hours - productive_capacity_hours, 0.0),
                4,
            )
            free_capacity_hours = round(
                max(productive_capacity_hours - allocated_hours, 0.0),
                4,
            )
            daily_segments.append(
                {
                    "date": output.date,
                    "weekStartDate": _week_start_date(output.date),
                    "productiveCapacityHours": productive_capacity_hours,
                    "allocatedHours": allocated_hours,
                    "utilizationRatio": _safe_ratio(
                        numerator=allocated_hours,
                        denominator=productive_capacity_hours,
                    ),
                    "overloadHours": overload_hours,
                    "freeCapacityHours": free_capacity_hours,
                    "activeAssignmentCount": output.active_assignment_count,
                    "taskCount": len(task_refs),
                    "movementIndicatorCount": len(movement_task_ids),
                    "riskIndicatorCount": len(risk_task_ids),
                    "hasGhostLoad": any(task_ref["ghostVisible"] for task_ref in task_refs),
                    "taskRefs": task_refs,
                }
            )

        daily_swimlanes.append(
            {
                "resourceId": resource_id,
                "resourceExternalId": resource_outputs[0].resource_external_id,
                "resourceDisplayName": resource_outputs[0].resource_display_name,
                "totalProductiveCapacityHours": round(
                    sum(
                        segment["productiveCapacityHours"] for segment in daily_segments
                    ),
                    4,
                ),
                "totalAllocatedHours": round(
                    sum(segment["allocatedHours"] for segment in daily_segments),
                    4,
                ),
                "ghostSummary": ghost_by_resource_id.get(
                    resource_id,
                    {
                        "hasGhostLoad": False,
                        "partiallyPlacedTaskCount": 0,
                        "unschedulableTaskCount": 0,
                        "ghostUnscheduledEffortHours": 0.0,
                        "taskRefs": [],
                    },
                ),
                "laneIndicators": {
                    "movementIndicatorCount": len(
                        {
                            task_ref["taskId"]
                            for segment in daily_segments
                            for task_ref in segment["taskRefs"]
                            if task_ref["movementIndicatorPresent"]
                        }
                    ),
                    "riskIndicatorCount": len(
                        {
                            task_ref["taskId"]
                            for segment in daily_segments
                            for task_ref in segment["taskRefs"]
                            if task_ref["riskIndicatorPresent"]
                        }
                    ),
                    "overloadedDayCount": len(
                        [
                            segment
                            for segment in daily_segments
                            if segment["overloadHours"] > 0
                        ]
                    ),
                    "freeCapacityDayCount": len(
                        [
                            segment
                            for segment in daily_segments
                            if segment["freeCapacityHours"] > 0
                        ]
                    ),
                },
                "dailySegments": daily_segments,
                "weeklyRollups": _build_weekly_rollups_from_daily_segments(daily_segments),
            }
        )

    return daily_swimlanes


def _build_weekly_rollups_from_daily_segments(
    daily_segments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    segments_by_week: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for segment in daily_segments:
        segments_by_week[segment["weekStartDate"]].append(segment)

    weekly_rollups = []
    for week_start_date in sorted(segments_by_week.keys()):
        weekly_segments = sorted(
            segments_by_week[week_start_date],
            key=lambda segment: segment["date"],
        )
        weekly_rollups.append(
            {
                "weekStartDate": week_start_date,
                "dayCount": len(weekly_segments),
                "productiveCapacityHours": round(
                    sum(segment["productiveCapacityHours"] for segment in weekly_segments),
                    4,
                ),
                "allocatedHours": round(
                    sum(segment["allocatedHours"] for segment in weekly_segments),
                    4,
                ),
                "overloadHours": round(
                    sum(segment["overloadHours"] for segment in weekly_segments),
                    4,
                ),
                "freeCapacityHours": round(
                    sum(segment["freeCapacityHours"] for segment in weekly_segments),
                    4,
                ),
                "utilizationRatio": _safe_ratio(
                    numerator=sum(segment["allocatedHours"] for segment in weekly_segments),
                    denominator=sum(
                        segment["productiveCapacityHours"] for segment in weekly_segments
                    ),
                ),
                "taskCount": len(
                    {
                        task_ref["taskId"]
                        for segment in weekly_segments
                        for task_ref in segment["taskRefs"]
                    }
                ),
                "movementIndicatorCount": len(
                    {
                        task_ref["taskId"]
                        for segment in weekly_segments
                        for task_ref in segment["taskRefs"]
                        if task_ref["movementIndicatorPresent"]
                    }
                ),
                "riskIndicatorCount": len(
                    {
                        task_ref["taskId"]
                        for segment in weekly_segments
                        for task_ref in segment["taskRefs"]
                        if task_ref["riskIndicatorPresent"]
                    }
                ),
                "hasGhostLoad": any(
                    segment["hasGhostLoad"] for segment in weekly_segments
                ),
            }
        )
    return weekly_rollups


def _build_s01_indicator_summary(daily_swimlanes: List[Dict[str, Any]]) -> Dict[str, Any]:
    movement_task_ids = set()
    risk_task_ids = set()
    overloaded_segment_count = 0
    free_capacity_segment_count = 0
    ghost_lane_count = 0

    for swimlane in daily_swimlanes:
        if swimlane["ghostSummary"]["hasGhostLoad"]:
            ghost_lane_count += 1
        for segment in swimlane["dailySegments"]:
            if segment["overloadHours"] > 0:
                overloaded_segment_count += 1
            if segment["freeCapacityHours"] > 0:
                free_capacity_segment_count += 1
            for task_ref in segment["taskRefs"]:
                if task_ref["movementIndicatorPresent"]:
                    movement_task_ids.add(task_ref["taskId"])
                if task_ref["riskIndicatorPresent"]:
                    risk_task_ids.add(task_ref["taskId"])

    indicator_present = bool(
        movement_task_ids
        or risk_task_ids
        or ghost_lane_count
        or overloaded_segment_count
    )

    return {
        "indicatorPresent": indicator_present,
        "movementIndicatorTaskCount": len(movement_task_ids),
        "riskIndicatorTaskCount": len(risk_task_ids),
        "ghostLaneCount": ghost_lane_count,
        "overloadedSegmentCount": overloaded_segment_count,
        "freeCapacitySegmentCount": free_capacity_segment_count,
    }


def _empty_indicator_summary() -> Dict[str, Any]:
    return {
        "indicatorPresent": False,
        "movementIndicatorTaskCount": 0,
        "riskIndicatorTaskCount": 0,
        "ghostLaneCount": 0,
        "overloadedSegmentCount": 0,
        "freeCapacitySegmentCount": 0,
    }


def _select_drilldown_tasks(
    data: Dict[str, Any],
    resource_id: Optional[str],
    resource_external_id: Optional[str],
    task_id: Optional[str],
    task_external_id: Optional[str],
    selected_date: Optional[str],
    week_start_date: Optional[str],
) -> List[str]:
    task_schedules_by_id = data["task_schedules_by_id"]
    selected_task_ids: Set[str] = set()

    if task_id is not None:
        if task_id in task_schedules_by_id and _selected_task_matches_context(
            selected_task_schedule=task_schedules_by_id[task_id],
            data=data,
            resource_id=resource_id,
            resource_external_id=resource_external_id,
            selected_date=selected_date,
            week_start_date=week_start_date,
        ):
            selected_task_ids.add(task_id)
    elif task_external_id is not None:
        for task_schedule in task_schedules_by_id.values():
            if (
                task_schedule.task_external_id == task_external_id
                and _selected_task_matches_context(
                    selected_task_schedule=task_schedule,
                    data=data,
                    resource_id=resource_id,
                    resource_external_id=resource_external_id,
                    selected_date=selected_date,
                    week_start_date=week_start_date,
                )
            ):
                selected_task_ids.add(task_schedule.task_id)
    else:
        for task_schedule in task_schedules_by_id.values():
            if not _task_matches_resource_context(
                task_schedule=task_schedule,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
                resource_external_ids_by_resource_id=data["resource_external_ids_by_resource_id"],
            ):
                continue
            if _task_matches_context(
                task_schedule=task_schedule,
                allocations=data["allocations_by_task_id"].get(task_schedule.task_id, []),
                selected_date=selected_date,
                week_start_date=week_start_date,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
            ):
                selected_task_ids.add(task_schedule.task_id)

    return sorted(
        selected_task_ids,
        key=lambda selected_task_id: (
            task_schedules_by_id[selected_task_id].task_name,
            task_schedules_by_id[selected_task_id].task_external_id,
        ),
    )


def _selected_task_matches_context(
    selected_task_schedule,
    data: Dict[str, Any],
    resource_id: Optional[str],
    resource_external_id: Optional[str],
    selected_date: Optional[str],
    week_start_date: Optional[str],
) -> bool:
    return _task_matches_resource_context(
        task_schedule=selected_task_schedule,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        resource_external_ids_by_resource_id=data["resource_external_ids_by_resource_id"],
    ) and _task_matches_context(
        task_schedule=selected_task_schedule,
        allocations=data["allocations_by_task_id"].get(selected_task_schedule.task_id, []),
        selected_date=selected_date,
        week_start_date=week_start_date,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
    )


def _task_matches_resource_context(
    task_schedule,
    resource_id: Optional[str],
    resource_external_id: Optional[str],
    resource_external_ids_by_resource_id: Dict[str, str],
) -> bool:
    if resource_id is None and resource_external_id is None:
        return True
    assigned_resource_ids = set(task_schedule.assigned_resource_ids or [])
    if resource_id is not None and resource_id not in assigned_resource_ids:
        return False
    if resource_external_id is not None and resource_external_id not in {
        resource_external_ids_by_resource_id.get(assigned_resource_id)
        for assigned_resource_id in assigned_resource_ids
    }:
        return False
    return True


def _task_matches_context(
    task_schedule,
    allocations: List[Any],
    selected_date: Optional[str],
    week_start_date: Optional[str],
    resource_id: Optional[str],
    resource_external_id: Optional[str],
) -> bool:
    filtered_allocations = [
        allocation
        for allocation in allocations
        if (resource_id is None or allocation.resource_id == resource_id)
        and (
            resource_external_id is None
            or allocation.resource_external_id == resource_external_id
        )
    ]
    if selected_date is None and week_start_date is None:
        return bool(filtered_allocations or task_schedule.unscheduled_effort_hours > 0)
    if selected_date is not None:
        if any(allocation.date == selected_date for allocation in filtered_allocations):
            return True
        return (
            task_schedule.unscheduled_effort_hours > 0
            and _task_date_matches(task_schedule, selected_date)
        )
    if week_start_date is not None:
        week_dates = {
            (date.fromisoformat(week_start_date) + timedelta(days=offset)).isoformat()
            for offset in range(7)
        }
        if any(allocation.date in week_dates for allocation in filtered_allocations):
            return True
        return task_schedule.unscheduled_effort_hours > 0 and any(
            _task_date_matches(task_schedule, candidate_date)
            for candidate_date in week_dates
        )
    return False


def _task_date_matches(task_schedule, candidate_date: str) -> bool:
    return candidate_date in {
        value
        for value in (
            task_schedule.requested_start_date,
            task_schedule.requested_due_date,
            task_schedule.scheduled_start_date,
            task_schedule.scheduled_end_date,
        )
        if value is not None
    }


def _build_drilldown_task_detail(
    task_id_value: str,
    data: Dict[str, Any],
    resource_id: Optional[str],
    resource_external_id: Optional[str],
    selected_date: Optional[str],
    week_start_date: Optional[str],
) -> Dict[str, Any]:
    task_schedule = data["task_schedules_by_id"][task_id_value]
    variance_fact = data["variance_by_task_id"].get(task_id_value)
    criticality_fact = data["criticality_by_task_id"].get(task_id_value)
    issue_facts = data["issues_by_task_id"].get(task_id_value, [])
    allocations = [
        allocation
        for allocation in data["allocations_by_task_id"].get(task_id_value, [])
        if (resource_id is None or allocation.resource_id == resource_id)
        and (
            resource_external_id is None
            or allocation.resource_external_id == resource_external_id
        )
        and (
            selected_date is None or allocation.date == selected_date
        )
        and (
            week_start_date is None
            or _week_start_date(allocation.date) == week_start_date
        )
    ]
    allocations.sort(key=lambda allocation: allocation.date)

    return {
        "taskId": task_schedule.task_id,
        "taskExternalId": task_schedule.task_external_id,
        "taskName": task_schedule.task_name,
        "projectId": task_schedule.project_id,
        "projectExternalId": task_schedule.project_external_id,
        "status": task_schedule.status,
        "requestedStartDate": task_schedule.requested_start_date,
        "requestedDueDate": task_schedule.requested_due_date,
        "scheduledStartDate": task_schedule.scheduled_start_date,
        "scheduledEndDate": task_schedule.scheduled_end_date,
        "requiredEffortHours": task_schedule.required_effort_hours,
        "scheduledEffortHours": task_schedule.scheduled_effort_hours,
        "unscheduledEffortHours": task_schedule.unscheduled_effort_hours,
        "ghostVisible": task_schedule.unscheduled_effort_hours > 0,
        "contextAllocatedHours": round(
            sum(allocation.allocated_hours for allocation in allocations),
            4,
        ),
        "allocations": [
            {
                "date": allocation.date,
                "allocatedHours": allocation.allocated_hours,
                "resourceId": allocation.resource_id,
                "resourceExternalId": allocation.resource_external_id,
            }
            for allocation in allocations
        ],
        "movementIndicator": {
            "present": _movement_indicator_present(variance_fact),
            "slippageDetected": False if variance_fact is None else variance_fact.slippage_detected,
            "startVarianceDays": None if variance_fact is None else variance_fact.start_variance_days,
            "finishVarianceDays": None if variance_fact is None else variance_fact.finish_variance_days,
        },
        "riskIndicator": {
            "present": _risk_indicator_present(criticality_fact, issue_facts),
            "critical": False if criticality_fact is None else criticality_fact.critical,
            "zeroSlack": False if criticality_fact is None else criticality_fact.zero_slack,
            "blockedByUnscheduledPredecessor": (
                False
                if criticality_fact is None
                else criticality_fact.blocked_by_unscheduled_predecessor
            ),
            "issueCount": len(issue_facts),
            "blockingIssueCount": len(
                [issue_fact for issue_fact in issue_facts if issue_fact.severity == "blocking"]
            ),
            "advisoryIssueCount": len(
                [issue_fact for issue_fact in issue_facts if issue_fact.severity != "blocking"]
            ),
        },
        "planningIssues": [
            {
                "severity": issue_fact.severity,
                "code": issue_fact.code,
                "message": issue_fact.message,
            }
            for issue_fact in sorted(
                issue_facts,
                key=lambda issue_fact: (issue_fact.severity, issue_fact.code),
            )
        ],
    }


def _build_d01_segment_summary(task_details: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "taskCount": len(task_details),
        "allocatedHours": round(
            sum(task_detail["contextAllocatedHours"] for task_detail in task_details),
            4,
        ),
        "ghostTaskCount": len(
            [task_detail for task_detail in task_details if task_detail["ghostVisible"]]
        ),
        "movementIndicatorCount": len(
            [
                task_detail
                for task_detail in task_details
                if task_detail["movementIndicator"]["present"]
            ]
        ),
        "riskIndicatorCount": len(
            [
                task_detail
                for task_detail in task_details
                if task_detail["riskIndicator"]["present"]
            ]
        ),
    }


def _movement_indicator_present(variance_fact) -> bool:
    if variance_fact is None:
        return False
    return bool(
        variance_fact.slippage_detected
        or (
            variance_fact.start_variance_days is not None
            and variance_fact.start_variance_days > 0
        )
        or (
            variance_fact.finish_variance_days is not None
            and variance_fact.finish_variance_days > 0
        )
    )


def _risk_indicator_present(criticality_fact, issue_facts: Iterable[Any]) -> bool:
    return bool(
        (criticality_fact is not None and criticality_fact.critical)
        or list(issue_facts)
    )


def _week_start_date(date_string: str) -> str:
    current_date = date.fromisoformat(date_string)
    return (current_date - timedelta(days=current_date.weekday())).isoformat()


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
