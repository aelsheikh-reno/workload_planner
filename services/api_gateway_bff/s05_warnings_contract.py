"""S05 — Planning Warnings Workspace read-model composition adapter."""

from typing import Any, Dict, List, Optional, Sequence

from services.decision_support_service import DecisionSupportService, ScreenWarningTrustSignal


S05_SCREEN = {"id": "S05", "label": "Planning Warnings Workspace"}
SCREEN_LABELS = {
    "S01": "Portfolio Swimlane Home",
    "S02": "Planning Setup",
    "S03": "Resource Detail",
    "S04": "Delta Review",
    "S05": "Planning Warnings Workspace",
}
DEFAULT_GROUP_BY = "affected_workflow"
WARNING_HEAVY_THRESHOLD = 4


def build_s05_warnings_workspace_contract(
    decision_support_service: Optional[DecisionSupportService] = None,
    planning_context_key: Optional[str] = None,
    source_snapshot_id: Optional[str] = None,
    origin_screen_id: Optional[str] = None,
    origin_scope_type: Optional[str] = None,
    origin_scope_id: Optional[str] = None,
    origin_scope_external_id: Optional[str] = None,
    origin_scope_label: Optional[str] = None,
    workflow_filter_ids: Optional[Sequence[str]] = None,
    classification_filters: Optional[Sequence[str]] = None,
    signal_type_filters: Optional[Sequence[str]] = None,
    is_loading: bool = False,
    is_refreshing: bool = False,
    access_restricted: bool = False,
    access_restricted_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose the S05 workspace contract from Decision Support warning/trust state."""

    normalized_origin_screen_id = (
        origin_screen_id if origin_screen_id in SCREEN_LABELS and origin_screen_id != "S05" else None
    )

    if access_restricted:
        return _build_access_restricted_contract(
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
            origin_screen_id=normalized_origin_screen_id,
            origin_scope_type=origin_scope_type,
            origin_scope_id=origin_scope_id,
            origin_scope_external_id=origin_scope_external_id,
            origin_scope_label=origin_scope_label,
            is_refreshing=is_refreshing,
            is_loading=is_loading,
            access_restricted_reason=access_restricted_reason,
        )

    state = None
    if decision_support_service is not None:
        state = decision_support_service.get_screen_warning_trust_state(
            screen_id="S05",
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
        )

    resolved_snapshot_id = (
        state.source_snapshot_id if state is not None else source_snapshot_id
    )
    all_items = _build_warning_items(state)
    active_workflow_filters = list(workflow_filter_ids or [])
    scoped_entry_defaulted = False
    if not active_workflow_filters and normalized_origin_screen_id is not None:
        active_workflow_filters = [normalized_origin_screen_id]
        scoped_entry_defaulted = True

    active_classification_filters = list(classification_filters or [])
    active_signal_type_filters = list(signal_type_filters or [])
    scope_filter = _build_scope_filter(
        scope_type=origin_scope_type,
        scope_id=origin_scope_id,
        scope_external_id=origin_scope_external_id,
        scope_label=origin_scope_label,
    )
    if scope_filter is not None and normalized_origin_screen_id is not None:
        scoped_entry_defaulted = True

    filtered_items = [
        item
        for item in all_items
        if _matches_filters(
            item=item,
            workflow_ids=active_workflow_filters,
            classification_filters=active_classification_filters,
            signal_type_filters=active_signal_type_filters,
            scope_filter=scope_filter,
        )
    ]
    group_summaries = _build_group_summaries(filtered_items)
    workspace_summary = _build_workspace_summary(
        state=state,
        filtered_items=filtered_items,
        group_summaries=group_summaries,
    )
    trust_guidance = _build_trust_guidance(filtered_items)
    available_filters = _build_available_filters(all_items)
    empty_state = _build_empty_state(
        state=state,
        filtered_items=filtered_items,
        is_loading=is_loading,
    )
    view_state = _build_view_state(
        filtered_items=filtered_items,
        workspace_summary=workspace_summary,
        is_loading=is_loading,
        is_refreshing=is_refreshing,
    )

    return {
        "screen": dict(S05_SCREEN),
        "queryContext": {
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": resolved_snapshot_id,
            "originScreenId": normalized_origin_screen_id,
            "originScope": scope_filter,
        },
        "viewState": view_state,
        "workspaceSummary": workspace_summary,
        "filterState": {
            "defaultGroupBy": DEFAULT_GROUP_BY,
            "groupBy": DEFAULT_GROUP_BY,
            "availableGroupings": [
                {"id": DEFAULT_GROUP_BY, "label": "Affected workflow"}
            ],
            "activeWorkflowIds": active_workflow_filters,
            "activeClassificationFilters": active_classification_filters,
            "activeSignalTypes": active_signal_type_filters,
            "availableFilters": available_filters,
            "scopedEntryDefaulted": scoped_entry_defaulted,
            "originScreenId": normalized_origin_screen_id,
            "scopeFilter": scope_filter,
        },
        "groupSummaries": group_summaries,
        "warningItems": filtered_items,
        "trustGuidance": trust_guidance,
        "returnNavigation": _build_return_navigation(
            origin_screen_id=normalized_origin_screen_id,
            scope_filter=scope_filter,
            planning_context_key=planning_context_key,
            source_snapshot_id=resolved_snapshot_id,
        ),
        "emptyState": empty_state,
    }


def _build_access_restricted_contract(
    planning_context_key: Optional[str],
    source_snapshot_id: Optional[str],
    origin_screen_id: Optional[str],
    origin_scope_type: Optional[str],
    origin_scope_id: Optional[str],
    origin_scope_external_id: Optional[str],
    origin_scope_label: Optional[str],
    is_refreshing: bool,
    is_loading: bool,
    access_restricted_reason: Optional[str],
) -> Dict[str, Any]:
    scope_filter = _build_scope_filter(
        scope_type=origin_scope_type,
        scope_id=origin_scope_id,
        scope_external_id=origin_scope_external_id,
        scope_label=origin_scope_label,
    )
    return {
        "screen": dict(S05_SCREEN),
        "queryContext": {
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": source_snapshot_id,
            "originScreenId": origin_screen_id,
            "originScope": scope_filter,
        },
        "viewState": {
            "screenState": "access_restricted",
            "isLoading": is_loading,
            "isRefreshing": is_refreshing,
            "accessRestricted": True,
            "accessRestrictedReason": access_restricted_reason or "access_denied",
        },
        "workspaceSummary": _empty_workspace_summary(),
        "filterState": {
            "defaultGroupBy": DEFAULT_GROUP_BY,
            "groupBy": DEFAULT_GROUP_BY,
            "availableGroupings": [
                {"id": DEFAULT_GROUP_BY, "label": "Affected workflow"}
            ],
            "activeWorkflowIds": [],
            "activeClassificationFilters": [],
            "activeSignalTypes": [],
            "availableFilters": _empty_available_filters(),
            "scopedEntryDefaulted": bool(origin_screen_id or scope_filter),
            "originScreenId": origin_screen_id,
            "scopeFilter": scope_filter,
        },
        "groupSummaries": [],
        "warningItems": [],
        "trustGuidance": [],
        "returnNavigation": _build_return_navigation(
            origin_screen_id=origin_screen_id,
            scope_filter=scope_filter,
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
        ),
        "emptyState": None,
    }


def _build_warning_items(state) -> List[Dict[str, Any]]:
    if state is None:
        return []
    return sorted(
        [_build_warning_item(signal) for signal in state.signals],
        key=_warning_item_sort_key,
    )


def _build_warning_item(signal: ScreenWarningTrustSignal) -> Dict[str, Any]:
    affected_workflow = _derive_affected_workflow(signal)
    affected_scope = _derive_affected_scope(signal=signal, affected_workflow=affected_workflow)
    classification = _derive_classification(signal)
    classification_label = {
        "blocking": "Blocking",
        "advisory": "Advisory",
        "trust_limited": "Trust-limited",
    }[classification]
    return {
        "itemId": signal.signal_id,
        "classification": classification,
        "classificationLabel": classification_label,
        "signalType": signal.signal_type,
        "severity": signal.severity,
        "code": signal.code,
        "message": signal.message,
        "interpretationCategory": signal.interpretation_category,
        "affectedWorkflow": affected_workflow,
        "affectedScope": affected_scope,
        "sourceIssueService": signal.source_issue_service,
        "sourceFact": {
            "factId": signal.source_fact_id,
            "factType": signal.source_fact_type,
            "factSeverity": signal.source_fact_severity,
        },
        "navigationTarget": {
            "screen": affected_workflow,
            "scope": affected_scope,
            "planningContextKey": signal.planning_context_key,
            "sourceSnapshotId": signal.source_snapshot_id,
        },
        "trustGuidance": {
            "present": classification == "trust_limited",
            "title": "Trust-limited interpretation" if classification == "trust_limited" else None,
            "message": signal.message if classification == "trust_limited" else None,
        },
    }


def _derive_affected_workflow(signal: ScreenWarningTrustSignal) -> Dict[str, str]:
    if signal.source_issue_service == "Integration Service":
        return {"id": "S02", "label": SCREEN_LABELS["S02"]}
    if signal.source_issue_service == "Review & Approval Service":
        return {"id": "S04", "label": SCREEN_LABELS["S04"]}
    if signal.source_issue_service == "Planning Engine Service":
        if signal.entity_type == "resource":
            return {"id": "S03", "label": SCREEN_LABELS["S03"]}
        return {"id": "S01", "label": SCREEN_LABELS["S01"]}
    return {"id": "S05", "label": SCREEN_LABELS["S05"]}


def _derive_affected_scope(
    signal: ScreenWarningTrustSignal,
    affected_workflow: Dict[str, str],
) -> Dict[str, Optional[str]]:
    workflow_id = affected_workflow["id"]
    if workflow_id == "S02":
        return {
            "scopeType": "setup",
            "scopeId": None,
            "scopeExternalId": None,
            "scopeLabel": "Planning Setup",
        }
    if workflow_id == "S04":
        scope_type = (
            "activation"
            if signal.interpretation_category == "activation_blocker"
            else "review"
        )
        return {
            "scopeType": scope_type,
            "scopeId": signal.entity_id,
            "scopeExternalId": signal.entity_external_id,
            "scopeLabel": signal.entity_external_id or signal.entity_id or affected_workflow["label"],
        }
    if workflow_id == "S03":
        return {
            "scopeType": "resource",
            "scopeId": signal.entity_id,
            "scopeExternalId": signal.entity_external_id,
            "scopeLabel": signal.entity_external_id or signal.entity_id or "Selected resource",
        }
    if signal.entity_type is None:
        return {
            "scopeType": "portfolio",
            "scopeId": None,
            "scopeExternalId": None,
            "scopeLabel": "Portfolio",
        }
    return {
        "scopeType": signal.entity_type,
        "scopeId": signal.entity_id,
        "scopeExternalId": signal.entity_external_id,
        "scopeLabel": signal.entity_external_id or signal.entity_id or signal.entity_type,
    }


def _derive_classification(signal: ScreenWarningTrustSignal) -> str:
    if signal.blocking or not signal.advisory:
        return "blocking"
    if signal.signal_type == "trust" or signal.interpretation_category == "trust_limited":
        return "trust_limited"
    return "advisory"


def _matches_filters(
    item: Dict[str, Any],
    workflow_ids: List[str],
    classification_filters: List[str],
    signal_type_filters: List[str],
    scope_filter: Optional[Dict[str, Optional[str]]],
) -> bool:
    if workflow_ids and item["affectedWorkflow"]["id"] not in workflow_ids:
        return False
    if classification_filters and item["classification"] not in classification_filters:
        return False
    if signal_type_filters and item["signalType"] not in signal_type_filters:
        return False
    if scope_filter is None:
        return True

    affected_scope = item["affectedScope"]
    if (
        scope_filter["scopeType"] is not None
        and affected_scope["scopeType"] != scope_filter["scopeType"]
    ):
        return False
    if (
        scope_filter["scopeId"] is not None
        and affected_scope["scopeId"] != scope_filter["scopeId"]
    ):
        return False
    if (
        scope_filter["scopeExternalId"] is not None
        and affected_scope["scopeExternalId"] != scope_filter["scopeExternalId"]
    ):
        return False
    return True


def _build_group_summaries(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summaries_by_workflow: Dict[str, Dict[str, Any]] = {}
    for item in items:
        workflow_id = item["affectedWorkflow"]["id"]
        summary = summaries_by_workflow.setdefault(
            workflow_id,
            {
                "workflowId": workflow_id,
                "workflowLabel": item["affectedWorkflow"]["label"],
                "itemCount": 0,
                "blockingCount": 0,
                "advisoryCount": 0,
                "trustLimitedCount": 0,
            },
        )
        summary["itemCount"] += 1
        if item["classification"] == "blocking":
            summary["blockingCount"] += 1
        elif item["classification"] == "trust_limited":
            summary["trustLimitedCount"] += 1
        else:
            summary["advisoryCount"] += 1

    return sorted(summaries_by_workflow.values(), key=lambda summary: summary["workflowId"])


def _build_workspace_summary(
    state,
    filtered_items: List[Dict[str, Any]],
    group_summaries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    blocking_count = len(
        [item for item in filtered_items if item["classification"] == "blocking"]
    )
    advisory_count = len(
        [item for item in filtered_items if item["classification"] == "advisory"]
    )
    trust_limited_count = len(
        [item for item in filtered_items if item["classification"] == "trust_limited"]
    )
    return {
        "totalSignalCount": 0 if state is None else state.active_signal_count,
        "filteredSignalCount": len(filtered_items),
        "blockingWarningCount": blocking_count,
        "advisoryWarningCount": advisory_count,
        "trustLimitedCount": trust_limited_count,
        "affectedWorkflowCount": len(group_summaries),
        "warningHeavy": len(filtered_items) >= WARNING_HEAVY_THRESHOLD,
        "trustLimitedPresent": trust_limited_count > 0,
        "oneListPresentation": True,
    }


def _build_trust_guidance(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    trust_items = [item for item in items if item["trustGuidance"]["present"]]
    guidance_by_message: Dict[str, Dict[str, Any]] = {}
    for item in trust_items:
        key = item["trustGuidance"]["message"] or item["code"]
        guidance = guidance_by_message.setdefault(
            key,
            {
                "guidanceId": f"guidance::{item['code']}",
                "title": item["trustGuidance"]["title"],
                "message": item["trustGuidance"]["message"],
                "relatedItemCount": 0,
            },
        )
        guidance["relatedItemCount"] += 1
    return sorted(guidance_by_message.values(), key=lambda guidance: guidance["guidanceId"])


def _build_available_filters(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    workflow_options = _count_options(
        values=[(item["affectedWorkflow"]["id"], item["affectedWorkflow"]["label"]) for item in items],
        key_name="workflowId",
        label_name="workflowLabel",
    )
    classification_options = _count_options(
        values=[
            (item["classification"], item["classificationLabel"])
            for item in items
        ],
        key_name="id",
        label_name="label",
    )
    signal_type_options = _count_options(
        values=[(item["signalType"], item["signalType"].title()) for item in items],
        key_name="id",
        label_name="label",
    )
    return {
        "workflowOptions": workflow_options,
        "classificationOptions": classification_options,
        "signalTypeOptions": signal_type_options,
    }


def _count_options(
    values: List[tuple],
    key_name: str,
    label_name: str,
) -> List[Dict[str, Any]]:
    counts: Dict[str, Dict[str, Any]] = {}
    for item_id, label in values:
        option = counts.setdefault(
            item_id,
            {
                key_name: item_id,
                label_name: label,
                "count": 0,
            },
        )
        option["count"] += 1
    return sorted(counts.values(), key=lambda option: option[key_name])


def _build_scope_filter(
    scope_type: Optional[str],
    scope_id: Optional[str],
    scope_external_id: Optional[str],
    scope_label: Optional[str],
) -> Optional[Dict[str, Optional[str]]]:
    if not any([scope_type, scope_id, scope_external_id, scope_label]):
        return None
    return {
        "scopeType": scope_type,
        "scopeId": scope_id,
        "scopeExternalId": scope_external_id,
        "scopeLabel": scope_label,
    }


def _build_return_navigation(
    origin_screen_id: Optional[str],
    scope_filter: Optional[Dict[str, Optional[str]]],
    planning_context_key: Optional[str],
    source_snapshot_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if origin_screen_id is None:
        return None
    return {
        "screen": {"id": origin_screen_id, "label": SCREEN_LABELS[origin_screen_id]},
        "scope": scope_filter,
        "planningContextKey": planning_context_key,
        "sourceSnapshotId": source_snapshot_id,
    }


def _build_empty_state(
    state,
    filtered_items: List[Dict[str, Any]],
    is_loading: bool,
) -> Optional[Dict[str, Any]]:
    if is_loading:
        return None
    if filtered_items:
        return None
    if state is None or state.active_signal_count == 0:
        return {
            "reason": "no_active_warnings",
            "message": "There are no interpreted warnings or trust-limited states in the current scope.",
        }
    return {
        "reason": "no_matching_warnings",
        "message": "No warnings match the current workspace filters.",
    }


def _build_view_state(
    filtered_items: List[Dict[str, Any]],
    workspace_summary: Dict[str, Any],
    is_loading: bool,
    is_refreshing: bool,
) -> Dict[str, Any]:
    if is_loading:
        screen_state = "loading"
    elif not filtered_items:
        screen_state = "no_warnings"
    elif workspace_summary["warningHeavy"]:
        screen_state = "warning_heavy"
    elif (
        workspace_summary["trustLimitedCount"] > 0
        and workspace_summary["blockingWarningCount"] == 0
        and workspace_summary["advisoryWarningCount"] == 0
    ):
        screen_state = "trust_limited"
    else:
        screen_state = "ready"
    return {
        "screenState": screen_state,
        "isLoading": is_loading,
        "isRefreshing": is_refreshing,
        "accessRestricted": False,
        "accessRestrictedReason": None,
    }


def _warning_item_sort_key(item: Dict[str, Any]) -> tuple:
    classification_rank = {
        "blocking": 0,
        "trust_limited": 1,
        "advisory": 2,
    }[item["classification"]]
    return (
        item["affectedWorkflow"]["id"],
        classification_rank,
        item["signalType"],
        item["code"],
        item["itemId"],
    )


def _empty_workspace_summary() -> Dict[str, Any]:
    return {
        "totalSignalCount": 0,
        "filteredSignalCount": 0,
        "blockingWarningCount": 0,
        "advisoryWarningCount": 0,
        "trustLimitedCount": 0,
        "affectedWorkflowCount": 0,
        "warningHeavy": False,
        "trustLimitedPresent": False,
        "oneListPresentation": True,
    }


def _empty_available_filters() -> Dict[str, Any]:
    return {
        "workflowOptions": [],
        "classificationOptions": [],
        "signalTypeOptions": [],
    }
