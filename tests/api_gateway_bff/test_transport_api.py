import json
import unittest
from pathlib import Path
from urllib.parse import urlencode

from services.api_gateway_bff import (
    ApiGatewayBffApplication,
    ApiGatewayBffDependencies,
    build_test_environ,
)
from services.decision_support_service import (
    DecisionSupportService,
    ScreenWarningTrustSignal,
)
from services.integration_service import IntegrationService
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
    ImportSyncExecutionGateway,
    ImportSyncExecutionReceipt,
    IntegrationBackedActivationExecutionGateway,
    IntegrationBackedImportSyncExecutionGateway,
    WorkflowOrchestratorService,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def build_approved_plan_snapshot(scenario):
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


def build_recommendation_origin_refs(scenario):
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


class ApiGatewayTransportTests(unittest.TestCase):
    def setUp(self):
        self.integration_service = IntegrationService()
        self.planning_engine_service = PlanningEngineService()
        self.decision_support_service = DecisionSupportService()
        self.review_approval_service = ReviewApprovalService()
        self.workflow_orchestrator_service = WorkflowOrchestratorService(
            integration_service=self.integration_service,
            planning_engine_gateway=PlanningEngineWorkflowGateway(
                integration_service=self.integration_service,
                planning_engine_service=self.planning_engine_service,
            ),
            import_sync_execution_gateway=IntegrationBackedImportSyncExecutionGateway(
                integration_service=self.integration_service
            ),
            activation_execution_gateway=IntegrationBackedActivationExecutionGateway(
                integration_service=self.integration_service
            ),
        )
        self.app = ApiGatewayBffApplication(
            ApiGatewayBffDependencies(
                integration_service=self.integration_service,
                planning_engine_service=self.planning_engine_service,
                review_approval_service=self.review_approval_service,
                decision_support_service=self.decision_support_service,
                workflow_orchestrator_service=self.workflow_orchestrator_service,
            )
        )

    def _request(self, method, path, query=None, body=None):
        status_holder = {}

        def start_response(status, headers):
            status_holder["status"] = status
            status_holder["headers"] = headers

        environ = build_test_environ(
            method=method,
            path=path,
            query_string=urlencode(query or {}, doseq=True),
            body=body,
        )
        response = b"".join(self.app(environ, start_response)).decode("utf-8")
        return (
            int(status_holder["status"].split()[0]),
            json.loads(response),
        )

    def _import_bundle(self, fixture_name):
        return self.integration_service.import_source_plan(load_fixture(fixture_name))

    def _execute_planning_run(self, fixture_name, planning_run_id, planning_context_key):
        bundle = self._import_bundle(fixture_name)
        execution_result = self.planning_engine_service.execute_planning_run(
            bundle=bundle,
            workflow_instance_id="workflow::%s" % planning_run_id,
            planning_context_key=planning_context_key,
            source_snapshot_id=bundle.snapshot.snapshot_id,
            source_artifact_id=bundle.artifact.artifact_id,
            requested_by="planner@example.com",
            requested_at="2026-04-07T09:00:00Z",
            attempt_number=1,
        )
        return bundle, execution_result

    def _create_review_context(self, execution_result, fixture_name):
        scenario = load_fixture(fixture_name)
        review_context = self.review_approval_service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=build_approved_plan_snapshot(scenario),
            recommendation_origin_refs=build_recommendation_origin_refs(scenario),
        )
        return scenario, review_context

    def _get_delta(self, review_context, entity_external_id):
        return next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == entity_external_id
        )

    def test_health_route_exists(self):
        status, payload = self._request("GET", "/health")

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_s01_portfolio_route_returns_view_model(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_portfolio_clean.json",
            "transport-s01",
            "context::transport-s01",
        )

        status, payload = self._request(
            "GET",
            "/api/screens/s01/portfolio",
            query={"planningRunId": execution_result.execution_record.planning_run_id},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["screen"]["id"], "S01")
        self.assertEqual(payload["portfolioSummary"]["scheduleState"], "scheduled")

    def test_d01_task_drilldown_route_returns_embedded_drawer_payload(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_schedule_happy_path.json",
            "transport-d01",
            "context::transport-d01",
        )

        status, payload = self._request(
            "GET",
            "/api/drawers/d01/task-drilldown",
            query={
                "planningRunId": execution_result.execution_record.planning_run_id,
                "resourceExternalId": "user-ada",
                "date": "2026-04-08",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["drawer"]["id"], "D01")
        self.assertEqual(payload["drawer"]["ownerScreenId"], "S01")
        self.assertEqual(payload["viewState"]["screenState"], "indicator_present")
        self.assertEqual(payload["segmentSummary"]["taskCount"], 1)
        self.assertEqual(payload["tasks"][0]["taskExternalId"], "task-implement")

    def test_d01_task_drilldown_route_handles_non_matching_context(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_schedule_happy_path.json",
            "transport-d01-empty",
            "context::transport-d01-empty",
        )

        status, payload = self._request(
            "GET",
            "/api/drawers/d01/task-drilldown",
            query={
                "planningRunId": execution_result.execution_record.planning_run_id,
                "resourceExternalId": "user-ada",
                "date": "2026-04-10",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["drawer"]["id"], "D01")
        self.assertEqual(payload["viewState"]["screenState"], "empty")
        self.assertEqual(payload["tasks"], [])

    def test_s02_setup_route_returns_screen_contract(self):
        bundle = self._import_bundle("source_plan_capacity_fte.json")

        status, payload = self._request(
            "GET",
            "/api/screens/s02/setup",
            query={
                "planningContextKey": "context::transport-s02",
                "sourceSnapshotId": bundle.snapshot.snapshot_id,
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["screen"]["id"], "S02")
        self.assertEqual(payload["sourceReadiness"]["state"], "ready")

    def test_s02_import_sync_start_route_delegates_to_orchestrator(self):
        class TrackingImportSyncExecutionGateway(ImportSyncExecutionGateway):
            def __init__(self):
                self.requests = []

            def submit_import_sync(self, request):
                self.requests.append(request)
                return ImportSyncExecutionReceipt(
                    handoff_id="import-sync-handoff-01",
                    accepted_at=request.requested_at,
                )

        class TrackingWorkflowOrchestratorService(WorkflowOrchestratorService):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.import_sync_triggers = []

            def start_import_sync(self, trigger):
                self.import_sync_triggers.append(trigger)
                return super().start_import_sync(trigger)

        import_sync_gateway = TrackingImportSyncExecutionGateway()
        tracking_orchestrator = TrackingWorkflowOrchestratorService(
            integration_service=self.integration_service,
            planning_engine_gateway=PlanningEngineWorkflowGateway(
                integration_service=self.integration_service,
                planning_engine_service=self.planning_engine_service,
            ),
            import_sync_execution_gateway=import_sync_gateway,
            activation_execution_gateway=IntegrationBackedActivationExecutionGateway(
                integration_service=self.integration_service
            ),
        )
        app = ApiGatewayBffApplication(
            ApiGatewayBffDependencies(
                integration_service=self.integration_service,
                planning_engine_service=self.planning_engine_service,
                review_approval_service=self.review_approval_service,
                decision_support_service=self.decision_support_service,
                workflow_orchestrator_service=tracking_orchestrator,
            )
        )

        status_holder = {}

        def start_response(status, headers):
            status_holder["status"] = status
            status_holder["headers"] = headers

        raw_payload = load_fixture("source_plan_valid.json")
        environ = build_test_environ(
            method="POST",
            path="/api/screens/s02/import-sync",
            body={
                "rawPayload": raw_payload,
                "requestedBy": "planner@example.com",
                "requestedAt": "2026-04-07T09:05:00Z",
                "idempotencyKey": "import-sync::transport",
            },
        )
        response = b"".join(app(environ, start_response)).decode("utf-8")
        payload = json.loads(response)

        self.assertEqual(int(status_holder["status"].split()[0]), 202)
        self.assertEqual(len(tracking_orchestrator.import_sync_triggers), 1)
        self.assertEqual(len(import_sync_gateway.requests), 1)
        self.assertEqual(payload["workflow_instance"]["workflow_type"], "import_sync")
        self.assertEqual(payload["workflow_instance"]["current_status"], "dispatched")
        self.assertEqual(
            payload["handoff_request"]["workflow_instance_id"],
            payload["workflow_instance"]["workflow_instance_id"],
        )
        self.assertIsNone(payload["source_snapshot_id"])
        self.assertIsNone(payload["source_readiness"])
        self.assertIsNone(self.integration_service.get_normalized_source_bundle())

    def test_s02_import_sync_start_route_rejects_invalid_raw_payload(self):
        status, payload = self._request(
            "POST",
            "/api/screens/s02/import-sync",
            body={
                "rawPayload": "not-an-object",
                "requestedBy": "planner@example.com",
                "requestedAt": "2026-04-07T09:05:00Z",
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "invalid_object_field")

    def test_s02_start_planning_run_route_delegates_to_orchestrator(self):
        bundle = self._import_bundle("source_plan_valid.json")

        status, payload = self._request(
            "POST",
            "/api/screens/s02/planning-runs",
            body={
                "planningContextKey": "context::transport-planning-run",
                "sourceSnapshotId": bundle.snapshot.snapshot_id,
                "requestedBy": "planner@example.com",
                "requestedAt": "2026-04-07T09:10:00Z",
                "idempotencyKey": "planning-run::transport",
            },
        )

        self.assertEqual(status, 202)
        self.assertEqual(payload["workflow_instance"]["current_status"], "dispatched")
        status_view = self.workflow_orchestrator_service.get_planning_run_status(
            planning_context_key="context::transport-planning-run",
            source_snapshot_id=bundle.snapshot.snapshot_id,
        )
        self.assertIsNotNone(status_view)
        self.assertEqual(status_view.status, "dispatched")

    def test_s02_start_planning_run_rejects_non_runnable_snapshot(self):
        bundle = self._import_bundle("source_plan_invalid_missing_required_fields.json")

        status, payload = self._request(
            "POST",
            "/api/screens/s02/planning-runs",
            body={
                "planningContextKey": "context::transport-planning-blocked",
                "sourceSnapshotId": bundle.snapshot.snapshot_id,
                "requestedBy": "planner@example.com",
                "requestedAt": "2026-04-07T09:11:00Z",
            },
        )

        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "source_not_runnable")

    def test_s02_planning_run_status_route_returns_status_payload(self):
        bundle = self._import_bundle("source_plan_valid.json")
        start_status, start_payload = self._request(
            "POST",
            "/api/screens/s02/planning-runs",
            body={
                "planningContextKey": "context::transport-status",
                "sourceSnapshotId": bundle.snapshot.snapshot_id,
                "requestedBy": "planner@example.com",
                "requestedAt": "2026-04-07T09:12:00Z",
            },
        )
        self.assertEqual(start_status, 202)

        status, payload = self._request(
            "GET",
            "/api/screens/s02/planning-runs/status",
            query={
                "workflowInstanceId": start_payload["workflow_instance"]["workflow_instance_id"]
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "dispatched")

    def test_s03_resource_detail_route_returns_view_model(self):
        bundle, execution_result = self._execute_planning_run(
            "source_plan_resource_detail_balanced.json",
            "transport-s03",
            "context::transport-s03",
        )
        self.decision_support_service.refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id="user-taylor",
        )

        status, payload = self._request(
            "GET",
            "/api/screens/s03/resource-detail",
            query={
                "planningRunId": execution_result.execution_record.planning_run_id,
                "planningContextKey": execution_result.execution_record.planning_context_key,
                "sourceSnapshotId": bundle.snapshot.snapshot_id,
                "resourceExternalId": "user-taylor",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["screen"]["id"], "S03")
        self.assertEqual(payload["resourceSummary"]["resourceExternalId"], "user-taylor")

    def test_s03_recommendation_refresh_and_get_routes(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_resource_detail_balanced.json",
            "transport-s03-recs",
            "context::transport-s03-recs",
        )

        refresh_status, refresh_payload = self._request(
            "POST",
            "/api/screens/s03/recommendation-context/refresh",
            body={
                "planningRunId": execution_result.execution_record.planning_run_id,
                "resourceExternalId": "user-taylor",
            },
        )
        get_status, get_payload = self._request(
            "GET",
            "/api/screens/s03/recommendation-context",
            query={
                "resourceExternalId": "user-taylor",
                "planningContextKey": execution_result.execution_record.planning_context_key,
                "sourceSnapshotId": execution_result.execution_record.source_snapshot_id,
            },
        )

        self.assertEqual(refresh_status, 200)
        self.assertEqual(get_status, 200)
        self.assertEqual(refresh_payload["context_id"], get_payload["context_id"])

    def test_s04_delta_review_route_returns_view_model(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_resource_detail_balanced.json",
            "transport-s04",
            "context::transport-s04",
        )
        _, review_context = self._create_review_context(
            execution_result,
            "review_approval_delta_simple.json",
        )

        status, payload = self._request(
            "GET",
            "/api/screens/s04/delta-review",
            query={
                "reviewContextId": review_context.review_context_id,
                "planningContextKey": "context::transport-s04",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["screen"]["id"], "S04")
        self.assertEqual(
            payload["reviewContextStatus"]["reviewContextId"],
            review_context.review_context_id,
        )

    def test_s04_review_context_route_generates_review_context_via_review_approval(self):
        class TrackingReviewApprovalService(ReviewApprovalService):
            def __init__(self):
                super().__init__()
                self.generated_review_context_calls = []

            def generate_reviewable_delta_set(
                self,
                execution_result,
                approved_plan_snapshot,
                recommendation_origin_refs=None,
            ):
                self.generated_review_context_calls.append(
                    (
                        execution_result.execution_record.planning_run_id,
                        approved_plan_snapshot.approved_plan_id,
                    )
                )
                return super().generate_reviewable_delta_set(
                    execution_result=execution_result,
                    approved_plan_snapshot=approved_plan_snapshot,
                    recommendation_origin_refs=recommendation_origin_refs,
                )

        _, execution_result = self._execute_planning_run(
            "source_plan_resource_detail_balanced.json",
            "transport-s04-review-context",
            "context::transport-s04-review-context",
        )
        scenario = load_fixture("review_approval_delta_simple.json")
        tracking_review_approval_service = TrackingReviewApprovalService()
        approved_plan_snapshot = build_approved_plan_snapshot(scenario)
        tracking_review_approval_service._repository.save_approved_plan_snapshot(
            approved_plan_snapshot,
            set_current=True,
        )
        app = ApiGatewayBffApplication(
            ApiGatewayBffDependencies(
                integration_service=self.integration_service,
                planning_engine_service=self.planning_engine_service,
                review_approval_service=tracking_review_approval_service,
                decision_support_service=self.decision_support_service,
                workflow_orchestrator_service=self.workflow_orchestrator_service,
            )
        )

        status_holder = {}

        def start_response(status, headers):
            status_holder["status"] = status
            status_holder["headers"] = headers

        environ = build_test_environ(
            method="POST",
            path="/api/screens/s04/review-context",
            body={
                "planningRunId": execution_result.execution_record.planning_run_id,
            },
        )
        response = b"".join(app(environ, start_response)).decode("utf-8")
        payload = json.loads(response)

        self.assertEqual(int(status_holder["status"].split()[0]), 200)
        self.assertEqual(
            tracking_review_approval_service.generated_review_context_calls,
            [
                (
                    execution_result.execution_record.planning_run_id,
                    approved_plan_snapshot.approved_plan_id,
                )
            ],
        )
        self.assertEqual(
            payload["planning_run_id"],
            execution_result.execution_record.planning_run_id,
        )
        self.assertEqual(
            payload["approved_plan_id"],
            approved_plan_snapshot.approved_plan_id,
        )
        self.assertEqual(
            payload["comparison_context"],
            "draft_vs_current_approved_plan",
        )
        self.assertGreater(len(payload["delta_items"]), 0)

    def test_s04_review_context_route_rejects_missing_planning_run(self):
        scenario = load_fixture("review_approval_delta_simple.json")
        approved_plan_snapshot = build_approved_plan_snapshot(scenario)
        self.review_approval_service._repository.save_approved_plan_snapshot(
            approved_plan_snapshot,
            set_current=True,
        )

        status, payload = self._request(
            "POST",
            "/api/screens/s04/review-context",
            body={"planningRunId": "missing-planning-run"},
        )

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "planning_run_not_found")

    def test_s04_acceptance_selection_route_delegates_to_review_approval(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_resource_detail_balanced.json",
            "transport-s04-accept",
            "context::transport-s04-accept",
        )
        _, review_context = self._create_review_context(
            execution_result,
            "review_approval_delta_simple.json",
        )
        rollout_delta = self._get_delta(review_context, "task-rollout")

        status, payload = self._request(
            "POST",
            "/api/screens/s04/acceptance-selection",
            body={
                "reviewContextId": review_context.review_context_id,
                "deltaId": rollout_delta.delta_id,
                "selected": True,
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "applied")
        refreshed_context = self.review_approval_service.get_review_context(
            review_context.review_context_id
        )
        self.assertTrue(
            next(
                delta.selected_for_acceptance
                for delta in refreshed_context.delta_items
                if delta.delta_id == rollout_delta.delta_id
            )
        )

    def test_m01_connected_change_set_route_returns_modal_payload(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_schedule_happy_path.json",
            "transport-m01",
            "context::transport-m01",
        )
        _, review_context = self._create_review_context(
            execution_result,
            "review_approval_delta_dependency_linked.json",
        )
        blocked_delta = self._get_delta(review_context, "task-implement")

        status, payload = self._request(
            "GET",
            "/api/modals/m01/connected-change-set",
            query={
                "reviewContextId": review_context.review_context_id,
                "requestedDeltaId": blocked_delta.delta_id,
                "planningContextKey": "context::transport-m01",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["screen"]["id"], "M01")
        self.assertEqual(payload["viewState"]["screenState"], "ready")
        self.assertEqual(len(payload["connectedSet"]["memberDeltaIds"]), 2)

    def test_m01_connected_change_set_acceptance_route_delegates_to_review_approval(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_schedule_happy_path.json",
            "transport-m01-accept",
            "context::transport-m01-accept",
        )
        _, review_context = self._create_review_context(
            execution_result,
            "review_approval_delta_dependency_linked.json",
        )
        blocked_delta = self._get_delta(review_context, "task-implement")

        status, payload = self._request(
            "POST",
            "/api/modals/m01/connected-change-set/acceptance-selection",
            body={
                "reviewContextId": review_context.review_context_id,
                "requestedDeltaId": blocked_delta.delta_id,
                "selected": True,
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["screen"]["id"], "M01")
        self.assertEqual(payload["selectionScope"], "connected_change_set")
        self.assertEqual(payload["action"], "select")
        self.assertEqual(payload["status"], "applied")
        self.assertIsNotNone(payload["connectedSetId"])
        self.assertEqual(payload["selectionSummary"]["selectedDeltaCount"], 2)
        refreshed_context = self.review_approval_service.get_review_context(
            review_context.review_context_id
        )
        self.assertEqual(
            2,
            len(
                [
                    delta
                    for delta in refreshed_context.delta_items
                    if delta.selected_for_acceptance
                ]
            ),
        )

    def test_m01_connected_change_set_acceptance_route_rejects_invalid_selected_field(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_schedule_happy_path.json",
            "transport-m01-invalid",
            "context::transport-m01-invalid",
        )
        _, review_context = self._create_review_context(
            execution_result,
            "review_approval_delta_dependency_linked.json",
        )
        blocked_delta = self._get_delta(review_context, "task-implement")

        status, payload = self._request(
            "POST",
            "/api/modals/m01/connected-change-set/acceptance-selection",
            body={
                "reviewContextId": review_context.review_context_id,
                "requestedDeltaId": blocked_delta.delta_id,
                "selected": "true",
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "invalid_boolean_field")

    def test_s04_activation_route_and_status_route_return_transport_payloads(self):
        _, execution_result = self._execute_planning_run(
            "source_plan_resource_detail_balanced.json",
            "transport-activation",
            "context::transport-activation",
        )
        _, review_context = self._create_review_context(
            execution_result,
            "review_approval_delta_simple.json",
        )
        rollout_delta = self._get_delta(review_context, "task-rollout")
        self.review_approval_service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=rollout_delta.delta_id,
            selected=True,
        )

        activate_status, activate_payload = self._request(
            "POST",
            "/api/screens/s04/activation",
            body={
                "reviewContextId": review_context.review_context_id,
                "requestedBy": "approver@example.com",
                "requestedAt": "2026-04-07T09:20:00Z",
            },
        )
        status_status, status_payload = self._request(
            "GET",
            "/api/screens/s04/activation-status",
            query={"reviewContextId": review_context.review_context_id},
        )

        self.assertEqual(activate_status, 200)
        self.assertEqual(activate_payload["status"], "activated")
        self.assertEqual(status_status, 200)
        self.assertEqual(status_payload["activation"]["status"], "activated")
        self.assertEqual(
            status_payload["activation"]["downstreamWorkflow"]["workflowState"],
            "dispatched",
        )

    def test_s05_warnings_workspace_route_returns_view_model(self):
        bundle = self._import_bundle("source_plan_capacity_fte.json")
        self.decision_support_service.publish_screen_warning_trust_state(
            screen_id="S05",
            planning_context_key="context::transport-s05",
            source_snapshot_id=bundle.snapshot.snapshot_id,
            signals=[
                ScreenWarningTrustSignal(
                    signal_id="warning-transport-01",
                    screen_id="S05",
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    planning_context_key="context::transport-s05",
                    signal_type="warning",
                    severity="medium",
                    code="review_attention_needed",
                    message="Review attention is needed.",
                    advisory=True,
                    blocking=False,
                    interpretation_category="advisory_warning",
                    source_issue_service="Review & Approval Service",
                    source_fact_id="fact-01",
                    source_fact_type="review_issue",
                    source_fact_severity="medium",
                    entity_type="task",
                    entity_id="task-01",
                    entity_external_id="task-rollout",
                )
            ],
        )

        status, payload = self._request(
            "GET",
            "/api/screens/s05/warnings-workspace",
            query={
                "planningContextKey": "context::transport-s05",
                "sourceSnapshotId": bundle.snapshot.snapshot_id,
                "originScreenId": "S04",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["screen"]["id"], "S05")
        self.assertEqual(payload["warningItems"][0]["affectedWorkflow"]["id"], "S04")

    def test_unknown_route_returns_not_found(self):
        status, payload = self._request("GET", "/api/unknown")

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "route_not_found")


if __name__ == "__main__":
    unittest.main()
