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
        # Successor of a partially_scheduled predecessor should NOT be blocked:
        # it uses the predecessor's actual scheduled_end_date as its anchor.
        # task-foundation ends Apr 8 (24h placed Mon-Wed). task-qa starts Apr 9 (Thu).
        self.assertEqual(tasks_by_external_id["task-qa"].status, "scheduled")
        self.assertIn(
            "task_partially_scheduled",
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


class PartialPredecessorTests(unittest.TestCase):
    """Verify that partially-scheduled predecessors don't block successors."""

    def test_partial_predecessor_does_not_block_successor(self):
        """Predecessor is partially_scheduled (not enough capacity to fully place).
        Successor should use predecessor's actual end date and schedule normally."""
        bundle = IntegrationService().import_source_plan(
            load_fixture("source_plan_schedule_partial_unschedulable.json")
        )
        engine = PlanningEngineService()
        result = engine.build_draft_schedule(
            bundle,
            capacity_result=engine.build_daily_capacity_model(bundle),
            planning_run_id="run-partial-pred",
        )
        schedules = {ts.task_external_id: ts for ts in result.task_schedules}

        # Foundation: 32h in 3-day window (24h cap) → partially_scheduled
        self.assertEqual(schedules["task-foundation"].status, "partially_scheduled")
        # QA: depends on foundation (FS). Foundation ends Apr 8 → QA starts Apr 9.
        # QA has 8h effort, Apr 9-10 has 16h capacity → scheduled
        self.assertEqual(schedules["task-qa"].status, "scheduled")
        self.assertEqual(schedules["task-qa"].scheduled_start_date, "2026-04-09")


class AllocationRoundingCapTests(unittest.TestCase):
    """Verify that rounding up to 0.5h never causes cumulative over-allocation."""

    def _make_bundle(self, tasks, dependencies=None, resources=None, assignments=None, exceptions=None):
        from services.integration_service.contracts import (
            NormalizedSourceBundle,
            SourceArtifact,
            SourceReadiness,
            SourceSnapshot,
        )
        artifact = SourceArtifact(
            artifact_id="art-001", external_artifact_id="art-001",
            source_system="test", captured_at="2026-04-09",
            payload_digest="abc", raw_payload={},
        )
        snapshot = SourceSnapshot(
            snapshot_id="snap-001", artifact_id="art-001",
            source_system="test", captured_at="2026-04-09",
            project_count=1, task_count=len(tasks),
            dependency_count=len(dependencies or []),
            assignment_count=len(assignments or []), issue_count=0,
        )
        readiness = SourceReadiness(
            state="ready", runnable=True,
            blocking_issue_count=0, advisory_issue_count=0, total_issue_count=0,
        )
        return NormalizedSourceBundle(
            artifact=artifact, snapshot=snapshot,
            project_mappings=[], task_mappings=[], resource_mappings=[],
            tasks=tasks, dependencies=dependencies or [],
            resource_assignments=assignments or [],
            resources=resources or [],
            resource_exceptions=exceptions or [],
            issue_facts=[], source_readiness=readiness,
        )

    def _make_resource(self, resource_id="r-001", external_id="ext-r-001",
                       daily_cap=8.0, working_days=None):
        from services.integration_service.contracts import NormalizedResourceRecord
        return NormalizedResourceRecord(
            resource_id=resource_id, source_snapshot_id="snap-001",
            source_system="test", external_resource_id=external_id,
            display_name="Test User", calendar_id="cal-001", calendar_name=None,
            default_daily_capacity_hours=daily_cap,
            working_days=working_days or ["Mon", "Tue", "Wed", "Thu", "Fri"],
            availability_ratio=1.0,
        )

    def _make_task(self, task_id, external_id, effort, start, due):
        from services.integration_service.contracts import NormalizedTaskRecord
        return NormalizedTaskRecord(
            task_id=task_id, source_snapshot_id="snap-001",
            source_system="test", external_task_id=external_id,
            project_id="p-001", project_external_id="proj-001",
            parent_task_id=None, name=f"Task {external_id}",
            hierarchy_path=[task_id], hierarchy_depth=0,
            effort_hours=effort, start_date=start, due_date=due,
        )

    def _make_assignment(self, task_id, task_ext, resource_id, resource_ext):
        from services.integration_service.contracts import NormalizedResourceAssignmentRecord
        return NormalizedResourceAssignmentRecord(
            assignment_id=f"a-{task_id}", source_snapshot_id="snap-001",
            source_system="test", task_id=task_id, task_external_id=task_ext,
            resource_id=resource_id, resource_external_id=resource_ext,
            allocation_percent=None,
        )

    def test_allocation_sum_equals_effort_for_fractional_hours(self):
        """Task with 4.3h effort must produce allocations summing to exactly 4.3h,
        not 4.5h (which is what uncapped rounding would produce)."""
        resource = self._make_resource()
        task = self._make_task("t-001", "ext-t-001", effort=4.3,
                               start="2026-04-06", due="2026-04-10")
        assignment = self._make_assignment("t-001", "ext-t-001", "r-001", "ext-r-001")
        bundle = self._make_bundle([task], resources=[resource], assignments=[assignment])

        engine = PlanningEngineService()
        capacity = engine.build_daily_capacity_model(bundle)
        result = engine.build_draft_schedule(bundle, capacity_result=capacity,
                                              planning_run_id="run-rounding")

        total_allocated = sum(a.allocated_hours for a in result.allocation_outputs)
        self.assertAlmostEqual(total_allocated, 4.3, places=2)
        self.assertEqual(result.task_schedules[0].status, "scheduled")

    def test_rounding_does_not_steal_capacity_from_sibling(self):
        """Two tasks on the same resource with fractional effort. The rounding cap
        must prevent the first task from over-consuming capacity, leaving enough
        for the second task to fully schedule."""
        resource = self._make_resource(daily_cap=8.0)
        task_a = self._make_task("t-001", "ext-t-a", effort=4.3,
                                  start="2026-04-06", due="2026-04-06")
        task_b = self._make_task("t-002", "ext-t-b", effort=3.7,
                                  start="2026-04-06", due="2026-04-06")
        assign_a = self._make_assignment("t-001", "ext-t-a", "r-001", "ext-r-001")
        assign_b = self._make_assignment("t-002", "ext-t-b", "r-001", "ext-r-001")
        bundle = self._make_bundle(
            [task_a, task_b], resources=[resource],
            assignments=[assign_a, assign_b],
        )

        engine = PlanningEngineService()
        capacity = engine.build_daily_capacity_model(bundle)
        result = engine.build_draft_schedule(bundle, capacity_result=capacity,
                                              planning_run_id="run-sibling")

        schedules = {ts.task_external_id: ts for ts in result.task_schedules}
        # Both tasks must be fully scheduled (8h capacity, 4.3 + 3.7 = 8.0h total)
        self.assertEqual(schedules["ext-t-a"].status, "scheduled")
        self.assertEqual(schedules["ext-t-b"].status, "scheduled")

        # Sum of all allocations must not exceed 8.0h
        total = sum(a.allocated_hours for a in result.allocation_outputs)
        self.assertLessEqual(total, 8.0)


if __name__ == "__main__":
    unittest.main()
