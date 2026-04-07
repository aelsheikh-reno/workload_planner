import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.planning_engine_service.service import PlanningEngineService
from services.review_approval_service import (
    ACTIVATION_STATUS_ACTIVATED,
    ACTIVATION_STATUS_BLOCKED,
    ACTIVATION_WORKFLOW_STATE_NOT_STARTED,
    DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS,
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


def build_review_context(fixture_name, planning_run_key):
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
        requested_at="2026-04-06T08:00:00Z",
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
    service = ReviewApprovalService()
    review_context = service.generate_reviewable_delta_set(
        execution_result=execution_result,
        approved_plan_snapshot=approved_plan_snapshot,
        recommendation_origin_refs=recommendation_origin_refs,
    )
    return service, review_context


def get_delta(review_context, entity_external_id):
    return next(
        delta
        for delta in review_context.delta_items
        if delta.entity_external_id == entity_external_id
    )


def get_task(snapshot, task_external_id):
    return next(task for task in snapshot.tasks if task.task_external_id == task_external_id)


class ReviewApprovalActivationCommandTests(unittest.TestCase):
    def test_valid_activation_from_selected_approved_set_updates_current_snapshot(self):
        service, review_context = build_review_context(
            "review_approval_delta_simple.json",
            "activation-valid",
        )
        requested_delta = get_delta(review_context, "task-rollout")
        attribute_changes = {
            change.attribute_name: change.after_value
            for change in requested_delta.attribute_changes
        }

        service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        result = service.activate_approved_changes(
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T09:00:00Z",
        )

        self.assertEqual(result.activation_state.status, ACTIVATION_STATUS_ACTIVATED)
        self.assertFalse(result.reused_existing)
        self.assertEqual(
            result.activation_state.review_context_id,
            review_context.review_context_id,
        )
        self.assertEqual(
            result.activation_state.approved_plan_id_before,
            review_context.approved_plan_id,
        )
        self.assertNotEqual(
            result.activation_state.approved_plan_id_after,
            review_context.approved_plan_id,
        )
        self.assertEqual(
            result.downstream_handoff.owner_service,
            "Workflow Orchestrator Service",
        )
        self.assertTrue(result.downstream_handoff.handoff_required)
        self.assertEqual(
            result.downstream_handoff.workflow_state,
            ACTIVATION_WORKFLOW_STATE_NOT_STARTED,
        )
        self.assertIsNone(result.downstream_handoff.workflow_instance_id)
        self.assertEqual(
            result.downstream_handoff.source_snapshot_id,
            review_context.source_snapshot_id,
        )
        self.assertEqual(
            [target.entity_external_id for target in result.downstream_handoff.write_back_targets],
            ["task-rollout"],
        )

        current_snapshot = service.get_approved_operating_plan_snapshot(current=True)
        original_snapshot = service.get_approved_operating_plan_snapshot(
            approved_plan_id=review_context.approved_plan_id
        )
        self.assertIsNotNone(current_snapshot)
        self.assertIsNotNone(original_snapshot)
        self.assertEqual(
            current_snapshot.approved_plan_id,
            result.activation_state.approved_plan_id_after,
        )
        rollout_task = get_task(current_snapshot, "task-rollout")
        self.assertEqual(
            rollout_task.approved_start_date,
            attribute_changes[DELTA_SCOPE_ATTRIBUTE_TASK_START_DATE],
        )
        self.assertEqual(
            rollout_task.approved_due_date,
            attribute_changes[DELTA_SCOPE_ATTRIBUTE_TASK_DUE_DATE],
        )
        self.assertEqual(
            rollout_task.assigned_resource_external_ids,
            sorted(attribute_changes[DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS]),
        )
        self.assertNotEqual(
            original_snapshot.approved_plan_id,
            current_snapshot.approved_plan_id,
        )

        emission = service.get_issue_fact_emission(
            activation_id=result.activation_state.activation_id
        )
        self.assertIsNotNone(emission)
        self.assertEqual(
            [fact.code for fact in emission.issue_facts],
            ["activation_completed"],
        )

    def test_invalid_activation_without_valid_approved_set_is_blocked(self):
        service, review_context = build_review_context(
            "review_approval_delta_simple.json",
            "activation-invalid-no-selection",
        )

        result = service.activate_approved_changes(
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T09:10:00Z",
        )

        self.assertEqual(result.activation_state.status, ACTIVATION_STATUS_BLOCKED)
        self.assertEqual(
            [blocker.code for blocker in result.activation_state.business_rule_blockers],
            ["activation_requires_approved_set"],
        )
        self.assertIsNone(result.resulting_approved_plan_snapshot)
        self.assertFalse(result.downstream_handoff.handoff_required)
        self.assertEqual(
            service.get_approved_operating_plan_snapshot(current=True).approved_plan_id,
            review_context.approved_plan_id,
        )

    def test_repeated_activation_is_idempotent_for_identical_selected_set(self):
        service, review_context = build_review_context(
            "review_approval_delta_simple.json",
            "activation-idempotent",
        )
        requested_delta = get_delta(review_context, "task-rollout")
        service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )

        first = service.activate_approved_changes(
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T09:20:00Z",
        )
        second = service.activate_approved_changes(
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T09:25:00Z",
        )

        self.assertEqual(first.activation_state.activation_id, second.activation_state.activation_id)
        self.assertFalse(first.reused_existing)
        self.assertTrue(second.reused_existing)
        self.assertEqual(
            first.activation_state.approved_plan_id_after,
            second.activation_state.approved_plan_id_after,
        )

    def test_activation_contract_shape(self):
        service, review_context = build_review_context(
            "review_approval_delta_simple.json",
            "activation-contract-shape",
        )
        requested_delta = get_delta(review_context, "task-rollout")
        service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )

        result = service.activate_approved_changes(
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T09:30:00Z",
        )
        contract = result.to_dict()

        self.assertEqual(
            sorted(contract.keys()),
            [
                "activation_state",
                "command_id",
                "downstream_handoff",
                "resulting_approved_plan_snapshot",
                "reused_existing",
                "review_context_id",
            ],
        )
        self.assertEqual(
            sorted(contract["activation_state"].keys()),
            [
                "activation_id",
                "approved_plan_id_after",
                "approved_plan_id_before",
                "business_rule_blockers",
                "outcome",
                "requested_at",
                "requested_by",
                "review_context_id",
                "selected_delta_ids",
                "status",
            ],
        )
        self.assertEqual(
            sorted(contract["downstream_handoff"].keys()),
            [
                "handoff_required",
                "owner_service",
                "source_snapshot_id",
                "workflow_instance_id",
                "workflow_state",
                "write_back_targets",
            ],
        )

    def test_workflow_execution_is_not_owned_here(self):
        service, review_context = build_review_context(
            "review_approval_delta_simple.json",
            "activation-boundary",
        )
        requested_delta = get_delta(review_context, "task-rollout")
        service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )

        payload = service.activate_approved_changes(
            review_context_id=review_context.review_context_id,
            requested_by="approver@example.com",
            requested_at="2026-04-06T09:35:00Z",
        ).to_dict()

        self.assertEqual(
            payload["downstream_handoff"]["owner_service"],
            "Workflow Orchestrator Service",
        )
        self.assertEqual(
            payload["downstream_handoff"]["workflow_state"],
            ACTIVATION_WORKFLOW_STATE_NOT_STARTED,
        )
        self.assertIsNone(payload["downstream_handoff"]["workflow_instance_id"])
        self.assertEqual(
            payload["downstream_handoff"]["source_snapshot_id"],
            review_context.source_snapshot_id,
        )
        self.assertEqual(
            [target["entity_external_id"] for target in payload["downstream_handoff"]["write_back_targets"]],
            ["task-rollout"],
        )
        self.assertNotIn("workflow_instance", payload)
        self.assertNotIn("workflow_status", payload)


if __name__ == "__main__":
    unittest.main()
