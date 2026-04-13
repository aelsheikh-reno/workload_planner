import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.planning_engine_service import PlanningEngineService


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class PlanningEngineDiagnosticsFactTests(unittest.TestCase):
    def setUp(self):
        self.integration_service = IntegrationService()
        self.planning_engine_service = PlanningEngineService()

    def _build_diagnostics(self, fixture_name, planning_run_id):
        bundle = self.integration_service.import_source_plan(load_fixture(fixture_name))
        capacity_result = self.planning_engine_service.build_daily_capacity_model(bundle)
        draft_schedule_result = self.planning_engine_service.build_draft_schedule(
            bundle=bundle,
            capacity_result=capacity_result,
            planning_run_id=planning_run_id,
        )
        return self.planning_engine_service.build_planning_diagnostics(
            bundle=bundle,
            draft_schedule_result=draft_schedule_result,
            capacity_result=capacity_result,
        )

    def test_variance_fact_generation_for_no_variance_conditions(self):
        diagnostics = self._build_diagnostics(
            "source_plan_diagnostics_no_variance.json",
            "planning-run-no-variance",
        )

        self.assertEqual(diagnostics.comparison_context, "source_baseline_only")
        self.assertFalse(diagnostics.approved_comparison_available)
        self.assertEqual(len(diagnostics.variance_facts), 1)
        variance_fact = diagnostics.variance_facts[0]
        self.assertEqual(variance_fact.start_variance_days, 0)
        self.assertEqual(variance_fact.finish_variance_days, 0)
        self.assertFalse(variance_fact.slippage_detected)

    def test_variance_fact_generation_for_slippage_conditions(self):
        diagnostics = self._build_diagnostics(
            "source_plan_diagnostics_slippage.json",
            "planning-run-slippage",
        )
        variance_facts_by_external_id = {
            fact.task_external_id: fact for fact in diagnostics.variance_facts
        }

        self.assertEqual(
            variance_facts_by_external_id["task-successor"].start_variance_days,
            1,
        )
        self.assertEqual(
            variance_facts_by_external_id["task-successor"].finish_variance_days,
            0,
        )
        self.assertTrue(
            variance_facts_by_external_id["task-successor"].slippage_detected
        )

    def test_criticality_fact_generation_for_dependency_pressure(self):
        diagnostics = self._build_diagnostics(
            "source_plan_diagnostics_dependency_pressure.json",
            "planning-run-criticality",
        )
        criticality_by_external_id = {
            fact.task_external_id: fact for fact in diagnostics.criticality_facts
        }

        self.assertTrue(criticality_by_external_id["task-a"].critical)
        self.assertTrue(criticality_by_external_id["task-b"].critical)
        self.assertTrue(criticality_by_external_id["task-c"].critical)
        self.assertEqual(criticality_by_external_id["task-a"].downstream_dependency_count, 2)
        self.assertEqual(criticality_by_external_id["task-b"].dependency_chain_depth, 1)
        self.assertTrue(criticality_by_external_id["task-c"].zero_slack)

    def test_planning_issue_fact_generation(self):
        diagnostics = self._build_diagnostics(
            "source_plan_diagnostics_issue_conditions.json",
            "planning-run-issues",
        )
        issue_codes = {fact.code for fact in diagnostics.planning_issue_facts}

        self.assertIn("draft_partially_schedulable", issue_codes)
        # After C6 fix: successors of partially-scheduled predecessors are no
        # longer blocked. task-follow-on now schedules using foundation's actual
        # end date, so "draft_unschedulable" is no longer generated.
        self.assertNotIn("draft_unschedulable", issue_codes)
        self.assertIn("dependency_chain_pressure", issue_codes)
        self.assertIn("criticality_zero_slack", issue_codes)

    def test_ownership_boundary_assertions(self):
        diagnostics = self._build_diagnostics(
            "source_plan_diagnostics_issue_conditions.json",
            "planning-run-boundary",
        )
        issue_codes = {fact.code for fact in diagnostics.planning_issue_facts}

        self.assertTrue(
            all(
                not any(
                    marker in code
                    for marker in (
                        "source_",
                        "approval",
                        "activation",
                        "warning",
                        "trust",
                        "recommend",
                    )
                )
                for code in issue_codes
            )
        )
        self.assertEqual(diagnostics.comparison_context, "source_baseline_only")
        self.assertFalse(diagnostics.approved_comparison_available)

    def test_deterministic_diagnostics_output(self):
        first = self._build_diagnostics(
            "source_plan_diagnostics_slippage.json",
            "planning-run-diagnostics-deterministic",
        )
        second = self._build_diagnostics(
            "source_plan_diagnostics_slippage.json",
            "planning-run-diagnostics-deterministic",
        )

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.diagnostics_id, second.diagnostics_id)

    def test_diagnostics_contract_shape(self):
        diagnostics = self._build_diagnostics(
            "source_plan_diagnostics_slippage.json",
            "planning-run-diagnostics-contract",
        )
        contract = diagnostics.to_dict()

        self.assertEqual(
            sorted(contract.keys()),
            [
                "approved_comparison_available",
                "capacity_snapshot_id",
                "comparison_context",
                "criticality_facts",
                "diagnostics_id",
                "draft_schedule_id",
                "planning_issue_facts",
                "planning_run_id",
                "source_artifact_id",
                "source_snapshot_id",
                "variance_facts",
            ],
        )
        self.assertEqual(
            sorted(contract["variance_facts"][0].keys()),
            [
                "baseline_due_date",
                "baseline_start_date",
                "draft_schedule_id",
                "fact_id",
                "finish_variance_days",
                "planning_run_id",
                "scheduled_end_date",
                "scheduled_start_date",
                "slippage_detected",
                "source_snapshot_id",
                "start_variance_days",
                "task_external_id",
                "task_id",
                "task_name",
                "unscheduled_effort_hours",
            ],
        )
        self.assertEqual(
            sorted(contract["criticality_facts"][0].keys()),
            [
                "blocked_by_unscheduled_predecessor",
                "critical",
                "dependency_chain_depth",
                "direct_predecessor_count",
                "direct_successor_count",
                "downstream_dependency_count",
                "draft_schedule_id",
                "fact_id",
                "planning_run_id",
                "slack_days",
                "source_snapshot_id",
                "task_external_id",
                "task_id",
                "task_name",
                "zero_slack",
            ],
        )
        self.assertEqual(
            sorted(contract["planning_issue_facts"][0].keys()),
            [
                "code",
                "draft_schedule_id",
                "entity_external_id",
                "entity_id",
                "entity_type",
                "fact_id",
                "message",
                "planning_run_id",
                "severity",
                "source_snapshot_id",
            ],
        )


if __name__ == "__main__":
    unittest.main()
