"""S04/M01 read-model composition and acceptance command adapters."""

from typing import Any, Dict, List, Optional

from services.decision_support_service import DecisionSupportService
from services.review_approval_service import (
    ACCEPTANCE_SELECTION_ACTION_SELECT,
    ACCEPTANCE_SELECTION_SCOPE_CONNECTED_CHANGE_SET,
    ACCEPTANCE_SELECTION_SCOPE_DELTA_ITEM,
    ACTIVATION_STATUS_ACTIVATED,
    ReviewApprovalService,
)
from services.workflow_orchestrator_service import (
    ActivationWriteBackTargetReference,
    ActivationWorkflowTrigger,
    WorkflowOrchestratorService,
)


S04_SCREEN = {"id": "S04", "label": "Delta Review"}
M01_SCREEN = {"id": "M01", "label": "Connected Change Set Modal"}
S05_SCREEN = {"id": "S05", "label": "Planning Warnings Workspace"}
WARNING_HEAVY_THRESHOLD = 3


def build_s04_delta_review_contract(
    review_approval_service: ReviewApprovalService,
    workflow_orchestrator_service: Optional[WorkflowOrchestratorService] = None,
    decision_support_service: Optional[DecisionSupportService] = None,
    review_context_id: Optional[str] = None,
    planning_context_key: Optional[str] = None,
    origin_screen_id: Optional[str] = None,
    origin_scope_type: Optional[str] = None,
    origin_scope_id: Optional[str] = None,
    origin_scope_external_id: Optional[str] = None,
    origin_scope_label: Optional[str] = None,
    focused_delta_id: Optional[str] = None,
    is_refreshing: bool = False,
    access_restricted: bool = False,
    access_restricted_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose the S04 review surface over Review & Approval and Decision Support state."""

    if access_restricted:
        return _build_s04_access_restricted_contract(
            review_context_id=review_context_id,
            planning_context_key=planning_context_key,
            origin_screen_id=origin_screen_id,
            origin_scope_type=origin_scope_type,
            origin_scope_id=origin_scope_id,
            origin_scope_external_id=origin_scope_external_id,
            origin_scope_label=origin_scope_label,
            is_refreshing=is_refreshing,
            access_restricted_reason=access_restricted_reason,
        )

    review_context = review_approval_service.get_review_context(review_context_id=review_context_id)
    if review_context is None:
        return _build_s04_no_data_contract(
            review_context_id=review_context_id,
            planning_context_key=planning_context_key,
            origin_screen_id=origin_screen_id,
            origin_scope_type=origin_scope_type,
            origin_scope_id=origin_scope_id,
            origin_scope_external_id=origin_scope_external_id,
            origin_scope_label=origin_scope_label,
            is_refreshing=is_refreshing,
        )

    review_issue_fact_emission = review_approval_service.get_current_review_issue_fact_emission(
        review_context_id=review_context.review_context_id
    )
    warning_trust_context = _build_warning_trust_context(
        decision_support_service=decision_support_service,
        planning_context_key=planning_context_key,
        source_snapshot_id=review_context.source_snapshot_id,
    )
    blocked_acceptance = _build_blocked_acceptance(
        review_approval_service=review_approval_service,
        review_context=review_context,
        focused_delta_id=focused_delta_id,
    )
    activation_state = review_approval_service.get_activation_state(
        review_context_id=review_context.review_context_id
    )
    activation_workflow_status = None
    if (
        workflow_orchestrator_service is not None
        and activation_state is not None
        and activation_state.status == ACTIVATION_STATUS_ACTIVATED
    ):
        activation_workflow_status = (
            workflow_orchestrator_service.get_activation_workflow_status(
                review_context_id=review_context.review_context_id
            )
        )
    delta_groups = _build_delta_groups(
        review_context=review_context,
        review_issue_fact_emission=review_issue_fact_emission,
    )
    acceptance_state = _build_acceptance_state(
        review_context=review_context,
        review_issue_fact_emission=review_issue_fact_emission,
        activation_state=activation_state,
    )
    activation = _build_activation_view(
        review_context=review_context,
        review_issue_fact_emission=review_issue_fact_emission,
        activation_state=activation_state,
        activation_workflow_status=activation_workflow_status,
    )
    delta_summary = _build_delta_summary(review_context=review_context)
    view_state = _build_s04_view_state(
        review_context=review_context,
        blocked_acceptance=blocked_acceptance,
        warning_trust_context=warning_trust_context,
        is_refreshing=is_refreshing,
    )
    review_context_status = {
        "reviewContextId": review_context.review_context_id,
        "planningRunId": review_context.planning_run_id,
        "sourceSnapshotId": review_context.source_snapshot_id,
        "approvedPlanId": review_context.approved_plan_id,
        "draftScheduleId": review_context.draft_schedule_id,
        "comparisonContext": review_context.comparison_context,
        "deltaSetId": review_context.delta_set_id,
        "reviewStage": acceptance_state["reviewStage"],
    }

    return {
        "screen": dict(S04_SCREEN),
        "queryContext": {
            "reviewContextId": review_context.review_context_id,
            "planningRunId": review_context.planning_run_id,
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": review_context.source_snapshot_id,
            "approvedPlanId": review_context.approved_plan_id,
            "originScreenId": origin_screen_id,
            "originScope": _build_origin_scope(
                origin_scope_type=origin_scope_type,
                origin_scope_id=origin_scope_id,
                origin_scope_external_id=origin_scope_external_id,
                origin_scope_label=origin_scope_label,
            ),
            "focusedDeltaId": focused_delta_id,
        },
        "viewState": view_state,
        "reviewContextStatus": review_context_status,
        "deltaSummary": delta_summary,
        "groupedDeltaReview": delta_groups,
        "acceptanceState": acceptance_state,
        "activation": activation,
        "blockedAcceptance": blocked_acceptance,
        "warningTrustContext": warning_trust_context,
        "navigation": _build_s04_navigation(
            review_context=review_context,
            planning_context_key=planning_context_key,
            origin_screen_id=origin_screen_id,
            origin_scope_type=origin_scope_type,
            origin_scope_id=origin_scope_id,
            origin_scope_external_id=origin_scope_external_id,
            origin_scope_label=origin_scope_label,
            warning_trust_context=warning_trust_context,
        ),
    }


def build_m01_connected_change_set_contract(
    review_approval_service: ReviewApprovalService,
    review_context_id: str,
    requested_delta_id: str,
    planning_context_key: Optional[str] = None,
    is_refreshing: bool = False,
    access_restricted: bool = False,
    access_restricted_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose the M01 connected-set handling modal from Review & Approval state."""

    if access_restricted:
        return {
            "screen": dict(M01_SCREEN),
            "queryContext": {
                "reviewContextId": review_context_id,
                "requestedDeltaId": requested_delta_id,
                "planningContextKey": planning_context_key,
            },
            "viewState": {
                "screenState": "access_restricted",
                "isRefreshing": is_refreshing,
                "accessRestricted": True,
                "accessRestrictedReason": access_restricted_reason or "access_denied",
            },
            "requestedDelta": None,
            "blockingReason": None,
            "connectedSet": None,
            "actions": {
                "selectConnectedSetAvailable": False,
                "deselectConnectedSetAvailable": False,
            },
            "navigation": _build_m01_navigation(
                review_context_id=review_context_id,
                requested_delta_id=requested_delta_id,
                planning_context_key=planning_context_key,
            ),
        }

    review_context = review_approval_service.get_review_context(review_context_id=review_context_id)
    if review_context is None:
        raise ValueError("A saved review context is required before opening M01.")

    resolution = review_approval_service.resolve_connected_change_set(
        review_context_id=review_context_id,
        requested_delta_id=requested_delta_id,
    )
    requested_delta = _get_delta_item(review_context=review_context, delta_id=requested_delta_id)
    connected_set = resolution.connected_change_set
    connected_set_items = []
    if connected_set is not None:
        connected_set_items = _build_connected_set_items(
            review_context=review_context,
            member_delta_ids=connected_set.member_delta_ids,
        )

    return {
        "screen": dict(M01_SCREEN),
        "queryContext": {
            "reviewContextId": review_context.review_context_id,
            "requestedDeltaId": requested_delta_id,
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": review_context.source_snapshot_id,
            "approvedPlanId": review_context.approved_plan_id,
        },
        "viewState": {
            "screenState": (
                "ready" if connected_set is not None else "no_modal_required"
            ),
            "isRefreshing": is_refreshing,
            "accessRestricted": False,
            "accessRestrictedReason": None,
        },
        "requestedDelta": _serialize_requested_delta(requested_delta),
        "blockingReason": {
            "code": resolution.blocking_reason_code,
            "message": resolution.blocking_reason_message,
        }
        if resolution.blocking_reason_code is not None
        else None,
        "connectedSet": None
        if connected_set is None
        else {
            "connectedSetId": connected_set.connected_set_id,
            "minimalForDependencySafety": connected_set.minimal_for_dependency_safety,
            "memberDeltaIds": list(connected_set.member_delta_ids),
            "memberEntityExternalIds": list(connected_set.member_entity_external_ids),
            "memberItems": connected_set_items,
            "selectedMemberCount": len(
                [item for item in connected_set_items if item["acceptanceState"]["selected"]]
            ),
        },
        "actions": {
            "selectConnectedSetAvailable": connected_set is not None,
            "deselectConnectedSetAvailable": connected_set is not None,
        },
        "navigation": _build_m01_navigation(
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta_id,
            planning_context_key=planning_context_key,
        ),
    }


def submit_s04_delta_acceptance_selection(
    review_approval_service: ReviewApprovalService,
    review_context_id: str,
    delta_id: str,
    selected: bool,
) -> Dict[str, Any]:
    """Route an S04 item-level acceptance command into Review & Approval."""

    result = review_approval_service.record_delta_acceptance_selection(
        review_context_id=review_context_id,
        delta_id=delta_id,
        selected=selected,
    )
    return _serialize_acceptance_command_result(
        screen=S04_SCREEN,
        result=result,
    )


def submit_m01_connected_set_acceptance_selection(
    review_approval_service: ReviewApprovalService,
    review_context_id: str,
    requested_delta_id: str,
    selected: bool,
) -> Dict[str, Any]:
    """Route an M01 connected-set acceptance command into Review & Approval."""

    result = review_approval_service.record_connected_set_acceptance_selection(
        review_context_id=review_context_id,
        requested_delta_id=requested_delta_id,
        selected=selected,
    )
    return _serialize_acceptance_command_result(
        screen=M01_SCREEN,
        result=result,
    )


def submit_s04_activation_command(
    review_approval_service: ReviewApprovalService,
    review_context_id: str,
    requested_by: str,
    requested_at: str,
    workflow_orchestrator_service: Optional[WorkflowOrchestratorService] = None,
) -> Dict[str, Any]:
    """Route an S04 activation command into Review & Approval."""

    result = review_approval_service.activate_approved_changes(
        review_context_id=review_context_id,
        requested_by=requested_by,
        requested_at=requested_at,
    )
    activation_workflow_status = None
    if (
        workflow_orchestrator_service is not None
        and result.downstream_handoff.handoff_required
        and result.activation_state.approved_plan_id_after is not None
    ):
        workflow_start = workflow_orchestrator_service.start_activation_workflow(
            ActivationWorkflowTrigger(
                activation_command_id=result.command_id,
                activation_id=result.activation_state.activation_id,
                review_context_id=result.review_context_id,
                approved_plan_id=result.activation_state.approved_plan_id_after,
                source_snapshot_id=result.downstream_handoff.source_snapshot_id,
                write_back_targets=[
                    ActivationWriteBackTargetReference(
                        target_id=target.target_id,
                        delta_id=target.delta_id,
                        entity_type=target.entity_type,
                        entity_external_id=target.entity_external_id,
                        entity_name=target.entity_name,
                        project_external_id=target.project_external_id,
                        write_back_action=target.write_back_action,
                        write_back_fields=list(target.write_back_fields),
                    )
                    for target in result.downstream_handoff.write_back_targets
                ],
                requested_by=requested_by,
                requested_at=requested_at,
                idempotency_key=result.command_id,
            )
        )
        activation_workflow_status = (
            workflow_orchestrator_service.get_activation_workflow_status(
                workflow_instance_id=workflow_start.workflow_instance.workflow_instance_id
            )
        )
    return _serialize_activation_command_result(
        screen=S04_SCREEN,
        result=result,
        activation_workflow_status=activation_workflow_status,
    )


def _build_s04_access_restricted_contract(
    review_context_id: Optional[str],
    planning_context_key: Optional[str],
    origin_screen_id: Optional[str],
    origin_scope_type: Optional[str],
    origin_scope_id: Optional[str],
    origin_scope_external_id: Optional[str],
    origin_scope_label: Optional[str],
    is_refreshing: bool,
    access_restricted_reason: Optional[str],
) -> Dict[str, Any]:
    return {
        "screen": dict(S04_SCREEN),
        "queryContext": {
            "reviewContextId": review_context_id,
            "planningRunId": None,
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": None,
            "approvedPlanId": None,
            "originScreenId": origin_screen_id,
            "originScope": _build_origin_scope(
                origin_scope_type=origin_scope_type,
                origin_scope_id=origin_scope_id,
                origin_scope_external_id=origin_scope_external_id,
                origin_scope_label=origin_scope_label,
            ),
            "focusedDeltaId": None,
        },
        "viewState": {
            "screenState": "access_restricted",
            "isRefreshing": is_refreshing,
            "accessRestricted": True,
            "accessRestrictedReason": access_restricted_reason or "access_denied",
        },
        "reviewContextStatus": None,
        "deltaSummary": _empty_delta_summary(),
        "groupedDeltaReview": [],
        "acceptanceState": _empty_acceptance_state(),
        "activation": _empty_activation_view(review_context_id=review_context_id),
        "blockedAcceptance": None,
        "warningTrustContext": _empty_warning_trust_context(),
        "navigation": {
            "returnNavigation": _build_return_navigation(
                origin_screen_id=origin_screen_id,
                origin_scope=_build_origin_scope(
                    origin_scope_type=origin_scope_type,
                    origin_scope_id=origin_scope_id,
                    origin_scope_external_id=origin_scope_external_id,
                    origin_scope_label=origin_scope_label,
                ),
                planning_context_key=planning_context_key,
                source_snapshot_id=None,
            ),
            "warningReview": None,
        },
    }


def _build_s04_no_data_contract(
    review_context_id: Optional[str],
    planning_context_key: Optional[str],
    origin_screen_id: Optional[str],
    origin_scope_type: Optional[str],
    origin_scope_id: Optional[str],
    origin_scope_external_id: Optional[str],
    origin_scope_label: Optional[str],
    is_refreshing: bool,
) -> Dict[str, Any]:
    return {
        "screen": dict(S04_SCREEN),
        "queryContext": {
            "reviewContextId": review_context_id,
            "planningRunId": None,
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": None,
            "approvedPlanId": None,
            "originScreenId": origin_screen_id,
            "originScope": _build_origin_scope(
                origin_scope_type=origin_scope_type,
                origin_scope_id=origin_scope_id,
                origin_scope_external_id=origin_scope_external_id,
                origin_scope_label=origin_scope_label,
            ),
            "focusedDeltaId": None,
        },
        "viewState": {
            "screenState": "no_data",
            "isRefreshing": is_refreshing,
            "accessRestricted": False,
            "accessRestrictedReason": None,
        },
        "reviewContextStatus": None,
        "deltaSummary": _empty_delta_summary(),
        "groupedDeltaReview": [],
        "acceptanceState": _empty_acceptance_state(),
        "activation": _empty_activation_view(review_context_id=review_context_id),
        "blockedAcceptance": None,
        "warningTrustContext": _empty_warning_trust_context(),
        "navigation": {
            "returnNavigation": _build_return_navigation(
                origin_screen_id=origin_screen_id,
                origin_scope=_build_origin_scope(
                    origin_scope_type=origin_scope_type,
                    origin_scope_id=origin_scope_id,
                    origin_scope_external_id=origin_scope_external_id,
                    origin_scope_label=origin_scope_label,
                ),
                planning_context_key=planning_context_key,
                source_snapshot_id=None,
            ),
            "warningReview": None,
        },
    }


def _build_origin_scope(
    origin_scope_type: Optional[str],
    origin_scope_id: Optional[str],
    origin_scope_external_id: Optional[str],
    origin_scope_label: Optional[str],
) -> Optional[Dict[str, Optional[str]]]:
    if not any(
        [origin_scope_type, origin_scope_id, origin_scope_external_id, origin_scope_label]
    ):
        return None
    return {
        "scopeType": origin_scope_type,
        "scopeId": origin_scope_id,
        "scopeExternalId": origin_scope_external_id,
        "scopeLabel": origin_scope_label,
    }


def _build_warning_trust_context(
    decision_support_service: Optional[DecisionSupportService],
    planning_context_key: Optional[str],
    source_snapshot_id: str,
) -> Dict[str, Any]:
    if decision_support_service is None:
        return _empty_warning_trust_context()

    state = decision_support_service.get_screen_warning_trust_state(
        screen_id="S04",
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
    )
    if state is None:
        return _empty_warning_trust_context()

    signals = sorted(
        [_serialize_warning_signal(signal) for signal in state.signals],
        key=_warning_signal_sort_key,
    )
    return {
        "interpretationId": state.interpretation_id,
        "activeSignalCount": len(signals),
        "advisorySignalCount": len(
            [signal for signal in signals if signal["classification"] == "advisory"]
        ),
        "blockingSignalCount": len(
            [signal for signal in signals if signal["classification"] == "blocking"]
        ),
        "trustLimitedSignalCount": len(
            [
                signal
                for signal in signals
                if signal["classification"] == "trust_limited"
            ]
        ),
        "warningHeavy": len(signals) >= WARNING_HEAVY_THRESHOLD,
        "signals": signals,
    }


def _build_blocked_acceptance(
    review_approval_service: ReviewApprovalService,
    review_context,
    focused_delta_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if focused_delta_id is None:
        return None
    requested_delta = _get_delta_item(
        review_context=review_context,
        delta_id=focused_delta_id,
    )
    if requested_delta.connected_set_id is None:
        return None
    unresolved_connected_set_ids = _build_unresolved_connected_set_ids(review_context)
    if requested_delta.connected_set_id not in unresolved_connected_set_ids:
        return None
    resolution = review_approval_service.get_connected_set_resolution(
        review_context_id=review_context.review_context_id,
        requested_delta_id=focused_delta_id,
    )
    if resolution is None:
        resolution = review_approval_service.resolve_connected_change_set(
            review_context_id=review_context.review_context_id,
            requested_delta_id=focused_delta_id,
        )
    if resolution.isolated_acceptance_safe:
        return None
    connected_set = resolution.connected_change_set
    return {
        "present": True,
        "requestedDeltaId": focused_delta_id,
        "requestedEntityExternalId": requested_delta.entity_external_id,
        "requestedEntityName": requested_delta.entity_name,
        "reasonCode": resolution.blocking_reason_code,
        "reasonMessage": resolution.blocking_reason_message,
        "connectedSetId": None
        if connected_set is None
        else connected_set.connected_set_id,
        "modalNavigation": {
            "screen": dict(M01_SCREEN),
            "reviewContextId": review_context.review_context_id,
            "requestedDeltaId": focused_delta_id,
        },
    }


def _build_delta_groups(
    review_context,
    review_issue_fact_emission,
) -> List[Dict[str, Any]]:
    dependency_blockers_by_delta_id: Dict[str, List[Dict[str, Any]]] = {}
    connected_set_required_ids = set()
    for fact in review_issue_fact_emission.issue_facts:
        if fact.code == "dependency_safe_approval_blocked":
            for delta_id in fact.related_delta_ids:
                dependency_blockers_by_delta_id.setdefault(delta_id, []).append(
                    {
                        "code": fact.code,
                        "message": fact.message,
                    }
                )
        if fact.code == "connected_set_required" and fact.related_connected_set_id is not None:
            connected_set_required_ids.add(fact.related_connected_set_id)
    unresolved_connected_set_ids = _build_unresolved_connected_set_ids(review_context)

    groups: Dict[str, Dict[str, Any]] = {}
    for delta in review_context.delta_items:
        group_key = delta.project_external_id or "ungrouped"
        group = groups.setdefault(
            group_key,
            {
                "groupId": group_key,
                "projectId": delta.project_id,
                "projectExternalId": delta.project_external_id,
                "groupLabel": delta.project_external_id or "Ungrouped changes",
                "deltaCount": 0,
                "selectedCount": 0,
                "blockedItemCount": 0,
                "connectedSetRequiredCount": 0,
                "items": [],
            },
        )
        item = _serialize_delta_item(
            delta=delta,
            dependency_blockers=dependency_blockers_by_delta_id.get(delta.delta_id, []),
            unresolved_connected_set_ids=unresolved_connected_set_ids,
            connected_set_required_ids=connected_set_required_ids,
        )
        group["deltaCount"] += 1
        if item["acceptanceState"]["selected"]:
            group["selectedCount"] += 1
        if item["acceptanceState"]["blocked"]:
            group["blockedItemCount"] += 1
        if item["acceptanceState"]["connectedSetRequiredPresent"]:
            group["connectedSetRequiredCount"] += 1
        group["items"].append(item)

    return [
        {
            **group,
            "groupSelectionAvailable": group["connectedSetRequiredCount"] == 0,
        }
        for _, group in sorted(groups.items(), key=lambda item: item[0])
    ]


def _serialize_delta_item(
    delta,
    dependency_blockers: List[Dict[str, Any]],
    unresolved_connected_set_ids: set,
    connected_set_required_ids: set,
) -> Dict[str, Any]:
    has_connected_set = delta.connected_set_id is not None
    unresolved_connected_set = delta.connected_set_id in unresolved_connected_set_ids
    blocked = unresolved_connected_set or bool(dependency_blockers)
    return {
        "deltaId": delta.delta_id,
        "entityType": delta.entity_type,
        "entityId": delta.entity_id,
        "entityExternalId": delta.entity_external_id,
        "entityName": delta.entity_name,
        "taskId": delta.task_id,
        "taskExternalId": delta.task_external_id,
        "taskName": delta.task_name,
        "projectId": delta.project_id,
        "projectExternalId": delta.project_external_id,
        "deltaScopeAttributes": list(delta.delta_scope_attributes),
        "attributeChanges": [
            {
                "attributeName": change.attribute_name,
                "beforeValue": change.before_value,
                "afterValue": change.after_value,
            }
            for change in delta.attribute_changes
        ],
        "acceptanceState": {
            "selected": delta.selected_for_acceptance,
            "directSelectable": delta.connected_set_id is None,
            "blocked": blocked,
            "requiresConnectedSet": unresolved_connected_set,
            "connectedSetId": delta.connected_set_id,
            "dependencyBlockerPresent": bool(dependency_blockers),
            "connectedSetRequiredPresent": (
                unresolved_connected_set
                and delta.connected_set_id in connected_set_required_ids
            ),
        },
        "dependencyBlockers": dependency_blockers,
        "connectedSetEntry": {
            "available": has_connected_set,
            "screen": dict(M01_SCREEN) if has_connected_set else None,
            "connectedSetId": delta.connected_set_id,
            "requestedDeltaId": delta.delta_id if has_connected_set else None,
        },
        "recommendationOriginContext": [
            {
                "recommendationId": ref.recommendation_id,
                "originScreenId": ref.origin_screen_id,
                "projectExternalId": ref.project_external_id,
                "taskExternalId": ref.task_external_id,
                "requiresReviewHandoff": ref.requires_review_handoff,
            }
            for ref in delta.recommendation_origin_refs
        ],
    }


def _build_acceptance_state(
    review_context,
    review_issue_fact_emission,
    activation_state,
) -> Dict[str, Any]:
    selected_count = len(
        [delta for delta in review_context.delta_items if delta.selected_for_acceptance]
    )
    unresolved_connected_set_ids = _build_unresolved_connected_set_ids(review_context)
    if (
        activation_state is not None
        and activation_state.status == ACTIVATION_STATUS_ACTIVATED
    ):
        review_stage = "approved_activated"
    else:
        review_stage = "draft" if selected_count == 0 else "in_review"
    return {
        "reviewStage": review_stage,
        "selectedDeltaCount": selected_count,
        "unselectedDeltaCount": len(review_context.delta_items) - selected_count,
        "connectedSetRequiredCount": len(
            [
                delta
                for delta in review_context.delta_items
                if delta.connected_set_id in unresolved_connected_set_ids
            ]
        ),
        "blockingIssueCount": review_issue_fact_emission.blocking_fact_count,
        "informationalIssueCount": review_issue_fact_emission.informational_fact_count,
    }


def _build_activation_view(
    review_context,
    review_issue_fact_emission,
    activation_state,
    activation_workflow_status,
) -> Dict[str, Any]:
    selected_delta_ids = sorted(
        [
            delta.delta_id
            for delta in review_context.delta_items
            if delta.selected_for_acceptance
        ]
    )
    if (
        activation_state is not None
        and activation_state.status != ACTIVATION_STATUS_ACTIVATED
        and activation_state.selected_delta_ids != selected_delta_ids
    ):
        activation_state = None

    if activation_state is None:
        return {
            "status": "not_requested",
            "activationId": None,
            "actionAvailable": bool(selected_delta_ids)
            and review_issue_fact_emission.blocking_fact_count == 0,
            "commandLabel": "Activate accepted changes",
            "approvedPlanIdBefore": review_context.approved_plan_id,
            "approvedPlanIdAfter": None,
            "selectedDeltaIds": selected_delta_ids,
            "businessRuleBlockers": [],
            "outcome": None,
            "downstreamWorkflow": {
                "ownerService": "Workflow Orchestrator Service",
                "handoffRequired": False,
                "workflowState": "not_started",
                "workflowInstanceId": None,
                "currentStep": None,
                "stepStates": [],
                "lastErrorCode": None,
                "lastErrorMessage": None,
            },
        }

    return {
        "status": activation_state.status,
        "activationId": activation_state.activation_id,
        "actionAvailable": bool(selected_delta_ids)
        and review_issue_fact_emission.blocking_fact_count == 0
        and activation_state.status != ACTIVATION_STATUS_ACTIVATED,
        "commandLabel": "Activate accepted changes",
        "approvedPlanIdBefore": activation_state.approved_plan_id_before,
        "approvedPlanIdAfter": activation_state.approved_plan_id_after,
        "selectedDeltaIds": list(activation_state.selected_delta_ids),
        "businessRuleBlockers": [
            {
                "ruleId": blocker.rule_id,
                "code": blocker.code,
                "message": blocker.message,
                "entityType": blocker.entity_type,
                "entityId": blocker.entity_id,
                "entityExternalId": blocker.entity_external_id,
            }
            for blocker in activation_state.business_rule_blockers
        ],
        "outcome": None
        if activation_state.outcome is None
        else {
            "code": activation_state.outcome.code,
            "message": activation_state.outcome.message,
            "activatedDeltaIds": list(activation_state.outcome.activated_delta_ids),
            "resultingApprovedPlanId": activation_state.outcome.resulting_approved_plan_id,
        },
        "downstreamWorkflow": _build_downstream_workflow_view(
            handoff_required=activation_state.status == ACTIVATION_STATUS_ACTIVATED,
            activation_workflow_status=activation_workflow_status,
        ),
    }


def _build_delta_summary(review_context) -> Dict[str, Any]:
    unresolved_connected_set_ids = _build_unresolved_connected_set_ids(review_context)
    return {
        "totalDeltaCount": len(review_context.delta_items),
        "taskDeltaCount": len(
            [delta for delta in review_context.delta_items if delta.entity_type == "task"]
        ),
        "milestoneDeltaCount": len(
            [delta for delta in review_context.delta_items if delta.entity_type == "milestone"]
        ),
        "projectDeltaCount": len(
            [delta for delta in review_context.delta_items if delta.entity_type == "project"]
        ),
        "selectedDeltaCount": len(
            [delta for delta in review_context.delta_items if delta.selected_for_acceptance]
        ),
        "blockedDeltaCount": len(
            [
                delta
                for delta in review_context.delta_items
                if delta.connected_set_id in unresolved_connected_set_ids
            ]
        ),
        "groupCount": len(
            {
                delta.project_external_id or "ungrouped"
                for delta in review_context.delta_items
            }
        ),
        "connectedSetCount": len(review_context.connected_change_sets),
        "recommendationOriginDeltaCount": len(
            [
                delta
                for delta in review_context.delta_items
                if delta.recommendation_origin_refs
            ]
        ),
        "hasDeltas": bool(review_context.delta_items),
    }


def _build_s04_navigation(
    review_context,
    planning_context_key: Optional[str],
    origin_screen_id: Optional[str],
    origin_scope_type: Optional[str],
    origin_scope_id: Optional[str],
    origin_scope_external_id: Optional[str],
    origin_scope_label: Optional[str],
    warning_trust_context: Dict[str, Any],
) -> Dict[str, Any]:
    origin_scope = _build_origin_scope(
        origin_scope_type=origin_scope_type,
        origin_scope_id=origin_scope_id,
        origin_scope_external_id=origin_scope_external_id,
        origin_scope_label=origin_scope_label,
    )
    return {
        "returnNavigation": _build_return_navigation(
            origin_screen_id=origin_screen_id,
            origin_scope=origin_scope,
            planning_context_key=planning_context_key,
            source_snapshot_id=review_context.source_snapshot_id,
        ),
        "warningReview": (
            {
                "available": True,
                "screen": dict(S05_SCREEN),
                "originScreenId": "S04",
                "planningContextKey": planning_context_key,
                "sourceSnapshotId": review_context.source_snapshot_id,
            }
            if warning_trust_context["activeSignalCount"] > 0
            else None
        ),
    }


def _build_s04_view_state(
    review_context,
    blocked_acceptance: Optional[Dict[str, Any]],
    warning_trust_context: Dict[str, Any],
    is_refreshing: bool,
) -> Dict[str, Any]:
    if not review_context.delta_items:
        screen_state = "no_deltas"
    elif blocked_acceptance is not None:
        screen_state = "blocked_isolated_acceptance"
    elif warning_trust_context["warningHeavy"]:
        screen_state = "warning_heavy"
    else:
        screen_state = "ready"
    return {
        "screenState": screen_state,
        "isRefreshing": is_refreshing,
        "accessRestricted": False,
        "accessRestrictedReason": None,
    }


def _build_return_navigation(
    origin_screen_id: Optional[str],
    origin_scope: Optional[Dict[str, Optional[str]]],
    planning_context_key: Optional[str],
    source_snapshot_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if origin_screen_id is None:
        return None
    return {
        "screen": {
            "id": origin_screen_id,
            "label": "Portfolio Swimlane Home"
            if origin_screen_id == "S01"
            else "Resource Detail"
            if origin_screen_id == "S03"
            else origin_screen_id,
        },
        "originScope": origin_scope,
        "planningContextKey": planning_context_key,
        "sourceSnapshotId": source_snapshot_id,
    }


def _build_m01_navigation(
    review_context_id: str,
    requested_delta_id: str,
    planning_context_key: Optional[str],
) -> Dict[str, Any]:
    return {
        "returnNavigation": {
            "screen": dict(S04_SCREEN),
            "reviewContextId": review_context_id,
            "requestedDeltaId": requested_delta_id,
            "planningContextKey": planning_context_key,
        }
    }


def _serialize_requested_delta(delta) -> Dict[str, Any]:
    return {
        "deltaId": delta.delta_id,
        "entityType": delta.entity_type,
        "entityExternalId": delta.entity_external_id,
        "entityName": delta.entity_name,
        "projectId": delta.project_id,
        "projectExternalId": delta.project_external_id,
        "selected": delta.selected_for_acceptance,
    }


def _build_connected_set_items(
    review_context,
    member_delta_ids: List[str],
) -> List[Dict[str, Any]]:
    member_ids = set(member_delta_ids)
    return [
        {
            "deltaId": delta.delta_id,
            "entityType": delta.entity_type,
            "entityExternalId": delta.entity_external_id,
            "entityName": delta.entity_name,
            "projectId": delta.project_id,
            "projectExternalId": delta.project_external_id,
            "acceptanceState": {
                "selected": delta.selected_for_acceptance,
            },
            "attributeChanges": [
                {
                    "attributeName": change.attribute_name,
                    "beforeValue": change.before_value,
                    "afterValue": change.after_value,
                }
                for change in delta.attribute_changes
            ],
        }
        for delta in review_context.delta_items
        if delta.delta_id in member_ids
    ]


def _serialize_warning_signal(signal) -> Dict[str, Any]:
    return {
        "signalId": signal.signal_id,
        "classification": _derive_warning_classification(signal),
        "signalType": signal.signal_type,
        "severity": signal.severity,
        "code": signal.code,
        "message": signal.message,
        "interpretationCategory": signal.interpretation_category,
        "sourceIssueService": signal.source_issue_service,
        "entityType": signal.entity_type,
        "entityId": signal.entity_id,
        "entityExternalId": signal.entity_external_id,
    }


def _derive_warning_classification(signal) -> str:
    if signal.blocking or not signal.advisory:
        return "blocking"
    if signal.signal_type == "trust" or signal.interpretation_category == "trust_limited":
        return "trust_limited"
    return "advisory"


def _warning_signal_sort_key(item: Dict[str, Any]) -> tuple:
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


def _serialize_acceptance_command_result(
    screen: Dict[str, str],
    result,
) -> Dict[str, Any]:
    acceptance_state = {
        "reviewStage": (
            "draft"
            if not any(
                delta.selected_for_acceptance for delta in result.review_context.delta_items
            )
            else "in_review"
        ),
        "selectedDeltaCount": len(
            [
                delta
                for delta in result.review_context.delta_items
                if delta.selected_for_acceptance
            ]
        ),
    }
    modal_launch = None
    if result.connected_set_resolution is not None and result.blocked_reason_code is not None:
        modal_launch = {
            "screen": dict(M01_SCREEN),
            "reviewContextId": result.review_context_id,
            "requestedDeltaId": result.requested_delta_id,
            "connectedSetId": result.connected_set_id,
        }
    return {
        "screen": dict(screen),
        "commandId": result.command_id,
        "reviewContextId": result.review_context_id,
        "requestedDeltaId": result.requested_delta_id,
        "connectedSetId": result.connected_set_id,
        "selectionScope": result.selection_scope,
        "action": result.action,
        "status": result.status,
        "blockedReasonCode": result.blocked_reason_code,
        "blockedReasonMessage": result.blocked_reason_message,
        "selectionSummary": acceptance_state,
        "modalLaunch": modal_launch,
    }


def _serialize_activation_command_result(
    screen: Dict[str, str],
    result,
    activation_workflow_status=None,
) -> Dict[str, Any]:
    activation_state = result.activation_state
    return {
        "screen": dict(screen),
        "commandId": result.command_id,
        "reviewContextId": result.review_context_id,
        "activationId": activation_state.activation_id,
        "status": activation_state.status,
        "reusedExisting": result.reused_existing,
        "approvedPlanIdBefore": activation_state.approved_plan_id_before,
        "approvedPlanIdAfter": activation_state.approved_plan_id_after,
        "selectedDeltaIds": list(activation_state.selected_delta_ids),
        "businessRuleBlockers": [
            {
                "ruleId": blocker.rule_id,
                "code": blocker.code,
                "message": blocker.message,
                "entityType": blocker.entity_type,
                "entityId": blocker.entity_id,
                "entityExternalId": blocker.entity_external_id,
            }
            for blocker in activation_state.business_rule_blockers
        ],
        "activationOutcome": None
        if activation_state.outcome is None
        else {
            "code": activation_state.outcome.code,
            "message": activation_state.outcome.message,
            "activatedDeltaIds": list(activation_state.outcome.activated_delta_ids),
            "resultingApprovedPlanId": activation_state.outcome.resulting_approved_plan_id,
        },
        "downstreamWorkflow": _build_downstream_workflow_view(
            handoff_required=result.downstream_handoff.handoff_required,
            activation_workflow_status=activation_workflow_status,
            owner_service=result.downstream_handoff.owner_service,
        ),
    }


def _build_downstream_workflow_view(
    handoff_required: bool,
    activation_workflow_status,
    owner_service: str = "Workflow Orchestrator Service",
) -> Dict[str, Any]:
    if activation_workflow_status is None:
        return {
            "ownerService": owner_service,
            "handoffRequired": handoff_required,
            "workflowState": "not_started",
            "workflowInstanceId": None,
            "currentStep": None,
            "stepStates": [],
            "lastErrorCode": None,
            "lastErrorMessage": None,
        }

    return {
        "ownerService": owner_service,
        "handoffRequired": handoff_required,
        "workflowState": activation_workflow_status.status,
        "workflowInstanceId": activation_workflow_status.workflow_instance_id,
        "currentStep": activation_workflow_status.current_step,
        "stepStates": [
            {
                "stepName": step.step_name,
                "status": step.status,
                "attemptNumber": step.attempt_number,
                "handoffId": step.handoff_id,
            }
            for step in activation_workflow_status.step_states
        ],
        "lastErrorCode": activation_workflow_status.last_error_code,
        "lastErrorMessage": activation_workflow_status.last_error_message,
    }


def _get_delta_item(review_context, delta_id: str):
    for delta in review_context.delta_items:
        if delta.delta_id == delta_id:
            return delta
    raise ValueError("Requested delta_id is not present in the review context.")


def _empty_delta_summary() -> Dict[str, Any]:
    return {
        "totalDeltaCount": 0,
        "taskDeltaCount": 0,
        "milestoneDeltaCount": 0,
        "projectDeltaCount": 0,
        "selectedDeltaCount": 0,
        "blockedDeltaCount": 0,
        "groupCount": 0,
        "connectedSetCount": 0,
        "recommendationOriginDeltaCount": 0,
        "hasDeltas": False,
    }


def _empty_acceptance_state() -> Dict[str, Any]:
    return {
        "reviewStage": "draft",
        "selectedDeltaCount": 0,
        "unselectedDeltaCount": 0,
        "connectedSetRequiredCount": 0,
        "blockingIssueCount": 0,
        "informationalIssueCount": 0,
    }


def _empty_activation_view(
    review_context_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "status": "not_requested",
        "activationId": None,
        "actionAvailable": False,
        "commandLabel": "Activate accepted changes",
        "approvedPlanIdBefore": None,
        "approvedPlanIdAfter": None,
        "selectedDeltaIds": [],
        "businessRuleBlockers": [],
        "outcome": None,
        "downstreamWorkflow": _build_downstream_workflow_view(
            handoff_required=False,
            activation_workflow_status=None,
        ),
    }


def _empty_warning_trust_context() -> Dict[str, Any]:
    return {
        "interpretationId": None,
        "activeSignalCount": 0,
        "advisorySignalCount": 0,
        "blockingSignalCount": 0,
        "trustLimitedSignalCount": 0,
        "warningHeavy": False,
        "signals": [],
    }


def _build_unresolved_connected_set_ids(review_context) -> set:
    selected_delta_ids = {
        delta.delta_id for delta in review_context.delta_items if delta.selected_for_acceptance
    }
    unresolved_connected_set_ids = set()
    for connected_set in review_context.connected_change_sets:
        if not all(
            member_delta_id in selected_delta_ids
            for member_delta_id in connected_set.member_delta_ids
        ):
            unresolved_connected_set_ids.add(connected_set.connected_set_id)
    return unresolved_connected_set_ids
