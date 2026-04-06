import json
import unittest
from pathlib import Path

from services.review_approval_service import (
    ACTIVATION_STATUS_ACTIVATED,
    ACTIVATION_STATUS_BLOCKED,
    ACTIVATION_STATUS_NOT_REQUESTED,
    ActivationBusinessRuleBlocker,
    ActivationOutcome,
    ActivationState,
    ReviewApprovalService,
    ReviewContextState,
    ReviewableDeltaItem,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def build_review_context_state(payload):
    return ReviewContextState(
        review_context_id=payload["review_context_id"],
        planning_run_id=payload["planning_run_id"],
        source_snapshot_id=payload["source_snapshot_id"],
        approved_plan_id=payload["approved_plan_id"],
        delta_items=[
            ReviewableDeltaItem(
                delta_id=item["delta_id"],
                entity_type=item.get("entity_type", "task"),
                entity_id=item.get("entity_id", item["task_id"]),
                entity_external_id=item.get(
                    "entity_external_id", item["task_external_id"]
                ),
                entity_name=item.get("entity_name", item["task_name"]),
                dependency_delta_ids=list(item["dependency_delta_ids"]),
                connected_set_id=item.get("connected_set_id"),
                selected_for_acceptance=item["selected_for_acceptance"],
                task_id=item["task_id"],
                task_external_id=item["task_external_id"],
                task_name=item["task_name"],
            )
            for item in payload["delta_items"]
        ],
    )


def build_activation_state(payload):
    if payload is None:
        return None
    blockers = [
        ActivationBusinessRuleBlocker(
            rule_id=blocker["rule_id"],
            code=blocker["code"],
            message=blocker["message"],
            entity_type=blocker["entity_type"],
            entity_id=blocker["entity_id"],
            entity_external_id=blocker.get("entity_external_id"),
        )
        for blocker in payload.get("business_rule_blockers", [])
    ]
    outcome_payload = payload.get("outcome")
    outcome = None
    if outcome_payload is not None:
        outcome = ActivationOutcome(
            code=outcome_payload["code"],
            message=outcome_payload["message"],
            activated_delta_ids=list(outcome_payload["activated_delta_ids"]),
        )
    return ActivationState(
        activation_id=payload["activation_id"],
        status=payload["status"],
        business_rule_blockers=blockers,
        outcome=outcome,
    )


class ReviewApprovalIssueFactEmissionTests(unittest.TestCase):
    def setUp(self):
        self.service = ReviewApprovalService()

    def _emit(self, fixture_name):
        payload = load_fixture(fixture_name)
        review_context = build_review_context_state(payload["review_context"])
        activation_state = build_activation_state(payload.get("activation_state"))
        return self.service.emit_issue_facts(
            review_context=review_context,
            activation_state=activation_state,
        )

    def test_dependency_safe_blocker_fact_emission(self):
        emission = self._emit("review_approval_blocked_isolated_acceptance.json")
        issue_codes = {fact.code for fact in emission.issue_facts}

        self.assertIn("dependency_safe_approval_blocked", issue_codes)
        dependency_fact = next(
            fact
            for fact in emission.issue_facts
            if fact.code == "dependency_safe_approval_blocked"
        )
        self.assertEqual(dependency_fact.context_scope, "review_context")
        self.assertEqual(dependency_fact.fact_type, "dependency_safe_blocker")
        self.assertEqual(
            dependency_fact.related_delta_ids,
            ["delta-foundation", "delta-successor"],
        )
        self.assertEqual(emission.blocking_fact_count, 2)

    def test_connected_set_required_fact_emission(self):
        emission = self._emit("review_approval_connected_set_required.json")

        self.assertEqual(emission.total_fact_count, 1)
        issue_fact = emission.issue_facts[0]
        self.assertEqual(issue_fact.code, "connected_set_required")
        self.assertEqual(issue_fact.fact_type, "connected_set_required")
        self.assertEqual(issue_fact.entity_type, "connected_change_set")
        self.assertEqual(issue_fact.related_connected_set_id, "connected-set-core")
        self.assertEqual(issue_fact.related_delta_ids, ["delta-alpha", "delta-beta"])

    def test_activation_blocker_fact_emission(self):
        emission = self._emit("review_approval_activation_blocked.json")
        issue_fact = emission.issue_facts[0]

        self.assertEqual(issue_fact.context_scope, "activation")
        self.assertEqual(issue_fact.fact_type, "activation_blocker")
        self.assertEqual(issue_fact.code, "activation_requires_current_approved_plan")
        self.assertEqual(issue_fact.activation_id, "activation-ctx-blocked")
        self.assertEqual(emission.blocking_fact_count, 1)
        self.assertEqual(emission.informational_fact_count, 0)

    def test_non_blocked_review_state_emits_no_blocker_fact(self):
        emission = self._emit("review_approval_clean_review_context.json")

        self.assertEqual(emission.total_fact_count, 0)
        self.assertEqual(emission.blocking_fact_count, 0)
        self.assertEqual(emission.informational_fact_count, 0)
        self.assertEqual(emission.issue_facts, [])

    def test_successful_activation_emits_activation_outcome_fact(self):
        emission = self._emit("review_approval_activation_succeeded.json")

        self.assertEqual(emission.blocking_fact_count, 0)
        self.assertEqual(emission.informational_fact_count, 1)
        self.assertEqual(emission.issue_facts[0].code, "activation_completed")
        self.assertEqual(emission.issue_facts[0].fact_type, "activation_outcome")
        self.assertEqual(
            emission.issue_facts[0].related_delta_ids,
            ["delta-foundation", "delta-successor"],
        )

    def test_deterministic_issue_fact_emission(self):
        first = self._emit("review_approval_activation_blocked.json")
        second = self._emit("review_approval_activation_blocked.json")

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.emission_id, second.emission_id)

    def test_issue_fact_contract_shape(self):
        emission = self._emit("review_approval_activation_succeeded.json")
        contract = emission.to_dict()

        self.assertEqual(
            sorted(contract.keys()),
            [
                "activation_id",
                "approved_plan_id",
                "blocking_fact_count",
                "emission_id",
                "informational_fact_count",
                "issue_facts",
                "planning_run_id",
                "review_context_id",
                "source_snapshot_id",
                "total_fact_count",
            ],
        )
        self.assertEqual(
            sorted(contract["issue_facts"][0].keys()),
            [
                "activation_id",
                "approved_plan_id",
                "code",
                "context_scope",
                "emitted_by_service",
                "entity_external_id",
                "entity_id",
                "entity_type",
                "fact_id",
                "fact_type",
                "message",
                "planning_run_id",
                "related_connected_set_id",
                "related_delta_ids",
                "review_context_id",
                "severity",
                "source_snapshot_id",
            ],
        )

    def test_ownership_boundary_assertions(self):
        emission = self._emit("review_approval_activation_blocked.json")
        payload = emission.to_dict()

        self.assertTrue(
            all(
                fact["emitted_by_service"] == "Review & Approval Service"
                for fact in payload["issue_facts"]
            )
        )
        self.assertTrue(
            all(
                not any(
                    marker in fact["code"]
                    for marker in ("warning", "trust", "recommend", "source_setup")
                )
                for fact in payload["issue_facts"]
            )
        )
        self.assertNotIn("warning_state", payload)
        self.assertNotIn("trust_state", payload)

    def test_repository_gets_latest_emission_by_activation_id(self):
        emission = self._emit("review_approval_activation_succeeded.json")
        persisted = self.service.get_issue_fact_emission(
            activation_id="activation-ctx-success"
        )

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.to_dict(), emission.to_dict())

    def test_emission_id_changes_when_fact_set_changes_with_same_context(self):
        payload = load_fixture("review_approval_activation_blocked.json")
        review_context = build_review_context_state(payload["review_context"])
        first_activation_state = ActivationState(
            activation_id="activation-ctx-shared",
            status=ACTIVATION_STATUS_BLOCKED,
            business_rule_blockers=[
                ActivationBusinessRuleBlocker(
                    rule_id="rule-approved-plan-pointer",
                    code="activation_requires_current_approved_plan",
                    message="Activation requires a current approved operating plan pointer before applying accepted changes.",
                    entity_type="approved_plan",
                    entity_id=review_context.approved_plan_id,
                    entity_external_id=None,
                )
            ],
            outcome=None,
        )
        second_activation_state = ActivationState(
            activation_id="activation-ctx-shared",
            status=ACTIVATION_STATUS_BLOCKED,
            business_rule_blockers=[
                ActivationBusinessRuleBlocker(
                    rule_id="rule-activation-window",
                    code="activation_window_closed",
                    message="Activation is blocked because the approved change window is closed.",
                    entity_type="activation_window",
                    entity_id="window-q2",
                    entity_external_id=None,
                )
            ],
            outcome=None,
        )

        first = self.service.emit_issue_facts(
            review_context=review_context,
            activation_state=first_activation_state,
        )
        second = self.service.emit_issue_facts(
            review_context=review_context,
            activation_state=second_activation_state,
        )

        self.assertEqual(first.total_fact_count, 1)
        self.assertEqual(second.total_fact_count, 1)
        self.assertNotEqual(first.issue_facts[0].code, second.issue_facts[0].code)
        self.assertNotEqual(first.emission_id, second.emission_id)

    def test_fixture_activation_statuses_cover_expected_contract_values(self):
        statuses = {
            build_activation_state(load_fixture("review_approval_activation_blocked.json")["activation_state"]).status,
            build_activation_state(load_fixture("review_approval_activation_succeeded.json")["activation_state"]).status,
            build_activation_state(
                {
                    "activation_id": "activation-ctx-none",
                    "status": ACTIVATION_STATUS_NOT_REQUESTED,
                    "business_rule_blockers": [],
                    "outcome": None,
                }
            ).status,
        }

        self.assertEqual(
            statuses,
            {
                ACTIVATION_STATUS_BLOCKED,
                ACTIVATION_STATUS_ACTIVATED,
                ACTIVATION_STATUS_NOT_REQUESTED,
            },
        )


if __name__ == "__main__":
    unittest.main()
