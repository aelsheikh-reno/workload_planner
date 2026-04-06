import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.planning_engine_service import PlanningEngineService


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class PlanningEngineDraftSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.integration_service = IntegrationService()
        self.planning_engine_service = PlanningEngineService()

    def test_happy_path_draft_scheduling(self):
        bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_schedule_happy_path.json")
        )
        capacity_result = self.planning_engine_service.build_daily_capacity_model(bundle)

        result = self.planning_engine_service.build_draft_schedule(
            bundle,
            capacity_result=capacity_result,
            planning_run_id="planning-run-happy",
        )

        self.assertEqual(result.schedule_state, "scheduled")
        self.assertEqual(len(result.task_schedules), 2)
        self.assertEqual(len(result.allocation_outputs), 3)
        self.assertEqual(result.schedule_issues, [])

    def test_dependency_respecting_placement(self):
        bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_schedule_happy_path.json")
        )
        result = self.planning_engine_service.build_draft_schedule(
            bundle,
            capacity_result=self.planning_engine_service.build_daily_capacity_model(bundle),
            planning_run_id="planning-run-dependency",
        )
        tasks_by_external_id = {
            task.task_external_id: task for task in result.task_schedules
        }

        self.assertEqual(tasks_by_external_id["task-design"].scheduled_end_date, "2026-04-07")
        self.assertEqual(
            tasks_by_external_id["task-implement"].scheduled_start_date,
            "2026-04-08",
        )

    def test_capacity_constrained_scheduling(self):
        bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_schedule_capacity_constrained.json")
        )
        result = self.planning_engine_service.build_draft_schedule(
            bundle,
            capacity_result=self.planning_engine_service.build_daily_capacity_model(bundle),
            planning_run_id="planning-run-constrained",
        )
        tasks_by_external_id = {
            task.task_external_id: task for task in result.task_schedules
        }

        self.assertEqual(result.schedule_state, "scheduled")
        self.assertEqual(tasks_by_external_id["task-alpha"].scheduled_start_date, "2026-04-06")
        self.assertEqual(tasks_by_external_id["task-alpha"].scheduled_end_date, "2026-04-07")
        self.assertEqual(tasks_by_external_id["task-beta"].scheduled_start_date, "2026-04-08")
        self.assertEqual(tasks_by_external_id["task-beta"].scheduled_end_date, "2026-04-09")

    def test_unschedulable_and_partially_schedulable_handling(self):
        bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_schedule_partial_unschedulable.json")
        )
        result = self.planning_engine_service.build_draft_schedule(
            bundle,
            capacity_result=self.planning_engine_service.build_daily_capacity_model(bundle),
            planning_run_id="planning-run-partial",
        )
        tasks_by_external_id = {
            task.task_external_id: task for task in result.task_schedules
        }

        self.assertEqual(result.schedule_state, "partially_schedulable")
        self.assertEqual(tasks_by_external_id["task-foundation"].status, "partially_scheduled")
        self.assertEqual(tasks_by_external_id["task-foundation"].scheduled_effort_hours, 24.0)
        self.assertEqual(tasks_by_external_id["task-foundation"].unscheduled_effort_hours, 8.0)
        self.assertEqual(tasks_by_external_id["task-qa"].status, "unschedulable")
        self.assertIn(
            "task_partially_scheduled",
            {issue.code for issue in result.schedule_issues},
        )
        self.assertIn(
            "predecessor_not_fully_scheduled",
            {issue.code for issue in result.schedule_issues},
        )

    def test_deterministic_draft_schedule_outputs(self):
        first_bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_schedule_happy_path.json")
        )
        second_bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_schedule_happy_path.json")
        )

        first_result = self.planning_engine_service.build_draft_schedule(
            first_bundle,
            capacity_result=self.planning_engine_service.build_daily_capacity_model(
                first_bundle
            ),
            planning_run_id="planning-run-deterministic",
        )
        second_result = self.planning_engine_service.build_draft_schedule(
            second_bundle,
            capacity_result=self.planning_engine_service.build_daily_capacity_model(
                second_bundle
            ),
            planning_run_id="planning-run-deterministic",
        )

        self.assertEqual(first_result.to_dict(), second_result.to_dict())
        self.assertEqual(first_result.draft_schedule_id, second_result.draft_schedule_id)

    def test_draft_schedule_contract_shape(self):
        bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_schedule_happy_path.json")
        )
        result = self.planning_engine_service.build_draft_schedule(
            bundle,
            capacity_result=self.planning_engine_service.build_daily_capacity_model(bundle),
            planning_run_id="planning-run-contract",
        )
        contract = result.to_dict()

        self.assertEqual(
            sorted(contract.keys()),
            [
                "allocation_outputs",
                "capacity_snapshot_id",
                "draft_schedule_id",
                "planning_run_id",
                "schedule_issues",
                "schedule_state",
                "source_artifact_id",
                "source_snapshot_id",
                "task_schedules",
            ],
        )
        self.assertEqual(
            sorted(contract["task_schedules"][0].keys()),
            [
                "assigned_resource_ids",
                "draft_schedule_id",
                "parent_task_id",
                "planning_run_id",
                "predecessor_task_ids",
                "project_external_id",
                "project_id",
                "requested_due_date",
                "requested_start_date",
                "required_effort_hours",
                "scheduled_effort_hours",
                "scheduled_end_date",
                "scheduled_start_date",
                "source_snapshot_id",
                "status",
                "task_external_id",
                "task_id",
                "task_name",
                "unscheduled_effort_hours",
            ],
        )
        self.assertEqual(
            sorted(contract["allocation_outputs"][0].keys()),
            [
                "allocated_hours",
                "allocation_id",
                "date",
                "draft_schedule_id",
                "planning_run_id",
                "resource_external_id",
                "resource_id",
                "source_snapshot_id",
                "task_external_id",
                "task_id",
            ],
        )


if __name__ == "__main__":
    unittest.main()
