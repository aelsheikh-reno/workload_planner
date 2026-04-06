"""S03 — Resource Detail read-model composition adapter."""

from typing import Any, Dict, List, Optional, Set

from services.decision_support_service import (
    DecisionSupportService,
    RECOMMENDATION_CONTEXT_STATE_NOT_AVAILABLE,
    RECOMMENDATION_FRESHNESS_NOT_GENERATED,
)
from services.planning_engine_service.service import PlanningEngineService

from .s01_portfolio_contract import (
    _build_projection_data,
    _build_unavailable_state,
    _movement_indicator_present,
    _resolve_execution_result,
    _risk_indicator_present,
    _safe_ratio,
    _week_start_date,
)


S03_SCREEN = {"id": "S03", "label": "Resource Detail"}
S01_LINK = {"id": "S01", "label": "Portfolio Swimlane Home"}
S04_LINK = {"id": "S04", "label": "Delta Review"}
S05_LINK = {"id": "S05", "label": "Planning Warnings Workspace"}

WARNING_HEAVY_THRESHOLD = 3


def build_s03_resource_detail_contract(
    planning_engine_service: PlanningEngineService,
    decision_support_service: Optional[DecisionSupportService] = None,
    planning_run_id: Optional[str] = None,
    source_snapshot_id: Optional[str] = None,
    planning_context_key: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_external_id: Optional[str] = None,
    origin_screen_id: Optional[str] = "S01",
    is_loading: bool = False,
    is_refreshing: bool = False,
    access_restricted: bool = False,
    access_restricted_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose the S03 Resource Detail contract from Planning Engine and Decision Support."""

    if access_restricted:
        return _build_access_restricted_contract(
            planning_run_id=planning_run_id,
            source_snapshot_id=source_snapshot_id,
            planning_context_key=planning_context_key,
            resource_id=resource_id,
            resource_external_id=resource_external_id,
            origin_screen_id=origin_screen_id,
            is_loading=is_loading,
            is_refreshing=is_refreshing,
            access_restricted_reason=access_restricted_reason,
        )

    execution_result = _resolve_execution_result(
        planning_engine_service=planning_engine_service,
        planning_run_id=planning_run_id,
        source_snapshot_id=source_snapshot_id,
    )
    if execution_result is None:
        return _build_empty_or_unavailable_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=planning_run_id,
            source_snapshot_id=source_snapshot_id,
            planning_context_key=planning_context_key,
            resource_id=resource_id,
            resource_external_id=resource_external_id,
            origin_screen_id=origin_screen_id,
            is_loading=is_loading,
            is_refreshing=is_refreshing,
        )

    resolved_planning_context_key = execution_result.execution_record.planning_context_key
    resolved_source_snapshot_id = execution_result.execution_record.source_snapshot_id
    data = _build_projection_data(execution_result)
    resource_context = _resolve_resource_context(
        data=data,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
    )
    if resource_context is None:
        return _build_empty_or_unavailable_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            source_snapshot_id=resolved_source_snapshot_id,
            planning_context_key=resolved_planning_context_key,
            resource_id=resource_id,
            resource_external_id=resource_external_id,
            origin_screen_id=origin_screen_id,
            is_loading=is_loading,
            is_refreshing=is_refreshing,
        )

    workload_timeline = _build_workload_timeline(
        data=data,
        resource_context=resource_context,
    )
    assigned_work_queue = _build_assigned_work_queue(
        data=data,
        resource_context=resource_context,
    )
    warning_trust_context = _build_warning_trust_context(
        decision_support_service=decision_support_service,
        planning_context_key=resolved_planning_context_key,
        source_snapshot_id=resolved_source_snapshot_id,
        resource_context=resource_context,
        assigned_work_queue=assigned_work_queue,
    )
    recommendation_context = _build_recommendation_context(
        decision_support_service=decision_support_service,
        planning_context_key=resolved_planning_context_key,
        source_snapshot_id=resolved_source_snapshot_id,
        resource_context=resource_context,
        warning_trust_context=warning_trust_context,
    )
    resource_summary = _build_resource_summary(
        resource_context=resource_context,
        workload_timeline=workload_timeline,
        assigned_work_queue=assigned_work_queue,
        warning_trust_context=warning_trust_context,
    )
    navigation = _build_navigation(
        planning_run_id=execution_result.execution_record.planning_run_id,
        planning_context_key=resolved_planning_context_key,
        source_snapshot_id=resolved_source_snapshot_id,
        resource_context=resource_context,
        recommendation_context=recommendation_context,
        warning_trust_context=warning_trust_context,
        origin_screen_id=origin_screen_id,
    )

    return {
        "screen": dict(S03_SCREEN),
        "queryContext": {
            "planningRunId": execution_result.execution_record.planning_run_id,
            "planningContextKey": resolved_planning_context_key,
            "sourceSnapshotId": resolved_source_snapshot_id,
            "resourceId": resource_context["resourceId"],
            "resourceExternalId": resource_context["resourceExternalId"],
            "originScreenId": origin_screen_id,
        },
        "viewState": _build_view_state(
            resource_summary=resource_summary,
            recommendation_context=recommendation_context,
            warning_trust_context=warning_trust_context,
            is_loading=is_loading,
            is_refreshing=is_refreshing,
        ),
        "resourceSummary": resource_summary,
        "workloadTimeline": workload_timeline,
        "assignedWorkQueue": assigned_work_queue,
        "recommendationContext": recommendation_context,
        "warningTrustContext": warning_trust_context,
        "navigation": navigation,
        "unavailableState": None,
    }


def _build_access_restricted_contract(
    planning_run_id: Optional[str],
    source_snapshot_id: Optional[str],
    planning_context_key: Optional[str],
    resource_id: Optional[str],
    resource_external_id: Optional[str],
    origin_screen_id: Optional[str],
    is_loading: bool,
    is_refreshing: bool,
    access_restricted_reason: Optional[str],
) -> Dict[str, Any]:
    return {
        "screen": dict(S03_SCREEN),
        "queryContext": {
            "planningRunId": planning_run_id,
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": source_snapshot_id,
            "resourceId": resource_id,
            "resourceExternalId": resource_external_id,
            "originScreenId": origin_screen_id,
        },
        "viewState": {
            "screenState": "access_restricted",
            "isLoading": is_loading,
            "isRefreshing": is_refreshing,
            "accessRestricted": True,
            "accessRestrictedReason": access_restricted_reason or "access_denied",
            "unavailableReason": None,
        },
        "resourceSummary": None,
        "workloadTimeline": [],
        "assignedWorkQueue": [],
        "recommendationContext": _empty_recommendation_context(),
        "warningTrustContext": _empty_warning_trust_context(),
        "navigation": _build_navigation(
            planning_run_id=planning_run_id,
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
            resource_context={
                "resourceId": resource_id,
                "resourceExternalId": resource_external_id,
                "resourceDisplayName": None,
            },
            recommendation_context=_empty_recommendation_context(),
            warning_trust_context=_empty_warning_trust_context(),
            origin_screen_id=origin_screen_id,
        ),
        "unavailableState": None,
    }


def _build_empty_or_unavailable_contract(
    planning_engine_service: PlanningEngineService,
    planning_run_id: Optional[str],
    source_snapshot_id: Optional[str],
    planning_context_key: Optional[str],
    resource_id: Optional[str],
    resource_external_id: Optional[str],
    origin_screen_id: Optional[str],
    is_loading: bool,
    is_refreshing: bool,
) -> Dict[str, Any]:
    unavailable_state = _build_unavailable_state(
        planning_engine_service=planning_engine_service,
        source_snapshot_id=source_snapshot_id,
    )
    screen_state = "unavailable" if unavailable_state is not None else "no_data"
    return {
        "screen": dict(S03_SCREEN),
        "queryContext": {
            "planningRunId": planning_run_id,
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": source_snapshot_id,
            "resourceId": resource_id,
            "resourceExternalId": resource_external_id,
            "originScreenId": origin_screen_id,
        },
        "viewState": {
            "screenState": screen_state,
            "isLoading": is_loading,
            "isRefreshing": is_refreshing,
            "accessRestricted": False,
            "accessRestrictedReason": None,
            "unavailableReason": None if unavailable_state is None else unavailable_state["reason"],
        },
        "resourceSummary": None,
        "workloadTimeline": [],
        "assignedWorkQueue": [],
        "recommendationContext": _empty_recommendation_context(),
        "warningTrustContext": _empty_warning_trust_context(),
        "navigation": _build_navigation(
            planning_run_id=planning_run_id,
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
            resource_context={
                "resourceId": resource_id,
                "resourceExternalId": resource_external_id,
                "resourceDisplayName": None,
            },
            recommendation_context=_empty_recommendation_context(),
            warning_trust_context=_empty_warning_trust_context(),
            origin_screen_id=origin_screen_id,
        ),
        "unavailableState": unavailable_state,
    }


def _resolve_resource_context(
    data: Dict[str, Any],
    resource_id: Optional[str],
    resource_external_id: Optional[str],
) -> Optional[Dict[str, Optional[str]]]:
    summaries = data["capacity_result"].resource_summaries
    if resource_id is not None:
        for summary in summaries:
            if summary.resource_id == resource_id:
                return {
                    "resourceId": summary.resource_id,
                    "resourceExternalId": summary.resource_external_id,
                    "resourceDisplayName": summary.resource_display_name,
                }
        return None
    if resource_external_id is not None:
        for summary in summaries:
            if summary.resource_external_id == resource_external_id:
                return {
                    "resourceId": summary.resource_id,
                    "resourceExternalId": summary.resource_external_id,
                    "resourceDisplayName": summary.resource_display_name,
                }
        return None
    if len(summaries) == 1:
        summary = summaries[0]
        return {
            "resourceId": summary.resource_id,
            "resourceExternalId": summary.resource_external_id,
            "resourceDisplayName": summary.resource_display_name,
        }
    return None


def _build_workload_timeline(
    data: Dict[str, Any],
    resource_context: Dict[str, Optional[str]],
) -> List[Dict[str, Any]]:
    resource_id = resource_context["resourceId"]
    outputs = sorted(
        [
            output
            for output in data["capacity_result"].daily_capacity_outputs
            if output.resource_id == resource_id
        ],
        key=lambda output: output.date,
    )
    timeline = []
    for output in outputs:
        allocations = sorted(
            data["allocations_by_resource_date"].get((resource_id, output.date), []),
            key=lambda allocation: allocation.task_external_id,
        )
        task_refs = []
        movement_task_ids: Set[str] = set()
        risk_task_ids: Set[str] = set()
        for allocation in allocations:
            task_schedule = data["task_schedules_by_id"][allocation.task_id]
            variance_fact = data["variance_by_task_id"].get(allocation.task_id)
            criticality_fact = data["criticality_by_task_id"].get(allocation.task_id)
            issue_facts = data["issues_by_task_id"].get(allocation.task_id, [])
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
                }
            )
        allocated_hours = round(
            sum(allocation.allocated_hours for allocation in allocations),
            4,
        )
        overload_hours = round(
            max(allocated_hours - output.productive_capacity_hours, 0.0),
            4,
        )
        free_capacity_hours = round(
            max(output.productive_capacity_hours - allocated_hours, 0.0),
            4,
        )
        timeline.append(
            {
                "date": output.date,
                "weekStartDate": _week_start_date(output.date),
                "productiveCapacityHours": output.productive_capacity_hours,
                "allocatedHours": allocated_hours,
                "utilizationRatio": _safe_ratio(
                    numerator=allocated_hours,
                    denominator=output.productive_capacity_hours,
                ),
                "overloadHours": overload_hours,
                "freeCapacityHours": free_capacity_hours,
                "activeAssignmentCount": output.active_assignment_count,
                "taskCount": len(task_refs),
                "hasGhostLoad": any(task_ref["ghostVisible"] for task_ref in task_refs),
                "movementIndicatorCount": len(movement_task_ids),
                "riskIndicatorCount": len(risk_task_ids),
                "taskRefs": task_refs,
            }
        )
    return timeline


def _build_assigned_work_queue(
    data: Dict[str, Any],
    resource_context: Dict[str, Optional[str]],
) -> List[Dict[str, Any]]:
    resource_id = resource_context["resourceId"]
    resource_external_id = resource_context["resourceExternalId"]
    queue_items = []
    for task_schedule in data["draft_result"].task_schedules:
        if resource_id not in set(task_schedule.assigned_resource_ids or []):
            continue
        allocations = sorted(
            [
                allocation
                for allocation in data["allocations_by_task_id"].get(task_schedule.task_id, [])
                if allocation.resource_id == resource_id
            ],
            key=lambda allocation: allocation.date,
        )
        variance_fact = data["variance_by_task_id"].get(task_schedule.task_id)
        criticality_fact = data["criticality_by_task_id"].get(task_schedule.task_id)
        issue_facts = data["issues_by_task_id"].get(task_schedule.task_id, [])
        queue_items.append(
            {
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
                "queueAllocatedHours": round(
                    sum(allocation.allocated_hours for allocation in allocations),
                    4,
                ),
                "ghostVisible": task_schedule.unscheduled_effort_hours > 0,
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
                    "slippageDetected": (
                        False if variance_fact is None else variance_fact.slippage_detected
                    ),
                    "startVarianceDays": (
                        None if variance_fact is None else variance_fact.start_variance_days
                    ),
                    "finishVarianceDays": (
                        None if variance_fact is None else variance_fact.finish_variance_days
                    ),
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
                "resourceId": resource_id,
                "resourceExternalId": resource_external_id,
            }
        )
    queue_items.sort(
        key=lambda item: (
            item["scheduledStartDate"] or item["requestedStartDate"] or "",
            item["taskName"],
            item["taskExternalId"],
        )
    )
    return queue_items


def _build_warning_trust_context(
    decision_support_service: Optional[DecisionSupportService],
    planning_context_key: Optional[str],
    source_snapshot_id: Optional[str],
    resource_context: Dict[str, Optional[str]],
    assigned_work_queue: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if decision_support_service is None:
        return _empty_warning_trust_context()

    state = decision_support_service.get_screen_warning_trust_state(
        screen_id="S03",
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
    )
    if state is None:
        return _empty_warning_trust_context()

    task_ids = {item["taskId"] for item in assigned_work_queue}
    task_external_ids = {item["taskExternalId"] for item in assigned_work_queue}
    relevant_signals = [
        signal
        for signal in state.signals
        if _signal_matches_resource_context(
            signal=signal,
            resource_context=resource_context,
            task_ids=task_ids,
            task_external_ids=task_external_ids,
        )
    ]
    items = sorted(
        [_build_warning_item(signal) for signal in relevant_signals],
        key=_warning_item_sort_key,
    )
    return {
        "interpretationId": state.interpretation_id,
        "activeSignalCount": len(items),
        "advisorySignalCount": len(
            [item for item in items if item["classification"] == "advisory"]
        ),
        "blockingSignalCount": len(
            [item for item in items if item["classification"] == "blocking"]
        ),
        "warningSignalCount": len(
            [item for item in items if item["signalType"] == "warning"]
        ),
        "trustSignalCount": len(
            [item for item in items if item["signalType"] == "trust"]
        ),
        "trustLimitedSignalCount": len(
            [item for item in items if item["classification"] == "trust_limited"]
        ),
        "warningHeavy": len(items) >= WARNING_HEAVY_THRESHOLD,
        "signals": items,
    }


def _signal_matches_resource_context(
    signal,
    resource_context: Dict[str, Optional[str]],
    task_ids: Set[str],
    task_external_ids: Set[str],
) -> bool:
    if signal.entity_type == "resource":
        if resource_context["resourceId"] is not None and signal.entity_id is not None:
            if signal.entity_id == resource_context["resourceId"]:
                return True
        return signal.entity_external_id == resource_context["resourceExternalId"]
    if signal.entity_type == "task":
        if signal.entity_id is not None and signal.entity_id in task_ids:
            return True
        return signal.entity_external_id in task_external_ids
    return False


def _build_warning_item(signal) -> Dict[str, Any]:
    classification = _derive_warning_classification(signal)
    return {
        "signalId": signal.signal_id,
        "classification": classification,
        "signalType": signal.signal_type,
        "severity": signal.severity,
        "code": signal.code,
        "message": signal.message,
        "interpretationCategory": signal.interpretation_category,
        "sourceIssueService": signal.source_issue_service or "Decision Support Service",
        "entityType": signal.entity_type,
        "entityId": signal.entity_id,
        "entityExternalId": signal.entity_external_id,
        "trustAffected": classification == "trust_limited",
    }


def _derive_warning_classification(signal) -> str:
    if signal.blocking or not signal.advisory:
        return "blocking"
    if signal.signal_type == "trust" or signal.interpretation_category == "trust_limited":
        return "trust_limited"
    return "advisory"


def _build_recommendation_context(
    decision_support_service: Optional[DecisionSupportService],
    planning_context_key: Optional[str],
    source_snapshot_id: Optional[str],
    resource_context: Dict[str, Optional[str]],
    warning_trust_context: Dict[str, Any],
) -> Dict[str, Any]:
    resource_external_id = resource_context["resourceExternalId"]
    if decision_support_service is None or resource_external_id is None:
        return _empty_recommendation_context(
            trust_affected=warning_trust_context["trustLimitedSignalCount"] > 0
        )

    context = decision_support_service.get_resource_recommendation_context(
        resource_external_id=resource_external_id,
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
    )
    if context is None:
        return _empty_recommendation_context(
            trust_affected=warning_trust_context["trustLimitedSignalCount"] > 0
        )

    trust_limited_task_ids = {
        signal["entityId"]
        for signal in warning_trust_context["signals"]
        if signal["classification"] == "trust_limited" and signal["entityType"] == "task"
    }
    trust_limited_task_external_ids = {
        signal["entityExternalId"]
        for signal in warning_trust_context["signals"]
        if signal["classification"] == "trust_limited"
        and signal["entityType"] == "task"
        and signal["entityExternalId"] is not None
    }
    resource_trust_limited = any(
        signal["classification"] == "trust_limited"
        and signal["entityType"] == "resource"
        for signal in warning_trust_context["signals"]
    )

    items = []
    for recommendation in context.recommendations:
        trust_affected = resource_trust_limited or bool(
            set(recommendation.affected_task_ids) & trust_limited_task_ids
        ) or bool(
            set(recommendation.affected_task_external_ids)
            & trust_limited_task_external_ids
        )
        items.append(
            {
                "recommendationId": recommendation.recommendation_id,
                "title": recommendation.title,
                "summary": recommendation.summary,
                "effectSummary": recommendation.effect_summary,
                "actionFamily": recommendation.action_family,
                "priorityRank": recommendation.priority_rank,
                "requiresReviewHandoff": recommendation.requires_review,
                "rationale": recommendation.rationale,
                "affectedTaskIds": recommendation.affected_task_ids,
                "affectedTaskExternalIds": recommendation.affected_task_external_ids,
                "originContext": (
                    recommendation.origin_context.to_dict()
                    if recommendation.origin_context is not None
                    else None
                ),
                "trustAffected": trust_affected,
                "reviewNavigation": (
                    {
                        "screen": dict(S04_LINK),
                        "reason": "formal_review_required",
                    }
                    if recommendation.requires_review
                    else None
                ),
            }
        )

    return {
        "contextId": context.context_id,
        "state": context.state,
        "freshnessStatus": context.freshness_status,
        "actionableRecommendationCount": context.actionable_recommendation_count,
        "totalRecommendationCount": context.total_recommendation_count,
        "trustAffected": any(item["trustAffected"] for item in items)
        or warning_trust_context["trustLimitedSignalCount"] > 0,
        "trustAffectedRecommendationCount": len(
            [item for item in items if item["trustAffected"]]
        ),
        "items": items,
    }


def _build_resource_summary(
    resource_context: Dict[str, Optional[str]],
    workload_timeline: List[Dict[str, Any]],
    assigned_work_queue: List[Dict[str, Any]],
    warning_trust_context: Dict[str, Any],
) -> Dict[str, Any]:
    total_allocated_hours = round(
        sum(segment["allocatedHours"] for segment in workload_timeline),
        4,
    )
    total_productive_capacity_hours = round(
        sum(segment["productiveCapacityHours"] for segment in workload_timeline),
        4,
    )
    return {
        "resourceId": resource_context["resourceId"],
        "resourceExternalId": resource_context["resourceExternalId"],
        "resourceDisplayName": resource_context["resourceDisplayName"],
        "totalAllocatedHours": total_allocated_hours,
        "totalProductiveCapacityHours": total_productive_capacity_hours,
        "utilizationRatio": _safe_ratio(
            numerator=total_allocated_hours,
            denominator=total_productive_capacity_hours,
        ),
        "scheduledTaskCount": len(assigned_work_queue),
        "ghostTaskCount": len(
            [item for item in assigned_work_queue if item["ghostVisible"]]
        ),
        "ghostUnscheduledEffortHours": round(
            sum(item["unscheduledEffortHours"] for item in assigned_work_queue),
            4,
        ),
        "overloadedDayCount": len(
            [segment for segment in workload_timeline if segment["overloadHours"] > 0]
        ),
        "freeCapacityDayCount": len(
            [segment for segment in workload_timeline if segment["freeCapacityHours"] > 0]
        ),
        "movementIndicatorCount": len(
            [
                item
                for item in assigned_work_queue
                if item["movementIndicator"]["present"]
            ]
        ),
        "riskIndicatorCount": len(
            [item for item in assigned_work_queue if item["riskIndicator"]["present"]]
        ),
        "warningSignalCount": warning_trust_context["warningSignalCount"],
        "trustSignalCount": warning_trust_context["trustSignalCount"],
        "trustLimitedSignalCount": warning_trust_context["trustLimitedSignalCount"],
    }


def _build_navigation(
    planning_run_id: Optional[str],
    planning_context_key: Optional[str],
    source_snapshot_id: Optional[str],
    resource_context: Dict[str, Optional[str]],
    recommendation_context: Dict[str, Any],
    warning_trust_context: Dict[str, Any],
    origin_screen_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "returnNavigation": {
            "screen": dict(S01_LINK if origin_screen_id == "S01" else S01_LINK),
            "planningRunId": planning_run_id,
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": source_snapshot_id,
            "resourceId": resource_context["resourceId"],
            "resourceExternalId": resource_context["resourceExternalId"],
        },
        "reviewHandoff": {
            "available": any(
                item["requiresReviewHandoff"]
                for item in recommendation_context["items"]
            ),
            "screen": dict(S04_LINK),
            "recommendationIds": [
                item["recommendationId"]
                for item in recommendation_context["items"]
                if item["requiresReviewHandoff"]
            ],
        },
        "warningReview": {
            "available": warning_trust_context["activeSignalCount"] > 0,
            "screen": dict(S05_LINK),
            "originScreenId": "S03",
            "scope": {
                "scopeType": "resource",
                "scopeId": resource_context["resourceId"],
                "scopeExternalId": resource_context["resourceExternalId"],
                "scopeLabel": resource_context["resourceDisplayName"],
            },
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": source_snapshot_id,
        },
    }


def _build_view_state(
    resource_summary: Dict[str, Any],
    recommendation_context: Dict[str, Any],
    warning_trust_context: Dict[str, Any],
    is_loading: bool,
    is_refreshing: bool,
) -> Dict[str, Any]:
    if is_loading:
        screen_state = "loading"
    elif warning_trust_context["warningHeavy"]:
        screen_state = "warning_heavy"
    elif (
        resource_summary["ghostTaskCount"] > 0
        or resource_summary["ghostUnscheduledEffortHours"] > 0
        or resource_summary["overloadedDayCount"] > 0
    ):
        screen_state = "overload_focused"
    elif resource_summary["freeCapacityDayCount"] > 0:
        screen_state = "underutilized"
    elif recommendation_context["state"] == "no_actionable_recommendations":
        screen_state = "no_actionable_recommendation"
    else:
        screen_state = "ready"
    return {
        "screenState": screen_state,
        "isLoading": is_loading,
        "isRefreshing": is_refreshing,
        "accessRestricted": False,
        "accessRestrictedReason": None,
        "unavailableReason": None,
    }


def _warning_item_sort_key(item: Dict[str, Any]) -> tuple:
    classification_rank = {
        "blocking": 0,
        "trust_limited": 1,
        "advisory": 2,
    }[item["classification"]]
    return (
        classification_rank,
        item["signalType"],
        item["code"],
        item["signalId"],
    )


def _empty_warning_trust_context() -> Dict[str, Any]:
    return {
        "interpretationId": None,
        "activeSignalCount": 0,
        "advisorySignalCount": 0,
        "blockingSignalCount": 0,
        "warningSignalCount": 0,
        "trustSignalCount": 0,
        "trustLimitedSignalCount": 0,
        "warningHeavy": False,
        "signals": [],
    }


def _empty_recommendation_context(
    trust_affected: bool = False,
) -> Dict[str, Any]:
    return {
        "contextId": None,
        "state": RECOMMENDATION_CONTEXT_STATE_NOT_AVAILABLE,
        "freshnessStatus": RECOMMENDATION_FRESHNESS_NOT_GENERATED,
        "actionableRecommendationCount": 0,
        "totalRecommendationCount": 0,
        "trustAffected": trust_affected,
        "trustAffectedRecommendationCount": 0,
        "items": [],
    }
