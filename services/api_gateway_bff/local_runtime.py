"""Local seeded runtime assembly for browser-usable MVP flows."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.decision_support_service import (
    DecisionSupportService,
    ScreenWarningTrustSignal,
)
from services.integration_service import (
    BoundedWriteBackExecutionReceipt,
    BoundedWriteBackItemResult,
    ExternalWriteBackGateway,
    IntegrationService,
    WRITE_BACK_ITEM_STATUS_SUCCEEDED,
)
from services.planning_engine_service import PlanningEngineService
from services.planning_engine_service.gateway import PlanningEngineWorkflowGateway
from services.review_approval_service import (
    ApprovedOperatingPlanSnapshot,
    ApprovedPlanProjectRecord,
    ApprovedPlanTaskRecord,
    RecommendationOriginReference,
    ReviewApprovalService,
)
from services.workflow_orchestrator_service import (
    IntegrationBackedActivationExecutionGateway,
    IntegrationBackedImportSyncExecutionGateway,
    PlanningRunTrigger,
    WorkflowOrchestratorService,
)

from .transport import ApiGatewayBffApplication, ApiGatewayBffDependencies


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
LOCAL_DEMO_PLANNING_CONTEXT_KEY = "context::frontend-shell"
LOCAL_DEMO_REQUESTED_BY = "planner@example.com"
LOCAL_DEMO_RESOURCE_EXTERNAL_ID = "user-ada"
LOCAL_DEMO_SOURCE_FIXTURE = "source_plan_schedule_happy_path.json"
LOCAL_DEMO_REVIEW_FIXTURE = "review_approval_delta_dependency_linked.json"
LOCAL_DEMO_S05_WARNING_FIXTURE = "decision_support_s05_workspace_heavy.json"
LOCAL_DEMO_S03_WARNING_FIXTURE = "decision_support_s03_warning_context_heavy.json"
LOCAL_DEMO_DRILLDOWN_DATE = "2026-04-08"
LOCAL_DEMO_DRILLDOWN_WEEK_START = "2026-04-06"
LOCAL_DEMO_BOOT_TIME = "2026-04-08T09:00:00Z"


@dataclass(frozen=True)
class LocalDemoSeedState:
    planning_context_key: str
    source_snapshot_id: str
    planning_run_id: str
    review_context_id: str
    approved_plan_id: str
    resource_external_id: str
    drilldown_date: str
    drilldown_week_start: str
    connected_set_delta_id: str


@dataclass(frozen=True)
class LocalDemoRuntime:
    dependencies: ApiGatewayBffDependencies
    seed_state: LocalDemoSeedState
    workflow_auto_progressor: "LocalWorkflowAutoProgressor"

    def build_application(self) -> ApiGatewayBffApplication:
        return ApiGatewayBffApplication(self.dependencies)


class LocalDeterministicWriteBackGateway(ExternalWriteBackGateway):
    """Local-only bounded write-back adapter for deterministic MVP startup."""

    def execute_write_back(self, request) -> BoundedWriteBackExecutionReceipt:
        return BoundedWriteBackExecutionReceipt(
            completed_at=request.requested_at,
            item_results=[
                BoundedWriteBackItemResult(
                    target_id=target.target_id,
                    delta_id=target.delta_id,
                    entity_type=target.entity_type,
                    entity_external_id=target.entity_external_id,
                    status=WRITE_BACK_ITEM_STATUS_SUCCEEDED,
                    applied_fields=sorted(target.write_back_fields),
                    error_code=None,
                    error_message=None,
                )
                for target in request.targets
            ],
        )


class LocalWorkflowAutoProgressor:
    """Local helper that advances async workflow state for browser smoke flows."""

    def __init__(
        self,
        workflow_orchestrator_service: WorkflowOrchestratorService,
        *,
        poll_interval_seconds: float = 0.35,
    ) -> None:
        self._workflow_orchestrator_service = workflow_orchestrator_service
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="local-mvp-auto-progressor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def tick(self, occurred_at: Optional[str] = None) -> bool:
        timestamp = occurred_at or _now_iso()
        progressed = False
        progressed = self._progress_planning_workflow(timestamp) or progressed
        progressed = self._progress_activation_workflow(timestamp) or progressed
        return progressed

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            progressed = self.tick()
            self._stop_event.wait(0.1 if progressed else self._poll_interval_seconds)

    def _progress_planning_workflow(self, occurred_at: str) -> bool:
        status = self._workflow_orchestrator_service.get_planning_run_status()
        if status is None:
            return False
        if status.status == "dispatched":
            self._workflow_orchestrator_service.mark_planning_run_running(
                workflow_instance_id=status.workflow_instance_id,
                occurred_at=occurred_at,
            )
            return True
        if status.status == "running":
            self._workflow_orchestrator_service.mark_planning_run_succeeded(
                workflow_instance_id=status.workflow_instance_id,
                occurred_at=occurred_at,
            )
            return True
        if status.status == "retry_pending":
            self._workflow_orchestrator_service.retry_planning_run(
                workflow_instance_id=status.workflow_instance_id,
                retried_at=occurred_at,
            )
            return True
        return False

    def _progress_activation_workflow(self, occurred_at: str) -> bool:
        status = self._workflow_orchestrator_service.get_activation_workflow_status()
        if status is None:
            return False
        if status.status == "dispatched":
            self._workflow_orchestrator_service.mark_activation_step_running(
                workflow_instance_id=status.workflow_instance_id,
                step_name=status.current_step,
                occurred_at=occurred_at,
            )
            return True
        if status.status == "running":
            self._workflow_orchestrator_service.mark_activation_step_succeeded(
                workflow_instance_id=status.workflow_instance_id,
                step_name=status.current_step,
                occurred_at=occurred_at,
            )
            return True
        if status.status == "retry_pending":
            self._workflow_orchestrator_service.retry_activation_workflow(
                workflow_instance_id=status.workflow_instance_id,
                retried_at=occurred_at,
            )
            return True
        return False


def build_local_demo_runtime() -> LocalDemoRuntime:
    integration_service = IntegrationService(
        external_write_back_gateway=LocalDeterministicWriteBackGateway()
    )
    planning_engine_service = PlanningEngineService()
    decision_support_service = DecisionSupportService()
    review_approval_service = ReviewApprovalService()
    workflow_orchestrator_service = WorkflowOrchestratorService(
        integration_service=integration_service,
        planning_engine_gateway=PlanningEngineWorkflowGateway(
            integration_service=integration_service,
            planning_engine_service=planning_engine_service,
        ),
        import_sync_execution_gateway=IntegrationBackedImportSyncExecutionGateway(
            integration_service=integration_service
        ),
        activation_execution_gateway=IntegrationBackedActivationExecutionGateway(
            integration_service=integration_service
        ),
    )

    bundle = integration_service.import_source_plan(
        _load_fixture(LOCAL_DEMO_SOURCE_FIXTURE)
    )
    planning_start = workflow_orchestrator_service.start_planning_run(
        PlanningRunTrigger(
            planning_context_key=LOCAL_DEMO_PLANNING_CONTEXT_KEY,
            source_snapshot_id=bundle.snapshot.snapshot_id,
            requested_by=LOCAL_DEMO_REQUESTED_BY,
            requested_at=LOCAL_DEMO_BOOT_TIME,
            idempotency_key="local-demo-seed-planning-run",
            max_attempts=2,
        )
    )
    workflow_orchestrator_service.mark_planning_run_running(
        workflow_instance_id=planning_start.workflow_instance.workflow_instance_id,
        occurred_at=_offset_time(LOCAL_DEMO_BOOT_TIME, seconds=30),
    )
    workflow_orchestrator_service.mark_planning_run_succeeded(
        workflow_instance_id=planning_start.workflow_instance.workflow_instance_id,
        occurred_at=_offset_time(LOCAL_DEMO_BOOT_TIME, minutes=1),
    )
    execution_result = planning_engine_service.get_execution_result(
        planning_run_id=planning_start.workflow_instance.planning_engine_run_id
    )
    if execution_result is None:
        raise RuntimeError("Local demo runtime requires a saved seeded planning run.")

    decision_support_service.refresh_resource_recommendation_context(
        execution_result=execution_result,
        resource_external_id=LOCAL_DEMO_RESOURCE_EXTERNAL_ID,
    )
    _publish_fixture_signals(
        decision_support_service=decision_support_service,
        fixture_name=LOCAL_DEMO_S03_WARNING_FIXTURE,
        screen_id="S03",
        planning_context_key=LOCAL_DEMO_PLANNING_CONTEXT_KEY,
        source_snapshot_id=bundle.snapshot.snapshot_id,
    )

    review_scenario = _load_fixture(LOCAL_DEMO_REVIEW_FIXTURE)
    review_context = review_approval_service.generate_reviewable_delta_set(
        execution_result=execution_result,
        approved_plan_snapshot=_build_approved_plan_snapshot(review_scenario),
        recommendation_origin_refs=_build_recommendation_origin_refs(review_scenario),
    )

    _publish_fixture_signals(
        decision_support_service=decision_support_service,
        fixture_name=LOCAL_DEMO_S05_WARNING_FIXTURE,
        screen_id="S05",
        planning_context_key=LOCAL_DEMO_PLANNING_CONTEXT_KEY,
        source_snapshot_id=bundle.snapshot.snapshot_id,
        review_context_id=review_context.review_context_id,
    )

    connected_set_delta_id = _find_connected_set_delta_id(review_context)
    if connected_set_delta_id is None:
        raise RuntimeError("Local demo runtime requires a connected-set delta for M01.")

    dependencies = ApiGatewayBffDependencies(
        integration_service=integration_service,
        planning_engine_service=planning_engine_service,
        review_approval_service=review_approval_service,
        decision_support_service=decision_support_service,
        workflow_orchestrator_service=workflow_orchestrator_service,
    )
    seed_state = LocalDemoSeedState(
        planning_context_key=LOCAL_DEMO_PLANNING_CONTEXT_KEY,
        source_snapshot_id=bundle.snapshot.snapshot_id,
        planning_run_id=execution_result.execution_record.planning_run_id,
        review_context_id=review_context.review_context_id,
        approved_plan_id=review_context.approved_plan_id,
        resource_external_id=LOCAL_DEMO_RESOURCE_EXTERNAL_ID,
        drilldown_date=LOCAL_DEMO_DRILLDOWN_DATE,
        drilldown_week_start=LOCAL_DEMO_DRILLDOWN_WEEK_START,
        connected_set_delta_id=connected_set_delta_id,
    )
    return LocalDemoRuntime(
        dependencies=dependencies,
        seed_state=seed_state,
        workflow_auto_progressor=LocalWorkflowAutoProgressor(
            workflow_orchestrator_service
        ),
    )


def build_local_demo_application() -> ApiGatewayBffApplication:
    return build_local_demo_runtime().build_application()


def _load_fixture(name: str) -> Dict[str, Any]:
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _build_approved_plan_snapshot(
    scenario: Dict[str, Any]
) -> ApprovedOperatingPlanSnapshot:
    return ApprovedOperatingPlanSnapshot(
        approved_plan_id=scenario["approved_plan"]["approved_plan_id"],
        projects=[
            ApprovedPlanProjectRecord(
                project_id=project.get("project_id"),
                project_external_id=project["project_external_id"],
                project_name=project["project_name"],
                finish_date=project.get("finish_date"),
            )
            for project in scenario["approved_plan"]["projects"]
        ],
        tasks=[
            ApprovedPlanTaskRecord(
                task_id=task.get("task_id"),
                task_external_id=task["task_external_id"],
                task_name=task["task_name"],
                project_id=task.get("project_id"),
                project_external_id=task["project_external_id"],
                approved_start_date=task.get("approved_start_date"),
                approved_due_date=task.get("approved_due_date"),
                assigned_resource_external_ids=list(
                    task.get("assigned_resource_external_ids", [])
                ),
                item_type=task.get("item_type", "task"),
            )
            for task in scenario["approved_plan"]["tasks"]
        ],
    )


def _build_recommendation_origin_refs(
    scenario: Dict[str, Any]
) -> List[RecommendationOriginReference]:
    return [
        RecommendationOriginReference(
            recommendation_id=item["recommendation_id"],
            origin_screen_id=item["origin_screen_id"],
            project_external_id=item.get("project_external_id"),
            task_external_id=item["task_external_id"],
            requires_review_handoff=item["requires_review_handoff"],
        )
        for item in scenario.get("recommendation_origin_refs", [])
    ]


def _publish_fixture_signals(
    decision_support_service: DecisionSupportService,
    fixture_name: str,
    screen_id: str,
    planning_context_key: str,
    source_snapshot_id: str,
    review_context_id: Optional[str] = None,
) -> None:
    payload = _load_fixture(fixture_name)
    signals = []
    for signal_payload in payload.get("signals", []):
        entity_id = signal_payload.get("entity_id")
        entity_external_id = signal_payload.get("entity_external_id")
        if (
            review_context_id is not None
            and signal_payload.get("source_issue_service") == "Review & Approval Service"
            and signal_payload.get("entity_type") == "review_context"
        ):
            entity_id = review_context_id
            entity_external_id = review_context_id
        signals.append(
            ScreenWarningTrustSignal(
                signal_id=signal_payload["signal_id"],
                screen_id=screen_id,
                source_snapshot_id=source_snapshot_id,
                planning_context_key=planning_context_key,
                signal_type=signal_payload["signal_type"],
                severity=signal_payload["severity"],
                code=signal_payload["code"],
                message=signal_payload["message"],
                advisory=signal_payload["advisory"],
                blocking=signal_payload["blocking"],
                interpretation_category=signal_payload["interpretation_category"],
                source_issue_service=signal_payload["source_issue_service"],
                source_fact_id=signal_payload["source_fact_id"],
                source_fact_type=signal_payload["source_fact_type"],
                source_fact_severity=signal_payload["source_fact_severity"],
                entity_type=signal_payload.get("entity_type"),
                entity_id=entity_id,
                entity_external_id=entity_external_id,
            )
        )
    decision_support_service.publish_screen_warning_trust_state(
        screen_id=screen_id,
        signals=signals,
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
    )


def _find_connected_set_delta_id(review_context) -> Optional[str]:
    for delta in review_context.delta_items:
        if delta.connected_set_id:
            return delta.delta_id
    return None


def _offset_time(base_time: str, *, minutes: int = 0, seconds: int = 0) -> str:
    resolved = datetime.fromisoformat(base_time.replace("Z", "+00:00")) + timedelta(
        minutes=minutes,
        seconds=seconds,
    )
    return resolved.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
