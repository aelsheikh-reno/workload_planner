import json
import unittest
from pathlib import Path

from services.decision_support_service import (
    DecisionSupportService,
    RecommendationCandidate,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def build_candidates(fixture_name, resource_external_id):
    payload = load_fixture(fixture_name)
    return [
        RecommendationCandidate(
            recommendation_id=item["recommendation_id"],
            resource_id=None,
            resource_external_id=resource_external_id,
            planning_context_key="context::recommendation-contract",
            source_snapshot_id="snapshot::recommendation-contract",
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


class DecisionSupportRecommendationContextTests(unittest.TestCase):
    def test_publish_and_get_resource_recommendation_context(self):
        service = DecisionSupportService()
        candidates = build_candidates(
            "decision_support_s03_recommendations_ready.json",
            resource_external_id="user-taylor",
        )

        state = service.publish_resource_recommendation_context(
            resource_external_id="user-taylor",
            planning_context_key="context::recommendation-contract",
            source_snapshot_id="snapshot::recommendation-contract",
            recommendations=candidates,
        )
        retrieved_state = service.get_resource_recommendation_context(
            resource_external_id="user-taylor",
            planning_context_key="context::recommendation-contract",
            source_snapshot_id="snapshot::recommendation-contract",
        )

        self.assertIsNotNone(retrieved_state)
        self.assertEqual(state.to_dict(), retrieved_state.to_dict())
        self.assertEqual(retrieved_state.actionable_recommendation_count, 2)
        self.assertEqual(
            [item.recommendation_id for item in retrieved_state.recommendations],
            ["rec-01", "rec-02"],
        )

    def test_recommendation_context_shape_and_determinism(self):
        service = DecisionSupportService()
        candidates = build_candidates(
            "decision_support_s03_recommendations_ready.json",
            resource_external_id="user-taylor",
        )

        first = service.publish_resource_recommendation_context(
            resource_external_id="user-taylor",
            planning_context_key="context::recommendation-contract",
            source_snapshot_id="snapshot::recommendation-contract",
            recommendations=candidates,
        )
        second = service.publish_resource_recommendation_context(
            resource_external_id="user-taylor",
            planning_context_key="context::recommendation-contract",
            source_snapshot_id="snapshot::recommendation-contract",
            recommendations=candidates,
        )

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            sorted(first.to_dict().keys()),
            [
                "actionable_recommendation_count",
                "context_id",
                "freshness_status",
                "planning_context_key",
                "recommendations",
                "resource_external_id",
                "resource_id",
                "source_snapshot_id",
                "state",
                "total_recommendation_count",
            ],
        )
