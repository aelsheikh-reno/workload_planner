import json
import unittest
from pathlib import Path

from services.decision_support_service import DecisionSupportService
from services.integration_service import SourceSetupIssueFact
from services.planning_engine_service import PlanningIssueFact
from services.review_approval_service import ReviewApprovalIssueFact


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def build_source_issue_fact(payload):
    return SourceSetupIssueFact(
        issue_id=payload["issue_id"],
        source_snapshot_id=payload["source_snapshot_id"],
        source_system=payload["source_system"],
        severity=payload["severity"],
        code=payload["code"],
        message=payload["message"],
        entity_type=payload["entity_type"],
        entity_external_id=payload.get("entity_external_id"),
        field=payload.get("field"),
    )


def build_planning_issue_fact(payload):
    return PlanningIssueFact(
        fact_id=payload["fact_id"],
        planning_run_id=payload["planning_run_id"],
        draft_schedule_id=payload["draft_schedule_id"],
        source_snapshot_id=payload["source_snapshot_id"],
        severity=payload["severity"],
        code=payload["code"],
        message=payload["message"],
        entity_type=payload["entity_type"],
        entity_id=payload["entity_id"],
        entity_external_id=payload["entity_external_id"],
    )


def build_review_issue_fact(payload):
    return ReviewApprovalIssueFact(
        fact_id=payload["fact_id"],
        emitted_by_service=payload["emitted_by_service"],
        context_scope=payload["context_scope"],
        fact_type=payload["fact_type"],
        review_context_id=payload["review_context_id"],
        planning_run_id=payload["planning_run_id"],
        source_snapshot_id=payload["source_snapshot_id"],
        approved_plan_id=payload["approved_plan_id"],
        activation_id=payload.get("activation_id"),
        severity=payload["severity"],
        code=payload["code"],
        message=payload["message"],
        entity_type=payload["entity_type"],
        entity_id=payload["entity_id"],
        entity_external_id=payload.get("entity_external_id"),
        related_delta_ids=list(payload["related_delta_ids"]),
        related_connected_set_id=payload.get("related_connected_set_id"),
    )


class DecisionSupportWarningTrustInterpretationTests(unittest.TestCase):
    def setUp(self):
        self.service = DecisionSupportService()

    def _refresh(self, fixture_name):
        payload = load_fixture(fixture_name)
        return self.service.refresh_warning_trust_interpretation(
            screen_id=payload["screen_id"],
            planning_context_key=payload.get("planning_context_key"),
            source_snapshot_id=payload.get("source_snapshot_id"),
            source_issue_facts=[
                build_source_issue_fact(issue)
                for issue in payload.get("source_issue_facts", [])
            ],
            planning_issue_facts=[
                build_planning_issue_fact(issue)
                for issue in payload.get("planning_issue_facts", [])
            ],
            review_issue_facts=[
                build_review_issue_fact(issue)
                for issue in payload.get("review_issue_facts", [])
            ],
        )

    def test_source_setup_issue_fact_becomes_setup_warning(self):
        state = self._refresh("decision_support_source_setup_warning.json")
        signals_by_code = {signal.code: signal for signal in state.signals}

        self.assertEqual(state.screen_id, "S02")
        self.assertEqual(state.blocking_signal_count, 1)
        self.assertEqual(state.advisory_signal_count, 1)
        self.assertEqual(state.warning_signal_count, 2)
        self.assertEqual(state.trust_signal_count, 0)
        self.assertEqual(
            signals_by_code["missing_task_name"].interpretation_category,
            "setup_blocker",
        )
        self.assertTrue(signals_by_code["missing_task_name"].blocking)
        self.assertFalse(signals_by_code["missing_task_name"].advisory)
        self.assertEqual(
            signals_by_code["missing_task_name"].source_issue_service,
            "Integration Service",
        )
        self.assertEqual(
            signals_by_code["missing_date_window"].interpretation_category,
            "setup_warning",
        )
        self.assertTrue(signals_by_code["missing_date_window"].advisory)

    def test_planning_issue_fact_becomes_advisory_or_trust_limited(self):
        state = self._refresh("decision_support_planning_warning_set.json")
        signals_by_code = {signal.code: signal for signal in state.signals}

        self.assertEqual(state.screen_id, "S05")
        self.assertEqual(state.blocking_signal_count, 0)
        self.assertEqual(state.advisory_signal_count, 2)
        self.assertEqual(state.warning_signal_count, 1)
        self.assertEqual(state.trust_signal_count, 1)
        self.assertEqual(state.trust_limited_signal_count, 1)
        self.assertEqual(
            signals_by_code["draft_unschedulable"].interpretation_category,
            "advisory_warning",
        )
        self.assertEqual(signals_by_code["draft_unschedulable"].signal_type, "warning")
        self.assertEqual(
            signals_by_code["criticality_zero_slack"].interpretation_category,
            "trust_limited",
        )
        self.assertEqual(
            signals_by_code["criticality_zero_slack"].signal_type,
            "trust",
        )

    def test_approval_issue_fact_becomes_review_or_activation_blocker(self):
        state = self._refresh("decision_support_review_blockers.json")
        signals_by_code = {signal.code: signal for signal in state.signals}

        self.assertEqual(state.screen_id, "S04")
        self.assertEqual(state.blocking_signal_count, 3)
        self.assertEqual(state.advisory_signal_count, 0)
        self.assertTrue(
            all(signal.source_issue_service == "Review & Approval Service" for signal in state.signals)
        )
        self.assertEqual(
            signals_by_code["dependency_safe_approval_blocked"].interpretation_category,
            "review_blocker",
        )
        self.assertEqual(
            signals_by_code["connected_set_required"].interpretation_category,
            "review_blocker",
        )
        self.assertEqual(
            signals_by_code["activation_requires_current_approved_plan"].interpretation_category,
            "activation_blocker",
        )

    def test_mixed_multi_source_issue_fact_interpretation(self):
        state = self._refresh("decision_support_mixed_warning_set.json")
        signal_services = {signal.source_issue_service for signal in state.signals}
        signal_codes = [signal.code for signal in state.signals]

        self.assertEqual(state.screen_id, "S05")
        self.assertEqual(state.total_input_fact_count, 4)
        self.assertEqual(state.interpreted_signal_count, 3)
        self.assertEqual(
            signal_services,
            {
                "Integration Service",
                "Planning Engine Service",
                "Review & Approval Service",
            },
        )
        self.assertNotIn("activation_completed", signal_codes)

    def test_blocking_vs_advisory_classification_is_preserved(self):
        state = self._refresh("decision_support_mixed_warning_set.json")

        self.assertEqual(state.active_signal_count, 3)
        self.assertEqual(state.blocking_signal_count, 1)
        self.assertEqual(state.advisory_signal_count, 2)
        self.assertEqual(state.trust_limited_signal_count, 1)

    def test_ownership_boundary_assertions(self):
        state = self._refresh("decision_support_mixed_warning_set.json")
        payload = state.to_dict()

        self.assertEqual(payload["lifecycle_state"], "current")
        self.assertNotIn("recommendations", payload)
        self.assertNotIn("source_readiness", payload)
        self.assertNotIn("accepted_changes", payload)
        self.assertTrue(
            all(signal["signal_id"] != signal["source_fact_id"] for signal in payload["signals"])
        )
        self.assertTrue(
            all(
                signal["source_issue_service"]
                in {
                    "Integration Service",
                    "Planning Engine Service",
                    "Review & Approval Service",
                }
                for signal in payload["signals"]
            )
        )

    def test_deterministic_warning_trust_output(self):
        first = self._refresh("decision_support_mixed_warning_set.json")
        second = self._refresh("decision_support_mixed_warning_set.json")

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.interpretation_id, second.interpretation_id)

    def test_contract_shape_assertions(self):
        state = self._refresh("decision_support_mixed_warning_set.json")
        contract = state.to_dict()

        self.assertEqual(
            sorted(contract.keys()),
            [
                "active_signal_count",
                "advisory_signal_count",
                "blocking_signal_count",
                "interpretation_id",
                "interpreted_signal_count",
                "lifecycle_state",
                "planning_context_key",
                "screen_id",
                "signals",
                "source_snapshot_id",
                "total_input_fact_count",
                "trust_limited_signal_count",
                "trust_signal_count",
                "warning_signal_count",
            ],
        )
        self.assertEqual(
            sorted(contract["signals"][0].keys()),
            [
                "advisory",
                "blocking",
                "code",
                "entity_external_id",
                "entity_id",
                "entity_type",
                "interpretation_category",
                "lifecycle_state",
                "message",
                "planning_context_key",
                "screen_id",
                "severity",
                "signal_id",
                "signal_type",
                "source_fact_id",
                "source_fact_severity",
                "source_fact_type",
                "source_issue_service",
                "source_snapshot_id",
            ],
        )

    def test_refresh_persists_state_for_screen_retrieval(self):
        state = self._refresh("decision_support_review_blockers.json")
        persisted = self.service.get_screen_warning_trust_state(
            screen_id="S04",
            planning_context_key="portfolio-review-alpha",
            source_snapshot_id="source-snapshot-warning-01",
        )

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.to_dict(), state.to_dict())


if __name__ == "__main__":
    unittest.main()
