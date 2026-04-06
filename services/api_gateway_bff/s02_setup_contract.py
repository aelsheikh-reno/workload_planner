"""S02 — Planning Setup read-model composition adapter."""

from typing import Any, Dict, List, Optional

from services.decision_support_service.service import DecisionSupportService
from services.integration_service.service import IntegrationService
from services.planning_engine_service.service import PlanningEngineService
from services.workflow_orchestrator_service.service import WorkflowOrchestratorService


SCREEN_ID = "S02"
SCREEN_LABEL = "Planning Setup"
OVERALL_READINESS_BASIS = "s02_bff_composed_readiness"
SOURCE_ONLY_READINESS_BASIS = "source_readiness_only"


def build_s02_setup_contract(
    integration_service: IntegrationService,
    planning_engine_service: Optional[PlanningEngineService] = None,
    decision_support_service: Optional[DecisionSupportService] = None,
    workflow_orchestrator_service: Optional[WorkflowOrchestratorService] = None,
    planning_context_key: Optional[str] = None,
    snapshot_id: Optional[str] = None,
    is_refreshing: bool = False,
    access_restricted: bool = False,
    access_restricted_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose the S02 read contract from authoritative downstream service outputs."""

    stubbed_dependencies = _build_stubbed_dependencies(
        planning_engine_service=planning_engine_service,
        decision_support_service=decision_support_service,
        workflow_orchestrator_service=workflow_orchestrator_service,
    )

    if access_restricted:
        return _build_access_restricted_contract(
            stubbed_dependencies=stubbed_dependencies,
            planning_context_key=planning_context_key,
            snapshot_id=snapshot_id,
            is_refreshing=is_refreshing,
            access_restricted_reason=access_restricted_reason,
        )

    bundle = integration_service.get_normalized_source_bundle(snapshot_id=snapshot_id)
    resolved_snapshot_id = bundle.snapshot.snapshot_id if bundle is not None else snapshot_id

    source_readiness = _serialize_source_readiness(bundle)
    source_setup_issues = _serialize_source_setup_issues(bundle)
    planning_run_status = _serialize_planning_run_status(
        workflow_orchestrator_service=workflow_orchestrator_service,
        planning_context_key=planning_context_key,
        snapshot_id=resolved_snapshot_id,
    )
    capacity_input_readiness, capacity_input_issues = _serialize_capacity_projection(
        planning_engine_service=planning_engine_service,
        bundle=bundle,
    )
    setup_warning_trust_state = _serialize_setup_warning_trust_state(
        decision_support_service=decision_support_service,
        planning_context_key=planning_context_key,
        snapshot_id=resolved_snapshot_id,
    )
    no_runnable_plan_blockers = _compose_no_runnable_plan_blockers(
        bundle=bundle,
        source_setup_issues=source_setup_issues,
        capacity_input_issues=capacity_input_issues,
    )
    advisory_signals = _compose_advisory_signals(
        source_setup_issues=source_setup_issues,
        capacity_input_issues=capacity_input_issues,
        setup_warning_trust_state=setup_warning_trust_state,
    )
    overall_readiness = _compose_overall_readiness(
        source_readiness=source_readiness,
        capacity_input_readiness=capacity_input_readiness,
        no_runnable_plan_blockers=no_runnable_plan_blockers,
        advisory_signals=advisory_signals,
    )
    view_state = {
        "screenState": _derive_screen_state(overall_readiness["state"]),
        "isRefreshing": is_refreshing,
        "accessRestricted": False,
        "accessRestrictedReason": None,
    }

    return {
        "screen": {"id": SCREEN_ID, "label": SCREEN_LABEL},
        "queryContext": {
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": resolved_snapshot_id,
        },
        "viewState": view_state,
        "sourceReadiness": source_readiness,
        "capacityInputReadiness": capacity_input_readiness,
        "overallReadiness": overall_readiness,
        "latestImport": _serialize_latest_import(bundle),
        "planningRunStatus": planning_run_status,
        "sourceSetupIssues": source_setup_issues,
        "capacityInputIssues": capacity_input_issues,
        "setupWarningTrustState": setup_warning_trust_state,
        "noRunnablePlanBlockers": no_runnable_plan_blockers,
        "advisorySignals": advisory_signals,
        "stubbedDependencies": stubbed_dependencies,
    }


def _build_access_restricted_contract(
    stubbed_dependencies: List[str],
    planning_context_key: Optional[str],
    snapshot_id: Optional[str],
    is_refreshing: bool,
    access_restricted_reason: Optional[str],
) -> Dict[str, Any]:
    return {
        "screen": {"id": SCREEN_ID, "label": SCREEN_LABEL},
        "queryContext": {
            "planningContextKey": planning_context_key,
            "sourceSnapshotId": snapshot_id,
        },
        "viewState": {
            "screenState": "access_restricted",
            "isRefreshing": is_refreshing,
            "accessRestricted": True,
            "accessRestrictedReason": access_restricted_reason or "access_denied",
        },
        "sourceReadiness": None,
        "capacityInputReadiness": None,
        "overallReadiness": None,
        "latestImport": None,
        "planningRunStatus": None,
        "sourceSetupIssues": [],
        "capacityInputIssues": [],
        "setupWarningTrustState": _empty_setup_warning_trust_state(stubbed=False),
        "noRunnablePlanBlockers": [],
        "advisorySignals": [],
        "stubbedDependencies": stubbed_dependencies,
    }


def _build_stubbed_dependencies(
    planning_engine_service: Optional[PlanningEngineService],
    decision_support_service: Optional[DecisionSupportService],
    workflow_orchestrator_service: Optional[WorkflowOrchestratorService],
) -> List[str]:
    stubbed_dependencies = []
    if planning_engine_service is None:
        stubbed_dependencies.append("capacityInputReadiness")
    if decision_support_service is None:
        stubbed_dependencies.append("warningTrustState")
    if workflow_orchestrator_service is None:
        stubbed_dependencies.extend(["planningRunStatus", "workflowOrchestration"])
    return stubbed_dependencies


def _serialize_source_readiness(bundle) -> Dict[str, Any]:
    if bundle is None:
        return {
            "state": "missing",
            "runnable": False,
            "blockingIssueCount": 0,
            "advisoryIssueCount": 0,
            "totalIssueCount": 0,
        }
    return {
        "state": bundle.source_readiness.state,
        "runnable": bundle.source_readiness.runnable,
        "blockingIssueCount": bundle.source_readiness.blocking_issue_count,
        "advisoryIssueCount": bundle.source_readiness.advisory_issue_count,
        "totalIssueCount": bundle.source_readiness.total_issue_count,
    }


def _serialize_source_setup_issues(bundle) -> List[Dict[str, Any]]:
    if bundle is None:
        return []
    return [
        {
            "ownerService": "Integration Service",
            "severity": issue.severity,
            "code": issue.code,
            "message": issue.message,
            "entityType": issue.entity_type,
            "entityExternalId": issue.entity_external_id,
            "field": issue.field,
        }
        for issue in bundle.issue_facts
    ]


def _serialize_capacity_projection(
    planning_engine_service: Optional[PlanningEngineService],
    bundle,
) -> Any:
    if planning_engine_service is None:
        return (
            {
                "state": "stubbed",
                "runnable": None,
                "blockingIssueCount": None,
                "advisoryIssueCount": None,
                "totalIssueCount": None,
                "stubbed": True,
            },
            [],
        )
    if bundle is None:
        return (
            {
                "state": "missing",
                "runnable": False,
                "blockingIssueCount": 0,
                "advisoryIssueCount": 0,
                "totalIssueCount": 0,
                "stubbed": False,
            },
            [],
        )

    capacity_result = planning_engine_service.get_capacity_model(
        source_snapshot_id=bundle.snapshot.snapshot_id
    )
    if capacity_result is None:
        capacity_result = planning_engine_service.build_daily_capacity_model(bundle)

    return (
        {
            "state": capacity_result.input_readiness.state,
            "runnable": capacity_result.input_readiness.runnable,
            "blockingIssueCount": capacity_result.input_readiness.blocking_issue_count,
            "advisoryIssueCount": capacity_result.input_readiness.advisory_issue_count,
            "totalIssueCount": capacity_result.input_readiness.total_issue_count,
            "stubbed": False,
        },
        [
            {
                "ownerService": "Planning Engine Service",
                "severity": issue.severity,
                "code": issue.code,
                "message": issue.message,
                "resourceExternalId": issue.resource_external_id,
                "field": issue.field,
            }
            for issue in capacity_result.input_issues
        ],
    )


def _serialize_setup_warning_trust_state(
    decision_support_service: Optional[DecisionSupportService],
    planning_context_key: Optional[str],
    snapshot_id: Optional[str],
) -> Dict[str, Any]:
    if decision_support_service is None:
        return _empty_setup_warning_trust_state(stubbed=True)

    state = decision_support_service.get_screen_warning_trust_state(
        screen_id=SCREEN_ID,
        planning_context_key=planning_context_key,
        source_snapshot_id=snapshot_id,
    )
    if state is None:
        return _empty_setup_warning_trust_state(stubbed=False)

    return {
        "activeSignalCount": state.active_signal_count,
        "advisorySignalCount": state.active_signal_count,
        "blockingSignalCount": 0,
        "signals": [
            {
                "ownerService": "Decision Support Service",
                "signalId": signal.signal_id,
                "signalType": signal.signal_type,
                "severity": signal.severity,
                "code": signal.code,
                "message": signal.message,
                "advisory": True,
            }
            for signal in state.signals
        ],
        "stubbed": False,
    }


def _empty_setup_warning_trust_state(stubbed: bool) -> Dict[str, Any]:
    return {
        "activeSignalCount": 0,
        "advisorySignalCount": 0,
        "blockingSignalCount": 0,
        "signals": [],
        "stubbed": stubbed,
    }


def _serialize_planning_run_status(
    workflow_orchestrator_service: Optional[WorkflowOrchestratorService],
    planning_context_key: Optional[str],
    snapshot_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if workflow_orchestrator_service is None:
        return None

    planning_run_status_view = workflow_orchestrator_service.get_planning_run_status(
        planning_context_key=planning_context_key,
        source_snapshot_id=snapshot_id,
    )
    if planning_run_status_view is None:
        return None
    return {
        "workflowInstanceId": planning_run_status_view.workflow_instance_id,
        "planningContextKey": planning_run_status_view.planning_context_key,
        "sourceSnapshotId": planning_run_status_view.source_snapshot_id,
        "sourceArtifactId": planning_run_status_view.source_artifact_id,
        "planningRunId": planning_run_status_view.planning_engine_run_id,
        "status": planning_run_status_view.status,
        "currentStep": planning_run_status_view.current_step,
        "currentAttempt": planning_run_status_view.current_attempt,
        "maxAttempts": planning_run_status_view.max_attempts,
        "requestedBy": planning_run_status_view.requested_by,
        "requestedAt": planning_run_status_view.requested_at,
        "lastTransitionAt": planning_run_status_view.last_transition_at,
        "completedAt": planning_run_status_view.completed_at,
        "lastErrorCode": planning_run_status_view.last_error_code,
        "lastErrorMessage": planning_run_status_view.last_error_message,
    }


def _serialize_latest_import(bundle) -> Optional[Dict[str, Any]]:
    if bundle is None:
        return None
    return {
        "snapshotId": bundle.snapshot.snapshot_id,
        "artifactId": bundle.artifact.artifact_id,
        "externalArtifactId": bundle.artifact.external_artifact_id,
        "sourceSystem": bundle.snapshot.source_system,
        "capturedAt": bundle.snapshot.captured_at,
        "projectCount": bundle.snapshot.project_count,
        "taskCount": bundle.snapshot.task_count,
        "dependencyCount": bundle.snapshot.dependency_count,
        "assignmentCount": bundle.snapshot.assignment_count,
    }


def _compose_no_runnable_plan_blockers(
    bundle,
    source_setup_issues: List[Dict[str, Any]],
    capacity_input_issues: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if bundle is None:
        return [
            {
                "ownerService": "Integration Service",
                "kind": "source_readiness",
                "severity": "blocking",
                "code": "missing_normalized_source_snapshot",
                "message": "A normalized source snapshot is required before planning can run.",
            }
        ]

    blockers = [
        {
            "ownerService": issue["ownerService"],
            "kind": "source_setup_issue",
            "severity": issue["severity"],
            "code": issue["code"],
            "message": issue["message"],
            "field": issue["field"],
            "entityType": issue["entityType"],
            "entityExternalId": issue["entityExternalId"],
        }
        for issue in source_setup_issues
        if issue["severity"] == "blocking"
    ]

    source_is_blocked = not bundle.source_readiness.runnable
    for issue in capacity_input_issues:
        if issue["severity"] != "blocking":
            continue
        if source_is_blocked and issue["code"] == "source_snapshot_not_runnable":
            continue
        blockers.append(
            {
                "ownerService": issue["ownerService"],
                "kind": "capacity_input_issue",
                "severity": issue["severity"],
                "code": issue["code"],
                "message": issue["message"],
                "field": issue["field"],
                "resourceExternalId": issue["resourceExternalId"],
            }
        )
    return blockers


def _compose_advisory_signals(
    source_setup_issues: List[Dict[str, Any]],
    capacity_input_issues: List[Dict[str, Any]],
    setup_warning_trust_state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    advisory_signals = [
        {
            "ownerService": issue["ownerService"],
            "kind": "source_setup_issue",
            "severity": issue["severity"],
            "code": issue["code"],
            "message": issue["message"],
            "field": issue["field"],
            "entityType": issue["entityType"],
            "entityExternalId": issue["entityExternalId"],
        }
        for issue in source_setup_issues
        if issue["severity"] != "blocking"
    ]
    advisory_signals.extend(
        {
            "ownerService": issue["ownerService"],
            "kind": "capacity_input_issue",
            "severity": issue["severity"],
            "code": issue["code"],
            "message": issue["message"],
            "field": issue["field"],
            "resourceExternalId": issue["resourceExternalId"],
        }
        for issue in capacity_input_issues
        if issue["severity"] != "blocking"
    )
    advisory_signals.extend(
        {
            "ownerService": signal["ownerService"],
            "kind": "warning_trust_signal",
            "signalId": signal["signalId"],
            "signalType": signal["signalType"],
            "severity": signal["severity"],
            "code": signal["code"],
            "message": signal["message"],
            "advisory": signal["advisory"],
        }
        for signal in setup_warning_trust_state["signals"]
    )
    return advisory_signals


def _compose_overall_readiness(
    source_readiness: Dict[str, Any],
    capacity_input_readiness: Dict[str, Any],
    no_runnable_plan_blockers: List[Dict[str, Any]],
    advisory_signals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if capacity_input_readiness.get("stubbed"):
        if source_readiness["state"] == "missing":
            state = "missing"
            runnable = False
        elif no_runnable_plan_blockers:
            state = "blocked"
            runnable = False
        elif advisory_signals:
            state = "ready_with_advisories"
            runnable = True
        else:
            state = source_readiness["state"]
            runnable = source_readiness["runnable"]
        return {
            "state": state,
            "runnable": runnable,
            "canContinueToPlanning": runnable,
            "basis": SOURCE_ONLY_READINESS_BASIS,
            "noRunnablePlanBlockerCount": len(no_runnable_plan_blockers),
            "advisorySignalCount": len(advisory_signals),
        }

    if source_readiness["state"] == "missing":
        return {
            "state": "missing",
            "runnable": False,
            "canContinueToPlanning": False,
            "basis": OVERALL_READINESS_BASIS,
            "noRunnablePlanBlockerCount": len(no_runnable_plan_blockers),
            "advisorySignalCount": len(advisory_signals),
        }

    if no_runnable_plan_blockers:
        state = "blocked"
        runnable = False
    elif advisory_signals:
        state = "ready_with_advisories"
        runnable = True
    else:
        state = "ready"
        runnable = True

    return {
        "state": state,
        "runnable": runnable,
        "canContinueToPlanning": runnable,
        "basis": OVERALL_READINESS_BASIS,
        "noRunnablePlanBlockerCount": len(no_runnable_plan_blockers),
        "advisorySignalCount": len(advisory_signals),
    }


def _derive_screen_state(overall_readiness_state: str) -> str:
    if overall_readiness_state == "missing":
        return "missing"
    if overall_readiness_state == "blocked":
        return "blocked"
    if overall_readiness_state == "ready_with_advisories":
        return "partially_configured"
    return "ready"
