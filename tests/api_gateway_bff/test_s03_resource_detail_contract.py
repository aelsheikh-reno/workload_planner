import json
import unittest
from pathlib import Path

from services.api_gateway_bff.s03_resource_detail_contract import (
    build_s03_resource_detail_contract,
)
from services.decision_support_service import (
    DecisionSupportService,
    RecommendationCandidate,
    ScreenWarningTrustSignal,
)
from services.integration_service.service import IntegrationService
from services.planning_engine_service.service import PlanningEngineService


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def execute_fixture(fixture_name, planning_run_id):
    integration_service = IntegrationService()
    planning_engine_service = PlanningEngineService()
    bundle = integration_service.import_source_plan(load_fixture(fixture_name))
    execution_result = planning_engine_service.execute_planning_run(
        bundle=bundle,
        workflow_instance_id=f"workflow::{planning_run_id}",
        planning_context_key=f"context::{planning_run_id}",
        source_snapshot_id=bundle.snapshot.snapshot_id,
        source_artifact_id=bundle.artifact.artifact_id,
        requested_by="delivery-manager@example.com",
        requested_at="2026-04-04T13:15:00Z",
        attempt_number=1,
    )
    return planning_engine_service, bundle, execution_result


def publish_recommendations(
    decision_support_service,
    fixture_name,
    resource_external_id,
    planning_context_key,
    source_snapshot_id,
):
    payload = load_fixture(fixture_name)
    recommendations = [
        RecommendationCandidate(
            recommendation_id=item["recommendation_id"],
            resource_id=None,
            resource_external_id=resource_external_id,
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
            title=item["title"],
            summary=item["summary"],
            action_family=item["action_family"],
            priority_rank=item["priority_rank"],
            requires_review=item["requires_review"],
            rationale=item.get("rationale"),
            affected_task_ids=list(item.get("affected_task_ids", [])),
            affected_task_external_ids=list(item.get("affected_task_external_ids", [])),
        )
        for item in payload.get("recommendations", [])
    ]
    return decision_support_service.publish_resource_recommendation_context(
        resource_external_id=resource_external_id,
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
        recommendations=recommendations,
        state=payload["state"],
        freshness_status=payload["freshness_status"],
    )


def publish_warning_state(
    decision_support_service,
    fixture_name,
    resource_external_id,
    planning_context_key,
    source_snapshot_id,
):
    payload = load_fixture(fixture_name)
    signals = []
    for item in payload.get("signals", []):
        signals.append(
            ScreenWarningTrustSignal(
                signal_id=item["signal_id"],
                screen_id="S03",
                source_snapshot_id=source_snapshot_id,
                planning_context_key=planning_context_key,
                signal_type=item["signal_type"],
                severity=item["severity"],
                code=item["code"],
                message=item["message"],
                advisory=item["advisory"],
                blocking=item["blocking"],
                interpretation_category=item["interpretation_category"],
                source_issue_service=item["source_issue_service"],
                source_fact_id=item["source_fact_id"],
                source_fact_type=item["source_fact_type"],
                source_fact_severity=item["source_fact_severity"],
                entity_type=item["entity_type"],
                entity_id=item.get("entity_id"),
                entity_external_id=(
                    resource_external_id
                    if item["entity_type"] == "resource"
                    else item.get("entity_external_id")
                ),
            )
        )
    return decision_support_service.publish_screen_warning_trust_state(
        screen_id="S03",
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
        signals=signals,
    )


class S03ResourceDetailContractTests(unittest.TestCase):
    def test_s03_normal_diagnostic_state(self):
        planning_engine_service, bundle, execution_result = execute_fixture(
            "source_plan_resource_detail_balanced.json",
            "s03-ready",
        )
        decision_support_service = DecisionSupportService()
        publish_recommendations(
            decision_support_service,
            "decision_support_s03_recommendations_ready.json",
            resource_external_id="user-taylor",
            planning_context_key=execution_result.execution_record.planning_context_key,
            source_snapshot_id=bundle.snapshot.snapshot_id,
        )

        contract = build_s03_resource_detail_contract(
            planning_engine_service=planning_engine_service,
            decision_support_service=decision_support_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-taylor",
        )

        self.assertEqual(contract["screen"], {"id": "S03", "label": "Resource Detail"})
        self.assertEqual(contract["viewState"]["screenState"], "ready")
        self.assertEqual(contract["resourceSummary"]["resourceExternalId"], "user-taylor")
        self.assertEqual(contract["resourceSummary"]["totalAllocatedHours"], 40.0)
        self.assertEqual(contract["resourceSummary"]["totalProductiveCapacityHours"], 40.0)
        self.assertEqual(contract["recommendationContext"]["state"], "available")
        self.assertEqual(contract["recommendationContext"]["actionableRecommendationCount"], 2)
        self.assertEqual(contract["warningTrustContext"]["activeSignalCount"], 0)
        self.assertTrue(contract["navigation"]["reviewHandoff"]["available"])

    def test_s03_overload_focused_state(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_partial_unschedulable.json",
            "s03-overload",
        )

        contract = build_s03_resource_detail_contract(
            planning_engine_service=planning_engine_service,
            decision_support_service=DecisionSupportService(),
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-lee",
        )

        self.assertEqual(contract["viewState"]["screenState"], "overload_focused")
        self.assertGreater(contract["resourceSummary"]["ghostTaskCount"], 0)
        self.assertGreater(contract["resourceSummary"]["ghostUnscheduledEffortHours"], 0.0)
        self.assertTrue(any(item["ghostVisible"] for item in contract["assignedWorkQueue"]))
        self.assertTrue(any(segment["hasGhostLoad"] for segment in contract["workloadTimeline"]))

    def test_s03_underutilized_state(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_happy_path.json",
            "s03-underutilized",
        )

        contract = build_s03_resource_detail_contract(
            planning_engine_service=planning_engine_service,
            decision_support_service=DecisionSupportService(),
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-ada",
        )

        self.assertEqual(contract["viewState"]["screenState"], "underutilized")
        self.assertGreater(contract["resourceSummary"]["freeCapacityDayCount"], 0)
        self.assertEqual(contract["recommendationContext"]["state"], "not_available")

    def test_s03_warning_heavy_state(self):
        planning_engine_service, bundle, execution_result = execute_fixture(
            "source_plan_resource_detail_balanced.json",
            "s03-warning-heavy",
        )
        decision_support_service = DecisionSupportService()
        publish_warning_state(
            decision_support_service,
            "decision_support_s03_warning_context_heavy.json",
            resource_external_id="user-taylor",
            planning_context_key=execution_result.execution_record.planning_context_key,
            source_snapshot_id=bundle.snapshot.snapshot_id,
        )

        contract = build_s03_resource_detail_contract(
            planning_engine_service=planning_engine_service,
            decision_support_service=decision_support_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-taylor",
        )

        self.assertEqual(contract["viewState"]["screenState"], "warning_heavy")
        self.assertTrue(contract["warningTrustContext"]["warningHeavy"])
        self.assertEqual(contract["warningTrustContext"]["activeSignalCount"], 3)
        self.assertTrue(contract["navigation"]["warningReview"]["available"])

    def test_s03_no_actionable_recommendation_state(self):
        planning_engine_service, bundle, execution_result = execute_fixture(
            "source_plan_resource_detail_balanced.json",
            "s03-no-actionable",
        )
        decision_support_service = DecisionSupportService()
        publish_recommendations(
            decision_support_service,
            "decision_support_s03_recommendations_none.json",
            resource_external_id="user-taylor",
            planning_context_key=execution_result.execution_record.planning_context_key,
            source_snapshot_id=bundle.snapshot.snapshot_id,
        )

        contract = build_s03_resource_detail_contract(
            planning_engine_service=planning_engine_service,
            decision_support_service=decision_support_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-taylor",
        )

        self.assertEqual(contract["viewState"]["screenState"], "no_actionable_recommendation")
        self.assertEqual(contract["recommendationContext"]["state"], "no_actionable_recommendations")
        self.assertEqual(contract["recommendationContext"]["items"], [])

    def test_s03_loading_and_refresh_state(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_resource_detail_balanced.json",
            "s03-loading",
        )

        contract = build_s03_resource_detail_contract(
            planning_engine_service=planning_engine_service,
            decision_support_service=DecisionSupportService(),
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-taylor",
            is_loading=True,
            is_refreshing=True,
        )

        self.assertEqual(contract["viewState"]["screenState"], "loading")
        self.assertTrue(contract["viewState"]["isLoading"])
        self.assertTrue(contract["viewState"]["isRefreshing"])

    def test_s03_access_restricted_state(self):
        contract = build_s03_resource_detail_contract(
            planning_engine_service=PlanningEngineService(),
            decision_support_service=DecisionSupportService(),
            resource_external_id="user-taylor",
            access_restricted=True,
            access_restricted_reason="scope_denied",
        )

        self.assertEqual(contract["viewState"]["screenState"], "access_restricted")
        self.assertTrue(contract["viewState"]["accessRestricted"])
        self.assertEqual(contract["viewState"]["accessRestrictedReason"], "scope_denied")
        self.assertEqual(contract["assignedWorkQueue"], [])

    def test_recommendation_context_remains_visible_when_trust_is_affected(self):
        planning_engine_service, bundle, execution_result = execute_fixture(
            "source_plan_resource_detail_balanced.json",
            "s03-trust-affected",
        )
        decision_support_service = DecisionSupportService()
        publish_recommendations(
            decision_support_service,
            "decision_support_s03_recommendations_ready.json",
            resource_external_id="user-taylor",
            planning_context_key=execution_result.execution_record.planning_context_key,
            source_snapshot_id=bundle.snapshot.snapshot_id,
        )
        publish_warning_state(
            decision_support_service,
            "decision_support_s03_warning_context_trust.json",
            resource_external_id="user-taylor",
            planning_context_key=execution_result.execution_record.planning_context_key,
            source_snapshot_id=bundle.snapshot.snapshot_id,
        )

        contract = build_s03_resource_detail_contract(
            planning_engine_service=planning_engine_service,
            decision_support_service=decision_support_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-taylor",
        )

        self.assertEqual(contract["viewState"]["screenState"], "ready")
        self.assertEqual(contract["recommendationContext"]["actionableRecommendationCount"], 2)
        self.assertTrue(contract["recommendationContext"]["trustAffected"])
        self.assertGreater(contract["recommendationContext"]["trustAffectedRecommendationCount"], 0)
        self.assertTrue(any(item["trustAffected"] for item in contract["recommendationContext"]["items"]))

    def test_queue_and_timeline_coexistence_and_consistency(self):
        planning_engine_service, bundle, execution_result = execute_fixture(
            "source_plan_resource_detail_balanced.json",
            "s03-consistency",
        )
        decision_support_service = DecisionSupportService()
        publish_recommendations(
            decision_support_service,
            "decision_support_s03_recommendations_ready.json",
            resource_external_id="user-taylor",
            planning_context_key=execution_result.execution_record.planning_context_key,
            source_snapshot_id=bundle.snapshot.snapshot_id,
        )

        contract = build_s03_resource_detail_contract(
            planning_engine_service=planning_engine_service,
            decision_support_service=decision_support_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-taylor",
        )

        queue_task_ids = {item["taskExternalId"] for item in contract["assignedWorkQueue"]}
        timeline_task_ids = {
            task_ref["taskExternalId"]
            for segment in contract["workloadTimeline"]
            for task_ref in segment["taskRefs"]
        }

        self.assertTrue(contract["workloadTimeline"])
        self.assertTrue(contract["assignedWorkQueue"])
        self.assertEqual(queue_task_ids, timeline_task_ids)
        self.assertEqual(
            round(sum(item["queueAllocatedHours"] for item in contract["assignedWorkQueue"]), 4),
            contract["resourceSummary"]["totalAllocatedHours"],
        )
        self.assertEqual(
            round(sum(segment["allocatedHours"] for segment in contract["workloadTimeline"]), 4),
            contract["resourceSummary"]["totalAllocatedHours"],
        )

    def test_s03_contract_shape(self):
        planning_engine_service, bundle, execution_result = execute_fixture(
            "source_plan_resource_detail_balanced.json",
            "s03-contract",
        )
        decision_support_service = DecisionSupportService()
        publish_recommendations(
            decision_support_service,
            "decision_support_s03_recommendations_ready.json",
            resource_external_id="user-taylor",
            planning_context_key=execution_result.execution_record.planning_context_key,
            source_snapshot_id=bundle.snapshot.snapshot_id,
        )

        contract = build_s03_resource_detail_contract(
            planning_engine_service=planning_engine_service,
            decision_support_service=decision_support_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-taylor",
        )

        self.assertEqual(
            sorted(contract.keys()),
            [
                "assignedWorkQueue",
                "navigation",
                "queryContext",
                "recommendationContext",
                "resourceSummary",
                "screen",
                "unavailableState",
                "viewState",
                "warningTrustContext",
                "workloadTimeline",
            ],
        )
        self.assertEqual(
            sorted(contract["assignedWorkQueue"][0].keys()),
            [
                "allocations",
                "ghostVisible",
                "movementIndicator",
                "planningIssues",
                "projectExternalId",
                "projectId",
                "queueAllocatedHours",
                "requestedDueDate",
                "requestedStartDate",
                "requiredEffortHours",
                "resourceExternalId",
                "resourceId",
                "riskIndicator",
                "scheduledEffortHours",
                "scheduledEndDate",
                "scheduledStartDate",
                "status",
                "taskExternalId",
                "taskId",
                "taskName",
                "unscheduledEffortHours",
            ],
        )
        self.assertEqual(
            sorted(contract["recommendationContext"]["items"][0].keys()),
            [
                "actionFamily",
                "affectedTaskExternalIds",
                "affectedTaskIds",
                "effectSummary",
                "originContext",
                "priorityRank",
                "rationale",
                "recommendationId",
                "requiresReviewHandoff",
                "reviewNavigation",
                "summary",
                "title",
                "trustAffected",
            ],
        )
