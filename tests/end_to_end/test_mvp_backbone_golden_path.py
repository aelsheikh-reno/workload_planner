import json
import unittest
from pathlib import Path

from services.api_gateway_bff.s01_portfolio_contract import (
    build_s01_portfolio_contract,
)
from services.api_gateway_bff.s02_setup_contract import build_s02_setup_contract
from services.api_gateway_bff.s03_resource_detail_contract import (
    build_s03_resource_detail_contract,
)
from services.api_gateway_bff.s04_delta_review_contract import (
    build_m01_connected_change_set_contract,
    build_s04_delta_review_contract,
    submit_m01_connected_set_acceptance_selection,
    submit_s04_activation_command,
    submit_s04_delta_acceptance_selection,
)
from services.decision_support_service import (
    DecisionSupportService,
    ScreenWarningTrustSignal,
)
from services.integration_service import (
    BoundedWriteBackExecutionReceipt,
    BoundedWriteBackItemResult,
    ExternalWriteBackGateway,
    InMemoryIntegrationRepository,
    IntegrationService,
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
    ACTIVATION_RECOMPUTATION_STEP,
    ACTIVATION_SIDE_EFFECTS_STEP,
    IntegrationBackedActivationExecutionGateway,
    PlanningRunTrigger,
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


class FixtureExternalWriteBackGateway(ExternalWriteBackGateway):
    def __init__(self, *fixture_names):
        self._fixtures = [load_fixture(name) for name in fixture_names]
        self.requests = []

    def execute_write_back(self, request):
        self.requests.append(request)
        fixture = self._fixtures.pop(0)
        item_results = []
        for target in request.targets:
            outcome = fixture["target_outcomes"][target.entity_external_id]
            item_results.append(
                BoundedWriteBackItemResult(
                    target_id=target.target_id,
                    delta_id=target.delta_id,
                    entity_type=target.entity_type,
                    entity_external_id=target.entity_external_id,
                    status=outcome["status"],
                    applied_fields=list(outcome.get("applied_fields", [])),
                    error_code=outcome.get("error_code"),
                    error_message=outcome.get("error_message"),
                )
            )
        return BoundedWriteBackExecutionReceipt(
            completed_at=fixture["completed_at"],
            item_results=item_results,
        )


class MvpBackboneGoldenPathTests(unittest.TestCase):
    def _build_services(
        self,
        source_fixture_name,
        planning_run_key,
        external_write_back_gateway=None,
    ):
        integration_repository = InMemoryIntegrationRepository()
        integration_service = IntegrationService(
            repository=integration_repository,
            external_write_back_gateway=external_write_back_gateway,
        )
        planning_engine_service = PlanningEngineService()
        decision_support_service = DecisionSupportService()
        review_approval_service = ReviewApprovalService()
        planning_engine_gateway = PlanningEngineWorkflowGateway(
            integration_service=integration_service,
            planning_engine_service=planning_engine_service,
        )
        workflow_orchestrator_service = WorkflowOrchestratorService(
            integration_service=integration_service,
            planning_engine_gateway=planning_engine_gateway,
            activation_execution_gateway=IntegrationBackedActivationExecutionGateway(
                integration_service=integration_service
            ),
        )
        bundle = integration_service.import_source_plan(load_fixture(source_fixture_name))
        return {
            "bundle": bundle,
            "integration_service": integration_service,
            "planning_engine_service": planning_engine_service,
            "decision_support_service": decision_support_service,
            "review_approval_service": review_approval_service,
            "workflow_orchestrator_service": workflow_orchestrator_service,
            "planning_context_key": "context::%s" % planning_run_key,
        }

    def _run_planning_workflow(
        self,
        workflow_orchestrator_service,
        planning_engine_service,
        bundle,
        planning_context_key,
        planning_run_key,
    ):
        trigger = PlanningRunTrigger(
            planning_context_key=planning_context_key,
            source_snapshot_id=bundle.snapshot.snapshot_id,
            requested_by="planner@example.com",
            requested_at="2026-04-06T08:00:00Z",
            idempotency_key="planning-run::%s" % planning_run_key,
        )
        start_result = workflow_orchestrator_service.start_planning_run(trigger)
        workflow_orchestrator_service.mark_planning_run_running(
            workflow_instance_id=start_result.workflow_instance.workflow_instance_id,
            occurred_at="2026-04-06T08:01:00Z",
        )
        workflow_orchestrator_service.mark_planning_run_succeeded(
            workflow_instance_id=start_result.workflow_instance.workflow_instance_id,
            occurred_at="2026-04-06T08:02:00Z",
        )
        execution_result = planning_engine_service.get_execution_result(
            planning_run_id=start_result.workflow_instance.planning_engine_run_id
        )
        self.assertIsNotNone(execution_result)
        return start_result, execution_result

    def _create_review_context(
        self,
        review_approval_service,
        execution_result,
        review_fixture_name,
    ):
        scenario = load_fixture(review_fixture_name)
        review_context = review_approval_service.generate_reviewable_delta_set(
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

    def test_golden_path_happy_flow_from_setup_to_activation_and_write_back(self):
        write_back_gateway = FixtureExternalWriteBackGateway(
            "integration_write_back_success.json"
        )
        services = self._build_services(
            source_fixture_name="source_plan_resource_detail_balanced.json",
            planning_run_key="golden-happy",
            external_write_back_gateway=write_back_gateway,
        )

        setup_contract = build_s02_setup_contract(
            integration_service=services["integration_service"],
            planning_engine_service=services["planning_engine_service"],
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
            planning_context_key=services["planning_context_key"],
            snapshot_id=services["bundle"].snapshot.snapshot_id,
        )
        self.assertEqual(setup_contract["overallReadiness"]["state"], "ready")
        self.assertTrue(setup_contract["overallReadiness"]["canContinueToPlanning"])

        planning_workflow, execution_result = self._run_planning_workflow(
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
            planning_engine_service=services["planning_engine_service"],
            bundle=services["bundle"],
            planning_context_key=services["planning_context_key"],
            planning_run_key="golden-happy",
        )

        setup_after_run = build_s02_setup_contract(
            integration_service=services["integration_service"],
            planning_engine_service=services["planning_engine_service"],
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
            planning_context_key=services["planning_context_key"],
            snapshot_id=services["bundle"].snapshot.snapshot_id,
        )
        self.assertEqual(setup_after_run["planningRunStatus"]["status"], "succeeded")
        self.assertEqual(
            setup_after_run["planningRunStatus"]["workflowInstanceId"],
            planning_workflow.workflow_instance.workflow_instance_id,
        )

        s01_contract = build_s01_portfolio_contract(
            planning_engine_service=services["planning_engine_service"],
            planning_run_id=execution_result.execution_record.planning_run_id,
        )
        self.assertIn(
            s01_contract["viewState"]["screenState"],
            {"ready", "indicator_present"},
        )
        self.assertTrue(s01_contract["dailySwimlanes"])

        services["decision_support_service"].refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id="user-taylor",
        )
        s03_contract = build_s03_resource_detail_contract(
            planning_engine_service=services["planning_engine_service"],
            decision_support_service=services["decision_support_service"],
            planning_run_id=execution_result.execution_record.planning_run_id,
            planning_context_key=services["planning_context_key"],
            resource_external_id="user-taylor",
        )
        self.assertEqual(
            s03_contract["resourceSummary"]["resourceExternalId"],
            "user-taylor",
        )
        self.assertTrue(s03_contract["workloadTimeline"])
        self.assertTrue(s03_contract["assignedWorkQueue"])
        self.assertEqual(
            s03_contract["recommendationContext"]["state"],
            "no_actionable_recommendations",
        )

        _, review_context = self._create_review_context(
            review_approval_service=services["review_approval_service"],
            execution_result=execution_result,
            review_fixture_name="review_approval_delta_simple.json",
        )
        rollout_delta = self._get_delta(review_context, "task-rollout")
        submit_s04_delta_acceptance_selection(
            review_approval_service=services["review_approval_service"],
            review_context_id=review_context.review_context_id,
            delta_id=rollout_delta.delta_id,
            selected=True,
        )
        activation_command = submit_s04_activation_command(
            review_approval_service=services["review_approval_service"],
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T10:00:00Z",
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
        )
        workflow_id = activation_command["downstreamWorkflow"]["workflowInstanceId"]

        services["workflow_orchestrator_service"].mark_activation_step_running(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            occurred_at="2026-04-06T10:01:00Z",
        )
        services["workflow_orchestrator_service"].mark_activation_step_succeeded(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            occurred_at="2026-04-06T10:02:00Z",
        )
        services["workflow_orchestrator_service"].mark_activation_step_running(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_SIDE_EFFECTS_STEP,
            occurred_at="2026-04-06T10:03:00Z",
        )
        services["workflow_orchestrator_service"].mark_activation_step_succeeded(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_SIDE_EFFECTS_STEP,
            occurred_at="2026-04-06T10:04:00Z",
        )

        s04_contract = build_s04_delta_review_contract(
            review_approval_service=services["review_approval_service"],
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
            review_context_id=review_context.review_context_id,
            planning_context_key=services["planning_context_key"],
        )
        write_back_result = services["integration_service"].get_write_back_result(
            activation_id=activation_command["activationId"]
        )

        self.assertEqual(activation_command["status"], "activated")
        self.assertEqual(write_back_result.status, "succeeded")
        self.assertEqual(len(write_back_gateway.requests), 1)
        self.assertEqual(
            write_back_gateway.requests[0].targets[0].entity_external_id,
            "task-rollout",
        )
        self.assertEqual(s04_contract["activation"]["status"], "activated")
        self.assertEqual(
            s04_contract["activation"]["downstreamWorkflow"]["workflowState"],
            "succeeded",
        )
        self.assertEqual(
            services["review_approval_service"]
            .get_approved_operating_plan_snapshot(current=True)
            .approved_plan_id,
            activation_command["approvedPlanIdAfter"],
        )

    def test_advisory_warnings_do_not_block_planning_entry(self):
        services = self._build_services(
            source_fixture_name="source_plan_resource_detail_balanced.json",
            planning_run_key="golden-advisory",
        )
        services["decision_support_service"].publish_screen_warning_trust_state(
            screen_id="S02",
            planning_context_key=services["planning_context_key"],
            source_snapshot_id=services["bundle"].snapshot.snapshot_id,
            signals=[
                ScreenWarningTrustSignal(
                    signal_id="s02-advisory-golden-path",
                    screen_id="S02",
                    source_snapshot_id=services["bundle"].snapshot.snapshot_id,
                    planning_context_key=services["planning_context_key"],
                    signal_type="warning",
                    severity="medium",
                    code="low_planning_confidence",
                    message="Advisory warning should not block planning entry.",
                    advisory=True,
                    blocking=False,
                    interpretation_category="advisory_warning",
                    source_issue_service="Decision Support Service",
                    source_fact_id="interpreted-fact-s02-01",
                    source_fact_type="interpreted_signal",
                    source_fact_severity="medium",
                    entity_type="planning_context",
                    entity_id=services["planning_context_key"],
                    entity_external_id=None,
                )
            ],
        )

        contract = build_s02_setup_contract(
            integration_service=services["integration_service"],
            planning_engine_service=services["planning_engine_service"],
            decision_support_service=services["decision_support_service"],
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
            planning_context_key=services["planning_context_key"],
            snapshot_id=services["bundle"].snapshot.snapshot_id,
        )

        self.assertEqual(contract["overallReadiness"]["state"], "ready_with_advisories")
        self.assertTrue(contract["overallReadiness"]["runnable"])
        self.assertTrue(contract["overallReadiness"]["canContinueToPlanning"])
        self.assertEqual(contract["overallReadiness"]["noRunnablePlanBlockerCount"], 0)
        self.assertEqual(contract["overallReadiness"]["advisorySignalCount"], 1)

    def test_dependency_safe_blocking_requires_connected_set_before_review_can_progress(self):
        services = self._build_services(
            source_fixture_name="source_plan_schedule_happy_path.json",
            planning_run_key="golden-connected-set",
        )
        _, execution_result = self._run_planning_workflow(
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
            planning_engine_service=services["planning_engine_service"],
            bundle=services["bundle"],
            planning_context_key=services["planning_context_key"],
            planning_run_key="golden-connected-set",
        )
        _, review_context = self._create_review_context(
            review_approval_service=services["review_approval_service"],
            execution_result=execution_result,
            review_fixture_name="review_approval_delta_dependency_linked.json",
        )
        blocked_delta = self._get_delta(review_context, "task-implement")

        selection_result = submit_s04_delta_acceptance_selection(
            review_approval_service=services["review_approval_service"],
            review_context_id=review_context.review_context_id,
            delta_id=blocked_delta.delta_id,
            selected=True,
        )
        blocked_contract = build_s04_delta_review_contract(
            review_approval_service=services["review_approval_service"],
            review_context_id=review_context.review_context_id,
            planning_context_key=services["planning_context_key"],
            focused_delta_id=blocked_delta.delta_id,
        )
        modal_contract = build_m01_connected_change_set_contract(
            review_approval_service=services["review_approval_service"],
            review_context_id=review_context.review_context_id,
            requested_delta_id=blocked_delta.delta_id,
            planning_context_key=services["planning_context_key"],
        )
        modal_selection = submit_m01_connected_set_acceptance_selection(
            review_approval_service=services["review_approval_service"],
            review_context_id=review_context.review_context_id,
            requested_delta_id=blocked_delta.delta_id,
            selected=True,
        )
        unblocked_contract = build_s04_delta_review_contract(
            review_approval_service=services["review_approval_service"],
            review_context_id=review_context.review_context_id,
            planning_context_key=services["planning_context_key"],
            focused_delta_id=blocked_delta.delta_id,
        )

        self.assertEqual(selection_result["status"], "blocked")
        self.assertEqual(selection_result["blockedReasonCode"], "connected_set_required")
        self.assertEqual(blocked_contract["viewState"]["screenState"], "blocked_isolated_acceptance")
        self.assertTrue(blocked_contract["blockedAcceptance"]["present"])
        self.assertEqual(
            modal_contract["connectedSet"]["memberDeltaIds"],
            sorted(modal_contract["connectedSet"]["memberDeltaIds"]),
        )
        self.assertEqual(len(modal_contract["connectedSet"]["memberDeltaIds"]), 2)
        self.assertEqual(modal_selection["status"], "applied")
        self.assertIsNone(unblocked_contract["blockedAcceptance"])
        self.assertEqual(unblocked_contract["acceptanceState"]["selectedDeltaCount"], 2)

    def test_write_back_failure_does_not_roll_back_approved_truth(self):
        write_back_gateway = FixtureExternalWriteBackGateway(
            "integration_write_back_failure.json"
        )
        services = self._build_services(
            source_fixture_name="source_plan_resource_detail_balanced.json",
            planning_run_key="golden-write-back-failure",
            external_write_back_gateway=write_back_gateway,
        )
        _, execution_result = self._run_planning_workflow(
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
            planning_engine_service=services["planning_engine_service"],
            bundle=services["bundle"],
            planning_context_key=services["planning_context_key"],
            planning_run_key="golden-write-back-failure",
        )
        _, review_context = self._create_review_context(
            review_approval_service=services["review_approval_service"],
            execution_result=execution_result,
            review_fixture_name="review_approval_delta_simple.json",
        )
        rollout_delta = self._get_delta(review_context, "task-rollout")
        submit_s04_delta_acceptance_selection(
            review_approval_service=services["review_approval_service"],
            review_context_id=review_context.review_context_id,
            delta_id=rollout_delta.delta_id,
            selected=True,
        )
        activation_command = submit_s04_activation_command(
            review_approval_service=services["review_approval_service"],
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T10:10:00Z",
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
        )
        workflow_id = activation_command["downstreamWorkflow"]["workflowInstanceId"]

        services["workflow_orchestrator_service"].mark_activation_step_running(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            occurred_at="2026-04-06T10:11:00Z",
        )
        retry_pending = services["workflow_orchestrator_service"].mark_activation_step_succeeded(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            occurred_at="2026-04-06T10:12:00Z",
        )
        s04_contract = build_s04_delta_review_contract(
            review_approval_service=services["review_approval_service"],
            workflow_orchestrator_service=services["workflow_orchestrator_service"],
            review_context_id=review_context.review_context_id,
            planning_context_key=services["planning_context_key"],
        )
        write_back_result = services["integration_service"].get_write_back_result(
            activation_id=activation_command["activationId"]
        )

        self.assertEqual(retry_pending.current_status, "retry_pending")
        self.assertEqual(write_back_result.status, "failed")
        self.assertEqual(len(write_back_gateway.requests), 1)
        self.assertEqual(s04_contract["activation"]["status"], "activated")
        self.assertEqual(
            s04_contract["activation"]["downstreamWorkflow"]["workflowState"],
            "retry_pending",
        )
        self.assertEqual(
            services["review_approval_service"]
            .get_approved_operating_plan_snapshot(current=True)
            .approved_plan_id,
            activation_command["approvedPlanIdAfter"],
        )


if __name__ == "__main__":
    unittest.main()
