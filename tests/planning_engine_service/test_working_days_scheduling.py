"""Tests for working_days format normalization and SQLite pipeline scheduling."""

import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.persistence.models import Assignment, Base, Member, Project, Task
from services.planning_engine_service import PlanningEngineService
from services.planning_engine_service.service import _build_daily_capacity_output, _day_name
from services.schedule_service.allocation_writer import AllocationOutputWriter
from services.schedule_service.sqlite_bundle_builder import SQLiteSourceBundleBuilder


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


# ── _day_name format tests ────────────────────────────────────────────────────

class DayNameFormatTests(unittest.TestCase):

    def test_sunday_returns_sun(self):
        self.assertEqual(_day_name("2026-04-05"), "Sun")

    def test_monday_returns_mon(self):
        self.assertEqual(_day_name("2026-04-06"), "Mon")

    def test_wednesday_returns_wed(self):
        self.assertEqual(_day_name("2026-04-08"), "Wed")

    def test_thursday_returns_thu(self):
        self.assertEqual(_day_name("2026-04-09"), "Thu")

    def test_friday_returns_fri(self):
        self.assertEqual(_day_name("2026-04-10"), "Fri")

    def test_saturday_returns_sat(self):
        self.assertEqual(_day_name("2026-04-11"), "Sat")


# ── Working days normalization tests ─────────────────────────────────────────

class WorkingDaysNormalizationTests(unittest.TestCase):
    """Verify that _build_daily_capacity_output handles both 'monday' and 'Mon' formats."""

    def _make_resource(self, working_days, daily_capacity=8.0):
        from services.integration_service.contracts import NormalizedResourceRecord
        return NormalizedResourceRecord(
            resource_id="r-001",
            source_snapshot_id="snap-001",
            source_system="test",
            external_resource_id="ext-001",
            display_name="Test User",
            calendar_id="cal-001",
            calendar_name=None,
            default_daily_capacity_hours=daily_capacity,
            working_days=working_days,
            availability_ratio=1.0,
        )

    def _make_bundle(self, resource):
        from services.integration_service.contracts import (
            NormalizedSourceBundle,
            SourceArtifact,
            SourceReadiness,
            SourceSnapshot,
        )
        artifact = SourceArtifact(
            artifact_id="art-001",
            external_artifact_id="art-001",
            source_system="test",
            captured_at="2026-04-09",
            payload_digest="abc",
            raw_payload={},
        )
        snapshot = SourceSnapshot(
            snapshot_id="snap-001",
            artifact_id="art-001",
            source_system="test",
            captured_at="2026-04-09",
            project_count=0,
            task_count=0,
            dependency_count=0,
            assignment_count=0,
            issue_count=0,
        )
        readiness = SourceReadiness(
            state="ready", runnable=True,
            blocking_issue_count=0, advisory_issue_count=0, total_issue_count=0,
        )
        return NormalizedSourceBundle(
            artifact=artifact,
            snapshot=snapshot,
            project_mappings=[],
            task_mappings=[],
            resource_mappings=[],
            tasks=[],
            dependencies=[],
            resource_assignments=[],
            resources=[resource],
            resource_exceptions=[],
            issue_facts=[],
            source_readiness=readiness,
        )

    def test_full_lowercase_working_days_recognized(self):
        resource = self._make_resource(
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"]
        )
        bundle = self._make_bundle(resource)
        # Monday 2026-04-06
        output = _build_daily_capacity_output(bundle, resource, "2026-04-06", 0, None)
        self.assertGreater(output.productive_capacity_hours, 0.0)

    def test_abbreviated_working_days_recognized(self):
        resource = self._make_resource(
            working_days=["Mon", "Tue", "Wed", "Thu", "Fri"]
        )
        bundle = self._make_bundle(resource)
        output = _build_daily_capacity_output(bundle, resource, "2026-04-06", 0, None)
        self.assertGreater(output.productive_capacity_hours, 0.0)

    def test_sun_thu_abbreviated_excludes_fri(self):
        resource = self._make_resource(
            working_days=["Sun", "Mon", "Tue", "Wed", "Thu"]
        )
        bundle = self._make_bundle(resource)
        # Friday 2026-04-10
        output = _build_daily_capacity_output(bundle, resource, "2026-04-10", 0, None)
        self.assertEqual(output.productive_capacity_hours, 0.0)

    def test_non_working_day_has_zero_capacity(self):
        resource = self._make_resource(
            working_days=["Mon", "Tue", "Wed", "Thu", "Fri"]
        )
        bundle = self._make_bundle(resource)
        # Sunday 2026-04-05
        output = _build_daily_capacity_output(bundle, resource, "2026-04-05", 0, None)
        self.assertEqual(output.productive_capacity_hours, 0.0)


# ── SQLite pipeline integration tests ────────────────────────────────────────

class SQLitePipelineSchedulingTests(unittest.TestCase):

    def setUp(self):
        self.session = _make_session()
        self._seed()

    def tearDown(self):
        self.session.close()

    def _seed(self):
        m = Member(
            external_id="m-001", display_name="Alice",
            weekly_capacity_hours=40.0,
            working_days=["Sun", "Mon", "Tue", "Wed", "Thu"],
            is_active=True,
        )
        self.session.add(m)
        self.member = m

        p = Project(external_id="proj-001", name="Alpha", status="active")
        self.session.add(p)
        self.session.flush()

        t = Task(
            external_id="t-001", project_id=p.id, name="Task A",
            status="active", estimated_hours=16.0,
            scheduled_start_date="2026-04-06",
            scheduled_end_date="2026-04-13",
        )
        self.session.add(t)
        self.session.flush()

        a = Assignment(
            task_id=t.id, member_id=m.id,
            allocated_hours=0.0,
            start_date="2026-04-06", end_date="2026-04-13",
            field_overrides={"source": "import"},
        )
        self.session.add(a)
        self.session.flush()
        self.task = t

    def _build_and_schedule(self, dry_run=False):
        builder = SQLiteSourceBundleBuilder()
        bundle = builder.build(self.session)

        engine = PlanningEngineService()
        draft = engine.build_draft_schedule(bundle)

        writer = AllocationOutputWriter()
        summary = writer.write(draft, bundle, self.session, dry_run=dry_run)
        return draft, summary

    def test_bundle_is_runnable(self):
        bundle = SQLiteSourceBundleBuilder().build(self.session)
        self.assertTrue(bundle.source_readiness.runnable)

    def test_task_scheduled_with_sun_thu_capacity(self):
        draft, _ = self._build_and_schedule(dry_run=True)
        statuses = {ts.task_external_id: ts.status for ts in draft.task_schedules}
        self.assertEqual(statuses.get("t-001"), "scheduled")

    def test_dry_run_no_db_changes(self):
        original_count = self.session.query(Assignment).count()
        _, summary = self._build_and_schedule(dry_run=True)
        self.assertEqual(summary["written"], 0)
        self.assertEqual(self.session.query(Assignment).count(), original_count)

    def test_apply_writes_engine_assignments(self):
        _, summary = self._build_and_schedule(dry_run=False)
        self.assertGreater(summary["written"], 0)
        engine_assigns = (
            self.session.query(Assignment)
            .filter(Assignment.task_id == self.task.id)
            .all()
        )
        sources = [a.field_overrides.get("source") for a in engine_assigns]
        self.assertIn("engine", sources)

    def test_sun_thu_capacity_8h_per_day(self):
        builder = SQLiteSourceBundleBuilder()
        bundle = builder.build(self.session)
        r = bundle.resources[0]
        # 40h / 5 days = 8.0h/day
        self.assertAlmostEqual(r.default_daily_capacity_hours, 8.0)


# ── Exception overwrite tests ────────────────────────────────────────────────

class ExceptionOverwriteTests(unittest.TestCase):
    """Verify that when multiple exceptions exist for the same (resource, date),
    the capacity model keeps the most restrictive (lowest capacity) one."""

    def test_time_off_not_overwritten_by_cross_project(self):
        """Time-off (0h) must win over cross-project deduction (5h) on the same date."""
        from services.integration_service.contracts import (
            NormalizedResourceExceptionRecord,
            NormalizedResourceRecord,
            NormalizedSourceBundle,
            NormalizedTaskRecord,
            NormalizedResourceAssignmentRecord,
            SourceArtifact,
            SourceReadiness,
            SourceSnapshot,
        )

        resource = NormalizedResourceRecord(
            resource_id="r-001", source_snapshot_id="snap-001",
            source_system="test", external_resource_id="ext-001",
            display_name="Ahmed", calendar_id="cal-001", calendar_name=None,
            default_daily_capacity_hours=8.0,
            working_days=["Sun", "Mon", "Tue", "Wed", "Thu"],
            availability_ratio=1.0,
        )
        task = NormalizedTaskRecord(
            task_id="t-001", source_snapshot_id="snap-001",
            source_system="test", external_task_id="ext-t-001",
            project_id="p-001", project_external_id="proj-001",
            parent_task_id=None, name="Task A",
            hierarchy_path=["t-001"], hierarchy_depth=0,
            effort_hours=8.0, start_date="2026-04-06", due_date="2026-04-08",
        )
        assignment = NormalizedResourceAssignmentRecord(
            assignment_id="a-001", source_snapshot_id="snap-001",
            source_system="test", task_id="t-001", task_external_id="ext-t-001",
            resource_id="r-001", resource_external_id="ext-001",
            allocation_percent=None,
        )
        # Two exceptions for the same (resource, date):
        # 1. Time-off: 0h capacity
        time_off_exception = NormalizedResourceExceptionRecord(
            exception_id="exc-timeoff", source_snapshot_id="snap-001",
            source_system="test", resource_id="r-001",
            resource_external_id="ext-001",
            date="2026-04-07", available_capacity_hours=0.0,
            reason="annual_leave",
        )
        # 2. Cross-project deduction: 5h remaining capacity
        cross_project_exception = NormalizedResourceExceptionRecord(
            exception_id="exc-xproj", source_snapshot_id="snap-001",
            source_system="test", resource_id="r-001",
            resource_external_id="ext-001",
            date="2026-04-07", available_capacity_hours=5.0,
            reason="manual_reassignment",
        )

        artifact = SourceArtifact(
            artifact_id="art-001", external_artifact_id="art-001",
            source_system="test", captured_at="2026-04-09",
            payload_digest="abc", raw_payload={},
        )
        snapshot = SourceSnapshot(
            snapshot_id="snap-001", artifact_id="art-001",
            source_system="test", captured_at="2026-04-09",
            project_count=1, task_count=1,
            dependency_count=0, assignment_count=1, issue_count=0,
        )
        readiness = SourceReadiness(
            state="ready", runnable=True,
            blocking_issue_count=0, advisory_issue_count=0, total_issue_count=0,
        )
        bundle = NormalizedSourceBundle(
            artifact=artifact, snapshot=snapshot,
            project_mappings=[], task_mappings=[], resource_mappings=[],
            tasks=[task], dependencies=[],
            resource_assignments=[assignment],
            resources=[resource],
            resource_exceptions=[time_off_exception, cross_project_exception],
            issue_facts=[], source_readiness=readiness,
        )

        engine = PlanningEngineService()
        capacity_result = engine.build_daily_capacity_model(bundle)

        # Find the capacity output for Apr 7 (the conflicting date)
        outputs_by_date = {
            o.date: o for o in capacity_result.daily_capacity_outputs
        }
        apr_7 = outputs_by_date["2026-04-07"]

        # Time-off (0h) must win — member is on leave, not available
        self.assertEqual(apr_7.productive_capacity_hours, 0.0)
        self.assertEqual(apr_7.exception_reason, "annual_leave")


if __name__ == "__main__":
    unittest.main()
