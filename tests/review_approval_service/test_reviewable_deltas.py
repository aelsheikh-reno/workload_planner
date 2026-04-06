import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.planning_engine_service.service import PlanningEngineService
from services.review_approval_service import (
    DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS,
    DELTA_SCOPE_ATTRIBUTE_MILESTONE_DATE,
    DELTA_SCOPE_ATTRIBUTE_PROJECT_FINISH_DATE,
    DELTA_SCOPE_ATTRIBUTE_TASK_DUE_DATE,
    DELTA_SCOPE_ATTRIBUTE_TASK_START_DATE,
    ApprovedOperatingPlanSnapshot,
    ApprovedPlanProjectRecord,
    ApprovedPlanTaskRecord,
    RecommendationOriginReference,
    ReviewApprovalService,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def execute_scenario(fixture_name, planning_run_key):
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
        requested_at="2026-04-05T15:00:00Z",
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
    return execution_result, approved_plan_snapshot, recommendation_origin_refs


class ReviewApprovalDeltaGenerationTests(unittest.TestCase):
    def setUp(self):
        self.service = ReviewApprovalService()

    def test_no_delta_case(self):
        execution_result, approved_plan_snapshot, recommendation_origin_refs = execute_scenario(
            "review_approval_delta_no_delta.json",
            "review-delta-none",
        )

        review_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )

        self.assertEqual(review_context.comparison_context, "draft_vs_current_approved_plan")
        self.assertEqual(review_context.delta_items, [])
        self.assertEqual(review_context.connected_change_sets, [])
        persisted = self.service.get_review_context(review_context.review_context_id)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.to_dict(), review_context.to_dict())

    def test_draft_vs_approved_delta_generation(self):
        execution_result, approved_plan_snapshot, recommendation_origin_refs = execute_scenario(
            "review_approval_delta_simple.json",
            "review-delta-simple",
        )

        review_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )

        self.assertEqual(len(review_context.delta_items), 2)
        task_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-rollout"
        )
        project_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_type == "project"
        )

        self.assertEqual(
            task_delta.delta_scope_attributes,
            [
                DELTA_SCOPE_ATTRIBUTE_TASK_START_DATE,
                DELTA_SCOPE_ATTRIBUTE_TASK_DUE_DATE,
                DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS,
            ],
        )
        self.assertEqual(
            [ref.recommendation_id for ref in task_delta.recommendation_origin_refs],
            ["recommendation-rollout-review"],
        )
        self.assertEqual(
            project_delta.delta_scope_attributes,
            [DELTA_SCOPE_ATTRIBUTE_PROJECT_FINISH_DATE],
        )
        self.assertIsNotNone(project_delta.project_id)
        self.assertEqual(project_delta.entity_id, project_delta.project_id)

    def test_delta_scope_includes_only_approved_attributes(self):
        execution_result, approved_plan_snapshot, recommendation_origin_refs = execute_scenario(
            "review_approval_delta_simple.json",
            "review-delta-scope",
        )

        review_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )

        allowed_attributes = {
            DELTA_SCOPE_ATTRIBUTE_TASK_START_DATE,
            DELTA_SCOPE_ATTRIBUTE_TASK_DUE_DATE,
            DELTA_SCOPE_ATTRIBUTE_MILESTONE_DATE,
            DELTA_SCOPE_ATTRIBUTE_PROJECT_FINISH_DATE,
            DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS,
        }
        observed_attributes = {
            attribute_change.attribute_name
            for delta_item in review_context.delta_items
            for attribute_change in delta_item.attribute_changes
        }

        self.assertTrue(observed_attributes)
        self.assertTrue(observed_attributes.issubset(allowed_attributes))

    def test_milestone_delta_generation_uses_milestone_date_scope(self):
        execution_result, approved_plan_snapshot, recommendation_origin_refs = execute_scenario(
            "review_approval_delta_milestone.json",
            "review-delta-milestone",
        )

        review_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )

        milestone_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_type == "milestone"
        )

        self.assertEqual(milestone_delta.entity_external_id, "task-rollout")
        self.assertEqual(
            milestone_delta.delta_scope_attributes,
            [DELTA_SCOPE_ATTRIBUTE_MILESTONE_DATE],
        )

    def test_project_scoped_task_matching_and_recommendation_origin_refs_do_not_collide(self):
        execution_result, approved_plan_snapshot, recommendation_origin_refs = execute_scenario(
            "review_approval_delta_project_scoped_collision.json",
            "review-delta-project-scoped",
        )

        review_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )

        task_deltas = [
            delta
            for delta in review_context.delta_items
            if delta.entity_type == "task"
        ]
        self.assertEqual(len(task_deltas), 2)

        delta_by_project = {
            delta.project_external_id: delta
            for delta in task_deltas
        }
        self.assertEqual(
            set(delta_by_project.keys()),
            {"project-alpha", "project-beta"},
        )
        self.assertEqual(
            delta_by_project["project-alpha"].recommendation_origin_refs,
            [],
        )
        self.assertEqual(
            [ref.recommendation_id for ref in delta_by_project["project-beta"].recommendation_origin_refs],
            ["recommendation-project-beta-shared-task"],
        )

    def test_dependency_linked_delta_case(self):
        execution_result, approved_plan_snapshot, recommendation_origin_refs = execute_scenario(
            "review_approval_delta_dependency_linked.json",
            "review-delta-linked",
        )

        review_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )

        self.assertEqual(len(review_context.delta_items), 3)
        self.assertEqual(len(review_context.connected_change_sets), 1)
        connected_set = review_context.connected_change_sets[0]
        task_deltas = [
            delta
            for delta in review_context.delta_items
            if delta.entity_type == "task"
        ]

        self.assertEqual(
            sorted(delta.entity_external_id for delta in task_deltas),
            ["task-design", "task-implement"],
        )
        self.assertTrue(all(delta.connected_set_id == connected_set.connected_set_id for delta in task_deltas))
        self.assertEqual(
            connected_set.member_entity_external_ids,
            ["task-design", "task-implement"],
        )

    def test_connected_set_determination_for_unsafe_isolated_acceptance_case(self):
        execution_result, approved_plan_snapshot, recommendation_origin_refs = execute_scenario(
            "review_approval_delta_dependency_linked.json",
            "review-delta-resolution",
        )

        review_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        resolution = self.service.resolve_connected_change_set(
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
        )

        self.assertFalse(resolution.isolated_acceptance_safe)
        self.assertEqual(resolution.blocking_reason_code, "connected_set_required")
        self.assertEqual(
            resolution.connected_change_set.member_entity_external_ids,
            ["task-design", "task-implement"],
        )

    def test_deterministic_connected_set_output_for_identical_inputs(self):
        execution_result, approved_plan_snapshot, recommendation_origin_refs = execute_scenario(
            "review_approval_delta_dependency_linked.json",
            "review-delta-deterministic",
        )

        first_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )
        second_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )
        first_requested_delta = next(
            delta
            for delta in first_context.delta_items
            if delta.entity_external_id == "task-implement"
        )
        second_requested_delta = next(
            delta
            for delta in second_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        first_resolution = self.service.resolve_connected_change_set(
            review_context_id=first_context.review_context_id,
            requested_delta_id=first_requested_delta.delta_id,
        )
        second_resolution = self.service.resolve_connected_change_set(
            review_context_id=second_context.review_context_id,
            requested_delta_id=second_requested_delta.delta_id,
        )

        self.assertEqual(first_context.to_dict(), second_context.to_dict())
        self.assertEqual(first_resolution.to_dict(), second_resolution.to_dict())

    def test_review_context_and_connected_set_contract_shapes(self):
        execution_result, approved_plan_snapshot, recommendation_origin_refs = execute_scenario(
            "review_approval_delta_dependency_linked.json",
            "review-delta-contract",
        )

        review_context = self.service.generate_reviewable_delta_set(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs,
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )
        resolution = self.service.resolve_connected_change_set(
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
        )

        review_contract = review_context.to_dict()
        resolution_contract = resolution.to_dict()
        self.assertEqual(
            sorted(review_contract.keys()),
            [
                "approved_plan_id",
                "comparison_context",
                "connected_change_sets",
                "delta_items",
                "delta_set_id",
                "draft_schedule_id",
                "planning_run_id",
                "review_context_id",
                "source_snapshot_id",
            ],
        )
        self.assertEqual(
            sorted(review_contract["delta_items"][0].keys()),
            [
                "attribute_changes",
                "connected_set_id",
                "delta_id",
                "delta_scope_attributes",
                "dependency_delta_ids",
                "entity_external_id",
                "entity_id",
                "entity_name",
                "entity_type",
                "project_external_id",
                "project_id",
                "recommendation_origin_refs",
                "selected_for_acceptance",
                "task_external_id",
                "task_id",
                "task_name",
            ],
        )
        project_delta_contract = next(
            item
            for item in review_contract["delta_items"]
            if item["entity_type"] == "project"
        )
        self.assertIsNotNone(project_delta_contract["project_id"])
        self.assertEqual(
            project_delta_contract["entity_id"],
            project_delta_contract["project_id"],
        )
        self.assertEqual(
            sorted(resolution_contract.keys()),
            [
                "blocking_reason_code",
                "blocking_reason_message",
                "connected_change_set",
                "isolated_acceptance_safe",
                "requested_delta_id",
                "resolution_id",
                "review_context_id",
            ],
        )
