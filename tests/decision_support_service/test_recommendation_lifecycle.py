import json
import unittest
from pathlib import Path

from services.decision_support_service import (
    DecisionSupportService,
    RECOMMENDATION_ACTION_FAMILY_DATE_EXTENSION,
    RECOMMENDATION_ACTION_FAMILY_MOVE_DEFER,
    RECOMMENDATION_ACTION_FAMILY_REASSIGNMENT,
    RECOMMENDATION_ACTION_FAMILY_RECHUNK,
    RECOMMENDATION_CONTEXT_STATE_AVAILABLE,
    RECOMMENDATION_CONTEXT_STATE_NO_ACTIONABLE,
    RECOMMENDATION_FRESHNESS_FRESH,
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
        requested_at="2026-04-05T10:00:00Z",
        attempt_number=1,
    )
    return bundle, execution_result


class DecisionSupportRecommendationLifecycleTests(unittest.TestCase):
    def test_recommendation_generation_happy_path_with_multiple_candidates(self):
        _, execution_result = execute_fixture(
            "source_plan_recommendation_multi_candidate.json",
            "recommendation-happy-path",
        )
        service = DecisionSupportService()

        state = service.refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id="user-riley",
        )

        self.assertEqual(state.state, RECOMMENDATION_CONTEXT_STATE_AVAILABLE)
        self.assertEqual(state.freshness_status, RECOMMENDATION_FRESHNESS_FRESH)
        self.assertEqual(state.actionable_recommendation_count, 5)
        self.assertEqual(state.total_recommendation_count, 5)
        self.assertEqual(
            [candidate.action_family for candidate in state.recommendations],
            [
                RECOMMENDATION_ACTION_FAMILY_RECHUNK,
                RECOMMENDATION_ACTION_FAMILY_REASSIGNMENT,
                RECOMMENDATION_ACTION_FAMILY_DATE_EXTENSION,
                RECOMMENDATION_ACTION_FAMILY_MOVE_DEFER,
                RECOMMENDATION_ACTION_FAMILY_MOVE_DEFER,
            ],
        )
        self.assertTrue(state.recommendations[0].requires_review)
        self.assertFalse(state.recommendations[-1].requires_review)

    def test_recommendation_ranking_is_deterministic_for_identical_inputs(self):
        _, execution_result = execute_fixture(
            "source_plan_recommendation_multi_candidate.json",
            "recommendation-deterministic",
        )
        service = DecisionSupportService()

        first = service.refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id="user-riley",
        )
        second = service.refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id="user-riley",
        )

        self.assertEqual(first.to_dict(), second.to_dict())

    def test_equal_score_candidates_follow_locked_tie_break_order(self):
        _, execution_result = execute_fixture(
            "source_plan_recommendation_multi_candidate.json",
            "recommendation-tie-break",
        )
        service = DecisionSupportService()

        state = service.refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id="user-riley",
        )

        recommendation_ids = [
            candidate.recommendation_id for candidate in state.recommendations
        ]
        self.assertEqual(
            [candidate.priority_rank for candidate in state.recommendations],
            [1, 2, 3, 4, 5],
        )
        self.assertLess(
            state.recommendations[0].disruption_score,
            state.recommendations[1].disruption_score,
        )
        self.assertEqual(
            state.recommendations[1].handoff_overhead_score,
            state.recommendations[2].handoff_overhead_score,
        )
        self.assertEqual(
            state.recommendations[1].action_family,
            RECOMMENDATION_ACTION_FAMILY_REASSIGNMENT,
        )
        self.assertEqual(
            state.recommendations[2].action_family,
            RECOMMENDATION_ACTION_FAMILY_DATE_EXTENSION,
        )
        self.assertLess(recommendation_ids[3], recommendation_ids[4])

    def test_no_actionable_recommendation_case(self):
        _, execution_result = execute_fixture(
            "source_plan_resource_detail_balanced.json",
            "recommendation-none",
        )
        service = DecisionSupportService()

        state = service.refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id="user-taylor",
        )

        self.assertEqual(state.state, RECOMMENDATION_CONTEXT_STATE_NO_ACTIONABLE)
        self.assertEqual(state.recommendations, [])
        self.assertEqual(state.actionable_recommendation_count, 0)

    def test_unsafe_or_disallowed_candidates_are_excluded(self):
        _, execution_result = execute_fixture(
            "source_plan_schedule_partial_unschedulable.json",
            "recommendation-exclusion",
        )
        service = DecisionSupportService()

        state = service.refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id="user-lee",
        )

        self.assertTrue(state.recommendations)
        self.assertFalse(
            any(
                candidate.action_family == RECOMMENDATION_ACTION_FAMILY_REASSIGNMENT
                for candidate in state.recommendations
            )
        )
        self.assertFalse(
            any(
                candidate.origin_context is not None
                and candidate.origin_context.task_external_id == "task-qa"
                for candidate in state.recommendations
            )
        )

    def test_recommendation_contract_shape_and_origin_context(self):
        _, execution_result = execute_fixture(
            "source_plan_recommendation_multi_candidate.json",
            "recommendation-origin-context",
        )
        service = DecisionSupportService()

        state = service.refresh_resource_recommendation_context(
            execution_result=execution_result,
            resource_external_id="user-riley",
        )
        candidate = state.recommendations[0]
        retrieved_candidate = service.get_recommendation_candidate(
            candidate.recommendation_id
        )
        origin_context = service.get_recommendation_origin_context(
            candidate.recommendation_id
        )

        self.assertIsNotNone(retrieved_candidate)
        self.assertIsNotNone(origin_context)
        self.assertEqual(
            sorted(candidate.to_dict().keys()),
            [
                "action_family",
                "affected_task_external_ids",
                "affected_task_ids",
                "disruption_score",
                "effect_summary",
                "handoff_overhead_score",
                "origin_context",
                "planning_context_key",
                "priority_rank",
                "ranking_policy",
                "ranking_score",
                "rationale",
                "recommendation_id",
                "requires_review",
                "resource_external_id",
                "resource_id",
                "source_snapshot_id",
                "summary",
                "title",
                "trigger_issue_fact_ids",
            ],
        )
        self.assertEqual(origin_context.origin_screen_id, "S03")
        self.assertEqual(
            origin_context.planning_run_id,
            execution_result.execution_record.planning_run_id,
        )
        self.assertEqual(origin_context.task_external_id, "task-01-critical-core")
