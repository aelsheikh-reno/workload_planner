import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.planning_engine_service.service import PlanningEngineService
from services.api_gateway_bff.s01_portfolio_contract import (
    build_d01_task_drilldown_contract,
    build_s01_portfolio_contract,
)


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
        requested_at="2026-04-04T12:45:00Z",
        attempt_number=1,
    )
    return planning_engine_service, bundle, execution_result


class S01PortfolioContractTests(unittest.TestCase):
    def test_s01_normal_state_composition(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_portfolio_clean.json",
            "portfolio-clean",
        )

        contract = build_s01_portfolio_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
        )

        self.assertEqual(contract["screen"], {"id": "S01", "label": "Portfolio Swimlane Home"})
        self.assertEqual(contract["viewState"]["screenState"], "ready")
        self.assertEqual(contract["portfolioSummary"]["scheduleState"], "scheduled")
        self.assertEqual(len(contract["dailySwimlanes"]), 1)
        self.assertFalse(contract["indicatorSummary"]["indicatorPresent"])
        self.assertEqual(
            contract["dailySwimlanes"][0]["weeklyRollups"][0]["allocatedHours"],
            8.0,
        )
        self.assertEqual(
            contract["dailySwimlanes"][0]["weeklyRollups"][0]["productiveCapacityHours"],
            40.0,
        )

    def test_s01_empty_no_data_state(self):
        contract = build_s01_portfolio_contract(PlanningEngineService())

        self.assertEqual(contract["viewState"]["screenState"], "no_data")
        self.assertIsNone(contract["portfolioSummary"])
        self.assertEqual(contract["dailySwimlanes"], [])
        self.assertEqual(contract["indicatorSummary"]["indicatorPresent"], False)

    def test_s01_indicator_present_state(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_diagnostics_issue_conditions.json",
            "portfolio-indicators",
        )

        contract = build_s01_portfolio_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
        )

        self.assertEqual(contract["viewState"]["screenState"], "indicator_present")
        self.assertTrue(contract["indicatorSummary"]["indicatorPresent"])
        self.assertGreaterEqual(contract["indicatorSummary"]["riskIndicatorTaskCount"], 1)

    def test_s01_unavailable_state_when_no_runnable_plan_exists(self):
        integration_service = IntegrationService()
        planning_engine_service = PlanningEngineService()
        bundle = integration_service.import_source_plan(
            load_fixture("source_plan_capacity_missing_availability.json")
        )
        planning_engine_service.build_daily_capacity_model(bundle)

        contract = build_s01_portfolio_contract(
            planning_engine_service=planning_engine_service,
            source_snapshot_id=bundle.snapshot.snapshot_id,
        )

        self.assertEqual(contract["viewState"]["screenState"], "unavailable")
        self.assertEqual(contract["unavailableState"]["reason"], "no_runnable_plan")
        self.assertEqual(contract["unavailableState"]["targetScreen"]["id"], "S02")

    def test_daily_to_weekly_rollup_derivation(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_happy_path.json",
            "portfolio-rollup",
        )

        contract = build_s01_portfolio_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
        )

        lane = contract["dailySwimlanes"][0]
        weekly_rollup = lane["weeklyRollups"][0]

        self.assertEqual(weekly_rollup["weekStartDate"], "2026-04-06")
        self.assertEqual(weekly_rollup["dayCount"], 5)
        self.assertEqual(weekly_rollup["allocatedHours"], 24.0)
        self.assertEqual(weekly_rollup["productiveCapacityHours"], 40.0)
        self.assertEqual(weekly_rollup["freeCapacityHours"], 16.0)
        self.assertEqual(weekly_rollup["overloadHours"], 0.0)
        self.assertEqual(weekly_rollup["taskCount"], 2)

    def test_ghost_visibility_presence_in_composed_payload(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_partial_unschedulable.json",
            "portfolio-ghost",
        )

        contract = build_s01_portfolio_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
        )

        ghost_summary = contract["dailySwimlanes"][0]["ghostSummary"]
        self.assertTrue(ghost_summary["hasGhostLoad"])
        self.assertEqual(ghost_summary["partiallyPlacedTaskCount"], 1)
        self.assertEqual(ghost_summary["unschedulableTaskCount"], 1)
        self.assertEqual(ghost_summary["ghostUnscheduledEffortHours"], 16.0)

    def test_overload_and_free_capacity_indicators_are_present(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_happy_path.json",
            "portfolio-capacity-indicators",
        )

        contract = build_s01_portfolio_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
        )

        lane = contract["dailySwimlanes"][0]
        self.assertEqual(lane["laneIndicators"]["overloadedDayCount"], 0)
        self.assertEqual(lane["laneIndicators"]["freeCapacityDayCount"], 2)
        self.assertEqual(contract["indicatorSummary"]["freeCapacitySegmentCount"], 2)

    def test_s01_contract_shape(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_portfolio_clean.json",
            "portfolio-contract",
        )

        contract = build_s01_portfolio_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
        )

        self.assertEqual(
            sorted(contract.keys()),
            [
                "dailySwimlanes",
                "indicatorSummary",
                "portfolioSummary",
                "queryContext",
                "screen",
                "unavailableState",
                "viewState",
            ],
        )
        self.assertEqual(
            sorted(contract["dailySwimlanes"][0].keys()),
            [
                "dailySegments",
                "ghostSummary",
                "laneIndicators",
                "resourceDisplayName",
                "resourceExternalId",
                "resourceId",
                "totalAllocatedHours",
                "totalProductiveCapacityHours",
                "weeklyRollups",
            ],
        )


class D01PortfolioDrillDownTests(unittest.TestCase):
    def test_d01_drill_down_payload_correctness_for_selected_context(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_happy_path.json",
            "drilldown-happy",
        )

        contract = build_d01_task_drilldown_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-ada",
            date="2026-04-08",
        )

        self.assertEqual(contract["drawer"]["id"], "D01")
        self.assertEqual(contract["viewState"]["screenState"], "indicator_present")
        self.assertEqual(contract["segmentSummary"]["taskCount"], 1)
        self.assertEqual(contract["tasks"][0]["taskExternalId"], "task-implement")
        self.assertEqual(contract["tasks"][0]["contextAllocatedHours"], 8.0)
        self.assertTrue(contract["tasks"][0]["movementIndicator"]["present"])

    def test_d01_ready_state_for_clean_selected_context(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_portfolio_clean.json",
            "drilldown-clean",
        )

        contract = build_d01_task_drilldown_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-grace",
            date="2026-04-06",
        )

        self.assertEqual(contract["viewState"]["screenState"], "ready")
        self.assertEqual(contract["segmentSummary"]["taskCount"], 1)
        self.assertEqual(contract["tasks"][0]["taskExternalId"], "task-clean")

    def test_d01_empty_state_for_non_matching_segment_context(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_happy_path.json",
            "drilldown-empty",
        )

        contract = build_d01_task_drilldown_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-ada",
            date="2026-04-10",
        )

        self.assertEqual(contract["viewState"]["screenState"], "empty")
        self.assertEqual(contract["tasks"], [])

    def test_d01_no_data_state(self):
        contract = build_d01_task_drilldown_contract(PlanningEngineService())

        self.assertEqual(contract["viewState"]["screenState"], "no_data")
        self.assertEqual(contract["tasks"], [])
        self.assertIsNone(contract["unavailableState"])

    def test_d01_unavailable_state_when_no_runnable_plan_exists(self):
        integration_service = IntegrationService()
        planning_engine_service = PlanningEngineService()
        bundle = integration_service.import_source_plan(
            load_fixture("source_plan_capacity_missing_availability.json")
        )
        planning_engine_service.build_daily_capacity_model(bundle)

        contract = build_d01_task_drilldown_contract(
            planning_engine_service=planning_engine_service,
            source_snapshot_id=bundle.snapshot.snapshot_id,
            resource_external_id="user-blocked",
            week_start_date="2026-04-06",
        )

        self.assertEqual(contract["viewState"]["screenState"], "unavailable")
        self.assertEqual(contract["unavailableState"]["reason"], "no_runnable_plan")
        self.assertEqual(contract["unavailableState"]["targetScreen"]["id"], "S02")

    def test_d01_excludes_wrong_resource_tasks_from_selected_context(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_happy_path.json",
            "drilldown-wrong-resource",
        )

        contract = build_d01_task_drilldown_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-not-in-lane",
            week_start_date="2026-04-06",
        )

        self.assertEqual(contract["viewState"]["screenState"], "empty")
        self.assertEqual(contract["tasks"], [])

    def test_d01_task_selector_cannot_override_selected_resource_context(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_happy_path.json",
            "drilldown-task-selector-guard",
        )

        contract = build_d01_task_drilldown_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-not-in-lane",
            task_external_id="task-implement",
            week_start_date="2026-04-06",
        )

        self.assertEqual(contract["viewState"]["screenState"], "empty")
        self.assertEqual(contract["tasks"], [])

    def test_d01_contract_shape(self):
        planning_engine_service, _, execution_result = execute_fixture(
            "source_plan_schedule_happy_path.json",
            "drilldown-contract",
        )

        contract = build_d01_task_drilldown_contract(
            planning_engine_service=planning_engine_service,
            planning_run_id=execution_result.execution_record.planning_run_id,
            resource_external_id="user-ada",
            week_start_date="2026-04-06",
        )

        self.assertEqual(
            sorted(contract.keys()),
            [
                "drawer",
                "queryContext",
                "segmentContext",
                "segmentSummary",
                "tasks",
                "unavailableState",
                "viewState",
            ],
        )
        self.assertEqual(
            sorted(contract["tasks"][0].keys()),
            [
                "allocations",
                "contextAllocatedHours",
                "ghostVisible",
                "movementIndicator",
                "planningIssues",
                "projectExternalId",
                "projectId",
                "requestedDueDate",
                "requestedStartDate",
                "requiredEffortHours",
                "riskIndicator",
                "scheduledEffortHours",
                "scheduledEndDate",
                "scheduledStartDate",
                "status",
                "taskExternalId",
                "taskId",
                "taskName",
                "unscheduledEffortHours",
            ],
        )


if __name__ == "__main__":
    unittest.main()
