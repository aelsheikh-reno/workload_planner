import json
import unittest
from pathlib import Path

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
from services.integration_service.service import IntegrationService
from services.planning_engine_service.service import PlanningEngineService
from services.review_approval_service import (
    ApprovedOperatingPlanSnapshot,
    ApprovedPlanProjectRecord,
    ApprovedPlanTaskRecord,
    RecommendationOriginReference,
    ReviewApprovalService,
)
from services.workflow_orchestrator_service import (
    ACTIVATION_RECOMPUTATION_STEP,
    ActivationExecutionGateway,
    ActivationExecutionGatewayError,
    ActivationExecutionStepReceipt,
    PlanningEngineGateway,
    WorkflowOrchestratorService,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def build_review_context(
    fixture_name,
    planning_run_key,
    service_factory=ReviewApprovalService,
):
    scenario = load_fixture(fixture_name)
    source_payload = load_fixture(scenario["source_plan_fixture"])
    integration_service = IntegrationService()
    planning_engine_service = PlanningEngineService()
    bundle = integration_service.import_source_plan(source_payload)
    execution_result = planning_engine_service.execute_planning_run(
        bundle=bundle,
        workflow_instance_id=f"workflow::{planning_run_key}",
        planning_context_key=f"context::{planning_run_key}",
        source_snapshot_id=bundle.snapshot.snapshot_id,
        source_artifact_id=bundle.artifact.artifact_id,
        requested_by="review-manager@example.com",
        requested_at="2026-04-05T18:00:00Z",
        attempt_number=1,
    )
    approved_plan_snapshot = ApprovedOperatingPlanSnapshot(
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
    recommendation_origin_refs = [
        RecommendationOriginReference(
            recommendation_id=item["recommendation_id"],
            origin_screen_id=item["origin_screen_id"],
            project_external_id=item.get("project_external_id"),
            task_external_id=item["task_external_id"],
            requires_review_handoff=item["requires_review_handoff"],
        )
        for item in scenario.get("recommendation_origin_refs", [])
    ]
    review_approval_service = service_factory()
    review_context = review_approval_service.generate_reviewable_delta_set(
        execution_result=execution_result,
        approved_plan_snapshot=approved_plan_snapshot,
        recommendation_origin_refs=recommendation_origin_refs,
    )
    return review_approval_service, review_context, execution_result


def publish_s04_warning_state(
    decision_support_service,
    planning_context_key,
    source_snapshot_id,
):
    signals = [
        ScreenWarningTrustSignal(
            signal_id="s04-signal-01",
            screen_id="S04",
            source_snapshot_id=source_snapshot_id,
            planning_context_key=planning_context_key,
            signal_type="warning",
            severity="medium",
            code="review_confidence_low",
            message="Review confidence is reduced by upstream plan movement.",
            advisory=True,
            blocking=False,
            interpretation_category="advisory_warning",
            source_issue_service="Planning Engine Service",
            source_fact_id="planning-fact-01",
            source_fact_type="planning_issue",
            source_fact_severity="medium",
            entity_type="task",
            entity_id="task_01",
            entity_external_id="task-rollout",
        ),
        ScreenWarningTrustSignal(
            signal_id="s04-signal-02",
            screen_id="S04",
            source_snapshot_id=source_snapshot_id,
            planning_context_key=planning_context_key,
            signal_type="trust",
            severity="medium",
            code="review_trust_limited",
            message="Interpretation is trust-limited for one or more related changes.",
            advisory=True,
            blocking=False,
            interpretation_category="trust_limited",
            source_issue_service="Decision Support Service",
            source_fact_id="derived-fact-02",
            source_fact_type="interpreted_signal",
            source_fact_severity="medium",
            entity_type="task",
            entity_id="task_02",
            entity_external_id="task-design",
        ),
        ScreenWarningTrustSignal(
            signal_id="s04-signal-03",
            screen_id="S04",
            source_snapshot_id=source_snapshot_id,
            planning_context_key=planning_context_key,
            signal_type="warning",
            severity="low",
            code="review_context_shifted",
            message="The draft changed recently; review selections should be rechecked.",
            advisory=True,
            blocking=False,
            interpretation_category="advisory_warning",
            source_issue_service="Review & Approval Service",
            source_fact_id="review-fact-03",
            source_fact_type="review_context_issue",
            source_fact_severity="low",
            entity_type="review_context",
            entity_id="review-context",
            entity_external_id=None,
        ),
    ]
    decision_support_service.publish_screen_warning_trust_state(
        screen_id="S04",
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
        signals=signals,
    )


class SpyReviewApprovalService(ReviewApprovalService):
    def __init__(self):
        super().__init__()
        self.delta_selection_calls = []
        self.connected_set_selection_calls = []
        self.activation_calls = []

    def record_delta_acceptance_selection(self, review_context_id, delta_id, selected):
        self.delta_selection_calls.append((review_context_id, delta_id, selected))
        return super().record_delta_acceptance_selection(
            review_context_id=review_context_id,
            delta_id=delta_id,
            selected=selected,
        )

    def record_connected_set_acceptance_selection(
        self,
        review_context_id,
        requested_delta_id,
        selected,
    ):
        self.connected_set_selection_calls.append(
            (review_context_id, requested_delta_id, selected)
        )
        return super().record_connected_set_acceptance_selection(
            review_context_id=review_context_id,
            requested_delta_id=requested_delta_id,
            selected=selected,
        )

    def activate_approved_changes(self, review_context_id, requested_by, requested_at):
        self.activation_calls.append((review_context_id, requested_by, requested_at))
        return super().activate_approved_changes(
            review_context_id=review_context_id,
            requested_by=requested_by,
            requested_at=requested_at,
        )


class UnusedPlanningEngineGateway(PlanningEngineGateway):
    def submit_planning_run(self, request):
        raise AssertionError("Planning Engine gateway should not be used in S04 activation tests.")


class FakeActivationExecutionGateway(ActivationExecutionGateway):
    def __init__(self):
        self.requests = []
        self._request_count = 0

    def submit_step(self, request):
        self.requests.append(request)
        self._request_count += 1
        return ActivationExecutionStepReceipt(
            step_name=request.step_name,
            handoff_id=f"{request.step_name}-hook-{self._request_count:02d}",
            accepted_at=f"2026-04-06T12:00:{self._request_count:02d}Z",
        )


class S04DeltaReviewContractTests(unittest.TestCase):
    def test_s04_normal_review_state(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_simple.json",
            "s04-normal",
        )

        contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
            origin_screen_id="S03",
            origin_scope_type="resource",
            origin_scope_external_id="user-taylor",
            origin_scope_label="Taylor Brooks",
        )

        self.assertEqual(contract["screen"], {"id": "S04", "label": "Delta Review"})
        self.assertEqual(contract["viewState"]["screenState"], "ready")
        self.assertEqual(contract["deltaSummary"]["totalDeltaCount"], 2)
        self.assertEqual(contract["acceptanceState"]["reviewStage"], "draft")
        self.assertEqual(len(contract["groupedDeltaReview"]), 1)
        self.assertEqual(
            contract["groupedDeltaReview"][0]["items"][0]["recommendationOriginContext"],
            [],
        )
        self.assertTrue(
            any(
                item["recommendationOriginContext"]
                for item in contract["groupedDeltaReview"][0]["items"]
            )
        )

    def test_s04_no_delta_state(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_no_delta.json",
            "s04-no-delta",
        )

        contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
        )

        self.assertEqual(contract["viewState"]["screenState"], "no_deltas")
        self.assertEqual(contract["deltaSummary"]["totalDeltaCount"], 0)
        self.assertEqual(contract["groupedDeltaReview"], [])

    def test_s04_blocked_isolated_acceptance_state(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_dependency_linked.json",
            "s04-blocked",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        command_result = submit_s04_delta_acceptance_selection(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
            focused_delta_id=requested_delta.delta_id,
        )

        self.assertEqual(command_result["status"], "blocked")
        self.assertEqual(command_result["blockedReasonCode"], "connected_set_required")
        self.assertIsNotNone(command_result["modalLaunch"])
        self.assertEqual(contract["viewState"]["screenState"], "blocked_isolated_acceptance")
        self.assertEqual(contract["acceptanceState"]["blockingIssueCount"], 2)
        self.assertEqual(contract["blockedAcceptance"]["requestedDeltaId"], requested_delta.delta_id)
        self.assertEqual(
            contract["blockedAcceptance"]["modalNavigation"]["screen"]["id"],
            "M01",
        )

    def test_s04_blocked_isolated_acceptance_state_on_first_render(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_dependency_linked.json",
            "s04-blocked-first-render",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
            focused_delta_id=requested_delta.delta_id,
        )

        self.assertEqual(contract["viewState"]["screenState"], "blocked_isolated_acceptance")
        self.assertEqual(contract["acceptanceState"]["blockingIssueCount"], 0)
        self.assertEqual(contract["blockedAcceptance"]["requestedDeltaId"], requested_delta.delta_id)
        self.assertEqual(contract["blockedAcceptance"]["reasonCode"], "connected_set_required")

    def test_s04_valid_task_level_acceptance_selection_and_deselection(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_simple.json",
            "s04-select-deselect",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-rollout"
        )

        select_result = submit_s04_delta_acceptance_selection(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        selected_contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
        )
        deselect_result = submit_s04_delta_acceptance_selection(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=False,
        )

        self.assertEqual(select_result["status"], "applied")
        self.assertEqual(select_result["selectionSummary"]["reviewStage"], "in_review")
        self.assertEqual(
            selected_contract["acceptanceState"]["selectedDeltaCount"],
            1,
        )
        self.assertEqual(deselect_result["status"], "applied")
        self.assertEqual(deselect_result["selectionSummary"]["reviewStage"], "draft")

    def test_s04_activation_state_and_command_after_acceptance(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_simple.json",
            "s04-activation",
        )
        workflow_orchestrator_service = WorkflowOrchestratorService(
            integration_service=IntegrationService(),
            planning_engine_gateway=UnusedPlanningEngineGateway(),
            activation_execution_gateway=FakeActivationExecutionGateway(),
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-rollout"
        )
        submit_s04_delta_acceptance_selection(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        pre_activation_contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            workflow_orchestrator_service=workflow_orchestrator_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
        )
        command_result = submit_s04_activation_command(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T10:00:00Z",
            workflow_orchestrator_service=workflow_orchestrator_service,
        )
        post_activation_contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            workflow_orchestrator_service=workflow_orchestrator_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
        )

        self.assertEqual(pre_activation_contract["activation"]["status"], "not_requested")
        self.assertTrue(pre_activation_contract["activation"]["actionAvailable"])
        self.assertEqual(command_result["status"], "activated")
        self.assertTrue(command_result["downstreamWorkflow"]["handoffRequired"])
        self.assertEqual(command_result["downstreamWorkflow"]["workflowState"], "dispatched")
        self.assertEqual(
            command_result["downstreamWorkflow"]["currentStep"],
            ACTIVATION_RECOMPUTATION_STEP,
        )
        self.assertEqual(post_activation_contract["activation"]["status"], "activated")
        self.assertFalse(post_activation_contract["activation"]["actionAvailable"])
        self.assertEqual(
            post_activation_contract["activation"]["downstreamWorkflow"]["workflowState"],
            "dispatched",
        )
        self.assertEqual(
            post_activation_contract["acceptanceState"]["reviewStage"],
            "approved_activated",
        )

    def test_s04_activation_view_reflects_async_workflow_progression(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_simple.json",
            "s04-activation-progress",
        )
        workflow_orchestrator_service = WorkflowOrchestratorService(
            integration_service=IntegrationService(),
            planning_engine_gateway=UnusedPlanningEngineGateway(),
            activation_execution_gateway=FakeActivationExecutionGateway(),
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-rollout"
        )
        submit_s04_delta_acceptance_selection(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        activation_command = submit_s04_activation_command(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T10:02:00Z",
            workflow_orchestrator_service=workflow_orchestrator_service,
        )
        workflow_id = activation_command["downstreamWorkflow"]["workflowInstanceId"]
        workflow_orchestrator_service.mark_activation_step_running(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            occurred_at="2026-04-06T10:03:00Z",
        )

        contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            workflow_orchestrator_service=workflow_orchestrator_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
        )

        self.assertEqual(contract["activation"]["status"], "activated")
        self.assertEqual(contract["activation"]["downstreamWorkflow"]["workflowState"], "running")
        self.assertEqual(
            contract["activation"]["downstreamWorkflow"]["currentStep"],
            ACTIVATION_RECOMPUTATION_STEP,
        )
        self.assertEqual(
            contract["activation"]["downstreamWorkflow"]["stepStates"][0]["status"],
            "running",
        )

    def test_s04_activation_is_blocked_without_valid_approved_set(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_simple.json",
            "s04-activation-blocked",
        )

        contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
        )
        command_result = submit_s04_activation_command(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T10:05:00Z",
        )

        self.assertFalse(contract["activation"]["actionAvailable"])
        self.assertEqual(command_result["status"], "blocked")
        self.assertEqual(
            [blocker["code"] for blocker in command_result["businessRuleBlockers"]],
            ["activation_requires_approved_set"],
        )
        self.assertFalse(command_result["downstreamWorkflow"]["handoffRequired"])

    def test_m01_invocation_and_connected_set_usage(self):
        review_approval_service, review_context, _ = build_review_context(
            "review_approval_delta_dependency_linked.json",
            "m01-usage",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        submit_s04_delta_acceptance_selection(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        modal_contract = build_m01_connected_change_set_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
        )
        modal_command = submit_m01_connected_set_acceptance_selection(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
            selected=True,
        )

        self.assertEqual(modal_contract["viewState"]["screenState"], "ready")
        self.assertEqual(modal_contract["connectedSet"]["selectedMemberCount"], 0)
        self.assertEqual(len(modal_contract["connectedSet"]["memberItems"]), 2)
        self.assertEqual(modal_command["status"], "applied")
        self.assertEqual(modal_command["selectionScope"], "connected_change_set")

    def test_s04_connected_set_members_are_not_blocked_after_group_selection(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_dependency_linked.json",
            "s04-connected-set-selected",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        submit_m01_connected_set_acceptance_selection(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
            selected=True,
        )
        contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
            focused_delta_id=requested_delta.delta_id,
        )

        self.assertEqual(contract["viewState"]["screenState"], "ready")
        self.assertIsNone(contract["blockedAcceptance"])
        self.assertEqual(contract["acceptanceState"]["connectedSetRequiredCount"], 0)
        self.assertEqual(contract["deltaSummary"]["blockedDeltaCount"], 0)
        self.assertEqual(contract["groupedDeltaReview"][0]["connectedSetRequiredCount"], 0)
        connected_set_items = [
            item
            for item in contract["groupedDeltaReview"][0]["items"]
            if item["connectedSetEntry"]["available"]
        ]
        self.assertEqual(len(connected_set_items), 2)
        for item in connected_set_items:
            self.assertTrue(item["acceptanceState"]["selected"])
            self.assertFalse(item["acceptanceState"]["blocked"])
            self.assertFalse(item["acceptanceState"]["requiresConnectedSet"])

    def test_s04_warning_heavy_state(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_simple.json",
            "s04-warning-heavy",
        )
        decision_support_service = DecisionSupportService()
        publish_s04_warning_state(
            decision_support_service=decision_support_service,
            planning_context_key=execution_result.execution_record.planning_context_key,
            source_snapshot_id=review_context.source_snapshot_id,
        )

        contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            decision_support_service=decision_support_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
        )

        self.assertEqual(contract["viewState"]["screenState"], "warning_heavy")
        self.assertTrue(contract["warningTrustContext"]["warningHeavy"])
        self.assertEqual(contract["warningTrustContext"]["activeSignalCount"], 3)
        self.assertIsNotNone(contract["navigation"]["warningReview"])

    def test_s04_access_restricted_state(self):
        contract = build_s04_delta_review_contract(
            review_approval_service=ReviewApprovalService(),
            access_restricted=True,
            access_restricted_reason="scope_denied",
        )

        self.assertEqual(contract["viewState"]["screenState"], "access_restricted")
        self.assertTrue(contract["viewState"]["accessRestricted"])
        self.assertEqual(contract["viewState"]["accessRestrictedReason"], "scope_denied")
        self.assertEqual(contract["groupedDeltaReview"], [])
        self.assertEqual(
            sorted(contract["activation"]["downstreamWorkflow"].keys()),
            [
                "currentStep",
                "handoffRequired",
                "lastErrorCode",
                "lastErrorMessage",
                "ownerService",
                "stepStates",
                "workflowInstanceId",
                "workflowState",
            ],
        )

    def test_s04_no_data_state_preserves_activation_contract_shape(self):
        contract = build_s04_delta_review_contract(
            review_approval_service=ReviewApprovalService(),
            review_context_id="missing-review-context",
            planning_context_key="context::missing",
        )

        self.assertEqual(contract["viewState"]["screenState"], "no_data")
        self.assertEqual(contract["groupedDeltaReview"], [])
        self.assertEqual(
            sorted(contract["activation"]["downstreamWorkflow"].keys()),
            [
                "currentStep",
                "handoffRequired",
                "lastErrorCode",
                "lastErrorMessage",
                "ownerService",
                "stepStates",
                "workflowInstanceId",
                "workflowState",
            ],
        )

    def test_s04_and_m01_contract_shapes(self):
        review_approval_service, review_context, execution_result = build_review_context(
            "review_approval_delta_dependency_linked.json",
            "s04-contract-shape",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )
        submit_s04_delta_acceptance_selection(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )

        review_contract = build_s04_delta_review_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            planning_context_key=execution_result.execution_record.planning_context_key,
            focused_delta_id=requested_delta.delta_id,
        )
        modal_contract = build_m01_connected_change_set_contract(
            review_approval_service=review_approval_service,
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
        )

        self.assertEqual(
            sorted(review_contract.keys()),
            [
                "acceptanceState",
                "activation",
                "blockedAcceptance",
                "deltaSummary",
                "groupedDeltaReview",
                "navigation",
                "queryContext",
                "reviewContextStatus",
                "screen",
                "viewState",
                "warningTrustContext",
            ],
        )
        self.assertEqual(
            sorted(review_contract["activation"].keys()),
            [
                "actionAvailable",
                "activationId",
                "approvedPlanIdAfter",
                "approvedPlanIdBefore",
                "businessRuleBlockers",
                "commandLabel",
                "downstreamWorkflow",
                "outcome",
                "selectedDeltaIds",
                "status",
            ],
        )
        self.assertEqual(
            sorted(review_contract["activation"]["downstreamWorkflow"].keys()),
            [
                "currentStep",
                "handoffRequired",
                "lastErrorCode",
                "lastErrorMessage",
                "ownerService",
                "stepStates",
                "workflowInstanceId",
                "workflowState",
            ],
        )
        self.assertEqual(
            sorted(review_contract["groupedDeltaReview"][0]["items"][0].keys()),
            [
                "acceptanceState",
                "attributeChanges",
                "connectedSetEntry",
                "deltaId",
                "deltaScopeAttributes",
                "dependencyBlockers",
                "entityExternalId",
                "entityId",
                "entityName",
                "entityType",
                "projectExternalId",
                "projectId",
                "recommendationOriginContext",
                "taskExternalId",
                "taskId",
                "taskName",
            ],
        )
        self.assertEqual(
            sorted(modal_contract.keys()),
            [
                "actions",
                "blockingReason",
                "connectedSet",
                "navigation",
                "queryContext",
                "requestedDelta",
                "screen",
                "viewState",
            ],
        )

    def test_acceptance_commands_route_to_review_approval_service(self):
        spy_service, review_context, _ = build_review_context(
            "review_approval_delta_simple.json",
            "s04-command-routing",
            service_factory=SpyReviewApprovalService,
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-rollout"
        )

        command_result = submit_s04_delta_acceptance_selection(
            review_approval_service=spy_service,
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )

        self.assertEqual(
            spy_service.delta_selection_calls,
            [(review_context.review_context_id, requested_delta.delta_id, True)],
        )
        self.assertEqual(command_result["status"], "applied")

    def test_m01_acceptance_command_routes_to_review_approval_service(self):
        spy_service, review_context, _ = build_review_context(
            "review_approval_delta_dependency_linked.json",
            "m01-command-routing",
            service_factory=SpyReviewApprovalService,
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        command_result = submit_m01_connected_set_acceptance_selection(
            review_approval_service=spy_service,
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
            selected=True,
        )

        self.assertEqual(
            spy_service.connected_set_selection_calls,
            [(review_context.review_context_id, requested_delta.delta_id, True)],
        )
        self.assertEqual(command_result["status"], "applied")

    def test_activation_command_routes_to_review_approval_service(self):
        spy_service, review_context, _ = build_review_context(
            "review_approval_delta_simple.json",
            "s04-activation-command-routing",
            service_factory=SpyReviewApprovalService,
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-rollout"
        )
        submit_s04_delta_acceptance_selection(
            review_approval_service=spy_service,
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )

        command_result = submit_s04_activation_command(
            review_approval_service=spy_service,
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T10:10:00Z",
        )

        self.assertEqual(
            spy_service.activation_calls,
            [
                (
                    review_context.review_context_id,
                    "approver@example.com",
                    "2026-04-06T10:10:00Z",
                )
            ],
        )
        self.assertEqual(command_result["status"], "activated")


if __name__ == "__main__":
    unittest.main()
