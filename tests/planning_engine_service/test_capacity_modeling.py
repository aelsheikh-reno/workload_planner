import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.planning_engine_service import PlanningEngineService


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class PlanningEngineCapacityModelingTests(unittest.TestCase):
    def setUp(self):
        self.integration_service = IntegrationService()
        self.planning_engine_service = PlanningEngineService()

    def test_daily_capacity_output_generation(self):
        bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_capacity_fte.json")
        )

        result = self.planning_engine_service.build_daily_capacity_model(bundle)

        self.assertEqual(result.input_readiness.state, "ready")
        self.assertTrue(result.input_readiness.runnable)
        self.assertEqual(len(result.resource_summaries), 1)
        self.assertEqual(len(result.daily_capacity_outputs), 5)
        self.assertEqual(
            [output.productive_capacity_hours for output in result.daily_capacity_outputs],
            [8.0, 8.0, 8.0, 8.0, 8.0],
        )
        self.assertEqual(
            result.resource_summaries[0].total_productive_capacity_hours,
            40.0,
        )
        self.assertEqual(result.resource_summaries[0].assigned_effort_hours, 40.0)

    def test_fte_vs_part_time_behavior(self):
        fte_bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_capacity_fte.json")
        )
        part_time_bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_capacity_part_time.json")
        )

        fte_result = self.planning_engine_service.build_daily_capacity_model(fte_bundle)
        part_time_result = self.planning_engine_service.build_daily_capacity_model(
            part_time_bundle
        )

        self.assertEqual(
            [output.productive_capacity_hours for output in fte_result.daily_capacity_outputs],
            [8.0, 8.0, 8.0, 8.0, 8.0],
        )
        self.assertEqual(
            [
                output.productive_capacity_hours
                for output in part_time_result.daily_capacity_outputs
            ],
            [4.0, 4.0, 4.0, 4.0, 4.0],
        )

    def test_exception_handling(self):
        bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_capacity_exception.json")
        )

        result = self.planning_engine_service.build_daily_capacity_model(bundle)
        outputs_by_date = {
            output.date: output for output in result.daily_capacity_outputs
        }

        self.assertEqual(outputs_by_date["2026-04-08"].productive_capacity_hours, 2.0)
        self.assertEqual(outputs_by_date["2026-04-08"].exception_reason, "training")
        self.assertEqual(
            result.resource_summaries[0].total_productive_capacity_hours,
            34.0,
        )

    def test_missing_availability_input_behavior(self):
        bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_capacity_missing_availability.json")
        )

        result = self.planning_engine_service.build_daily_capacity_model(bundle)

        self.assertEqual(result.input_readiness.state, "blocked")
        self.assertFalse(result.input_readiness.runnable)
        self.assertEqual(result.daily_capacity_outputs, [])
        self.assertIn(
            "missing_availability_ratio",
            {issue.code for issue in result.input_issues},
        )

    def test_deterministic_output_for_identical_inputs(self):
        first_bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_capacity_fte.json")
        )
        second_bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_capacity_fte.json")
        )

        first_result = self.planning_engine_service.build_daily_capacity_model(first_bundle)
        second_result = self.planning_engine_service.build_daily_capacity_model(
            second_bundle
        )

        self.assertEqual(first_result.to_dict(), second_result.to_dict())
        self.assertEqual(
            first_result.capacity_snapshot_id, second_result.capacity_snapshot_id
        )

    def test_capacity_output_contract_shape(self):
        bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_capacity_fte.json")
        )

        result = self.planning_engine_service.build_daily_capacity_model(bundle)
        contract = result.to_dict()

        self.assertEqual(
            sorted(contract.keys()),
            [
                "capacity_snapshot_id",
                "daily_capacity_outputs",
                "input_issues",
                "input_readiness",
                "resource_summaries",
                "source_artifact_id",
                "source_snapshot_id",
            ],
        )
        self.assertEqual(
            sorted(contract["input_readiness"].keys()),
            [
                "advisory_issue_count",
                "blocking_issue_count",
                "runnable",
                "state",
                "total_issue_count",
            ],
        )
        self.assertEqual(
            sorted(contract["resource_summaries"][0].keys()),
            [
                "assigned_effort_hours",
                "assignment_input_count",
                "days_modeled",
                "resource_display_name",
                "resource_external_id",
                "resource_id",
                "total_productive_capacity_hours",
                "window_end_date",
                "window_start_date",
            ],
        )
        self.assertEqual(
            sorted(contract["daily_capacity_outputs"][0].keys()),
            [
                "active_assignment_count",
                "availability_ratio",
                "calendar_capacity_hours",
                "date",
                "exception_reason",
                "output_id",
                "productive_capacity_hours",
                "resource_display_name",
                "resource_external_id",
                "resource_id",
                "source_snapshot_id",
                "working_day",
            ],
        )


if __name__ == "__main__":
    unittest.main()
