import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.planning_engine_service.service import PlanningEngineService
from services.review_approval_service import (
    ACCEPTANCE_SELECTION_SCOPE_CONNECTED_CHANGE_SET,
    ACCEPTANCE_SELECTION_SCOPE_DELTA_ITEM,
    ACCEPTANCE_SELECTION_STATUS_APPLIED,
    ACCEPTANCE_SELECTION_STATUS_BLOCKED,
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


def execute_review_context(fixture_name, planning_run_key):
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
        requested_at="2026-04-05T17:00:00Z",
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


class ReviewApprovalAcceptanceSelectionTests(unittest.TestCase):
    def test_safe_item_selection_and_deselection_mutates_acceptance_state(self):
        service, review_context = execute_review_context(
            "review_approval_delta_simple.json",
            "accept-safe-item",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-rollout"
        )

        selected = service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        deselected = service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=False,
        )

        self.assertEqual(selected.selection_scope, ACCEPTANCE_SELECTION_SCOPE_DELTA_ITEM)
        self.assertEqual(selected.status, ACCEPTANCE_SELECTION_STATUS_APPLIED)
        self.assertTrue(
            next(
                delta.selected_for_acceptance
                for delta in selected.review_context.delta_items
                if delta.delta_id == requested_delta.delta_id
            )
        )
        self.assertEqual(deselected.status, ACCEPTANCE_SELECTION_STATUS_APPLIED)
        self.assertFalse(
            next(
                delta.selected_for_acceptance
                for delta in deselected.review_context.delta_items
                if delta.delta_id == requested_delta.delta_id
            )
        )

    def test_connected_set_item_selection_is_blocked(self):
        service, review_context = execute_review_context(
            "review_approval_delta_dependency_linked.json",
            "accept-blocked-item",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        result = service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )

        self.assertEqual(result.selection_scope, ACCEPTANCE_SELECTION_SCOPE_DELTA_ITEM)
        self.assertEqual(result.status, ACCEPTANCE_SELECTION_STATUS_BLOCKED)
        self.assertEqual(result.blocked_reason_code, "connected_set_required")
        self.assertIsNotNone(result.connected_set_resolution)
        self.assertFalse(
            next(
                delta.selected_for_acceptance
                for delta in result.review_context.delta_items
                if delta.delta_id == requested_delta.delta_id
            )
        )

    def test_blocked_isolated_acceptance_updates_current_issue_facts(self):
        service, review_context = execute_review_context(
            "review_approval_delta_dependency_linked.json",
            "accept-blocked-item-issue-facts",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        emission = service.get_current_review_issue_fact_emission(
            review_context_id=review_context.review_context_id,
        )
        connected_set_id = next(
            delta.connected_set_id
            for delta in review_context.delta_items
            if delta.delta_id == requested_delta.delta_id
        )

        self.assertEqual(emission.blocking_fact_count, 2)
        self.assertEqual(
            {fact.code for fact in emission.issue_facts},
            {"dependency_safe_approval_blocked", "connected_set_required"},
        )
        dependency_fact = next(
            fact
            for fact in emission.issue_facts
            if fact.code == "dependency_safe_approval_blocked"
        )
        self.assertEqual(dependency_fact.entity_id, requested_delta.delta_id)
        self.assertEqual(dependency_fact.related_connected_set_id, connected_set_id)

    def test_connected_set_lookup_alone_does_not_emit_blocker_facts(self):
        service, review_context = execute_review_context(
            "review_approval_delta_dependency_linked.json",
            "accept-connected-set-lookup-only",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        service.resolve_connected_change_set(
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
        )
        emission = service.get_current_review_issue_fact_emission(
            review_context_id=review_context.review_context_id,
        )

        self.assertEqual(emission.total_fact_count, 0)
        self.assertEqual(emission.blocking_fact_count, 0)

    def test_connected_set_selection_clears_unresolved_blocker_issue_facts(self):
        service, review_context = execute_review_context(
            "review_approval_delta_dependency_linked.json",
            "accept-connected-set-clear-blockers",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        service.record_connected_set_acceptance_selection(
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
            selected=True,
        )
        emission = service.get_current_review_issue_fact_emission(
            review_context_id=review_context.review_context_id,
        )

        self.assertEqual(emission.total_fact_count, 0)
        self.assertEqual(emission.blocking_fact_count, 0)
        persisted = service.get_issue_fact_emission(
            review_context_id=review_context.review_context_id
        )
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.to_dict(), emission.to_dict())

    def test_blocker_evaluation_is_deterministic_for_identical_review_state(self):
        service, review_context = execute_review_context(
            "review_approval_delta_dependency_linked.json",
            "accept-deterministic-blockers",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        first = service.get_current_review_issue_fact_emission(
            review_context_id=review_context.review_context_id
        )
        second = service.get_current_review_issue_fact_emission(
            review_context_id=review_context.review_context_id
        )

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.emission_id, second.emission_id)

    def test_connected_set_selection_selects_all_members(self):
        service, review_context = execute_review_context(
            "review_approval_delta_dependency_linked.json",
            "accept-connected-set",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-implement"
        )

        result = service.record_connected_set_acceptance_selection(
            review_context_id=review_context.review_context_id,
            requested_delta_id=requested_delta.delta_id,
            selected=True,
        )

        self.assertEqual(
            result.selection_scope,
            ACCEPTANCE_SELECTION_SCOPE_CONNECTED_CHANGE_SET,
        )
        self.assertEqual(result.status, ACCEPTANCE_SELECTION_STATUS_APPLIED)
        connected_set_members = {
            delta.entity_external_id: delta.selected_for_acceptance
            for delta in result.review_context.delta_items
            if delta.connected_set_id == result.connected_set_id
        }
        self.assertEqual(
            connected_set_members,
            {"task-design": True, "task-implement": True},
        )

    def test_acceptance_selection_contract_shape(self):
        service, review_context = execute_review_context(
            "review_approval_delta_simple.json",
            "accept-contract-shape",
        )
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == "task-rollout"
        )

        result = service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        contract = result.to_dict()

        self.assertEqual(
            sorted(contract.keys()),
            [
                "action",
                "blocked_reason_code",
                "blocked_reason_message",
                "command_id",
                "connected_set_id",
                "connected_set_resolution",
                "requested_delta_id",
                "review_context",
                "review_context_id",
                "selection_scope",
                "status",
            ],
        )


if __name__ == "__main__":
    unittest.main()
