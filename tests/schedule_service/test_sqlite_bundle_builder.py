"""Tests for SQLiteSourceBundleBuilder — converts SQLite rows to NormalizedSourceBundle."""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.persistence.models import (
    Assignment,
    Base,
    Member,
    Project,
    Task,
    TaskDependency,
    TimeOff,
)
from services.schedule_service.sqlite_bundle_builder import SQLiteSourceBundleBuilder


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _add_member(session, external_id="m-001", display_name="Alice",
                weekly_hours=40.0, working_days=None):
    m = Member(
        external_id=external_id,
        display_name=display_name,
        weekly_capacity_hours=weekly_hours,
        working_days=working_days or ["Sun", "Mon", "Tue", "Wed", "Thu"],
        is_active=True,
    )
    session.add(m)
    session.flush()
    return m


def _add_project(session, external_id="proj-001", name="Alpha"):
    p = Project(external_id=external_id, name=name, status="active")
    session.add(p)
    session.flush()
    return p


def _add_task(session, project_id, external_id="t-001", name="Task A",
              estimated_hours=16.0, status="active",
              start="2026-04-06", end="2026-04-07"):
    t = Task(
        external_id=external_id,
        project_id=project_id,
        name=name,
        status=status,
        estimated_hours=estimated_hours,
        scheduled_start_date=start,
        scheduled_end_date=end,
    )
    session.add(t)
    session.flush()
    return t


class SQLiteSourceBundleBuilderTests(unittest.TestCase):

    def setUp(self):
        self.session = _make_session()
        self.builder = SQLiteSourceBundleBuilder()

    def tearDown(self):
        self.session.close()

    # ── Basic structure ────────────────────────────────────────────────────────

    def test_empty_db_returns_non_runnable_bundle(self):
        bundle = self.builder.build(self.session)
        self.assertFalse(bundle.source_readiness.runnable)
        self.assertEqual(bundle.tasks, [])
        self.assertEqual(bundle.resources, [])
        self.assertEqual(bundle.dependencies, [])

    # ── Members → Resources ────────────────────────────────────────────────────

    def test_active_members_become_resources(self):
        _add_member(self.session, external_id="m-001", weekly_hours=40.0,
                    working_days=["Sun", "Mon", "Tue", "Wed", "Thu"])
        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.resources), 1)
        r = bundle.resources[0]
        self.assertEqual(r.external_resource_id, "m-001")
        # 40h / 5 days = 8.0h/day
        self.assertAlmostEqual(r.default_daily_capacity_hours, 8.0)

    def test_part_time_member_daily_capacity(self):
        _add_member(self.session, external_id="m-002", weekly_hours=32.0,
                    working_days=["Sun", "Mon", "Tue", "Wed", "Thu"])
        bundle = self.builder.build(self.session)
        r = bundle.resources[0]
        # 32 / 5 = 6.4
        self.assertAlmostEqual(r.default_daily_capacity_hours, 6.4)

    def test_availability_ratio_is_one(self):
        _add_member(self.session)
        bundle = self.builder.build(self.session)
        for r in bundle.resources:
            self.assertEqual(r.availability_ratio, 1.0)

    def test_inactive_members_excluded(self):
        m = Member(
            external_id="m-inactive",
            display_name="Inactive",
            weekly_capacity_hours=40.0,
            working_days=["Sun", "Mon"],
            is_active=False,
        )
        self.session.add(m)
        self.session.flush()
        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.resources), 0)

    # ── Time off → Exceptions ──────────────────────────────────────────────────

    def test_time_off_expanded_one_record_per_day(self):
        m = _add_member(self.session, external_id="m-001")
        to = TimeOff(
            member_id=m.id,
            leave_type="annual",
            start_date="2026-04-06",
            end_date="2026-04-08",  # 3 days
        )
        self.session.add(to)
        self.session.flush()

        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.resource_exceptions), 3)
        for exc in bundle.resource_exceptions:
            self.assertEqual(exc.available_capacity_hours, 0.0)

    # ── Tasks ──────────────────────────────────────────────────────────────────

    def test_cancelled_tasks_excluded(self):
        p = _add_project(self.session)
        _add_task(self.session, p.id, external_id="t-cancelled", status="cancelled")
        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.tasks), 0)

    def test_active_tasks_included(self):
        p = _add_project(self.session)
        _add_task(self.session, p.id, external_id="t-active", status="active")
        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.tasks), 1)
        self.assertEqual(bundle.tasks[0].external_task_id, "t-active")

    def test_task_effort_hours_mapped(self):
        p = _add_project(self.session)
        _add_task(self.session, p.id, external_id="t-001", estimated_hours=24.0)
        bundle = self.builder.build(self.session)
        self.assertAlmostEqual(bundle.tasks[0].effort_hours, 24.0)

    # ── Dependencies ──────────────────────────────────────────────────────────

    def test_task_dependencies_become_dependency_records(self):
        p = _add_project(self.session)
        t1 = _add_task(self.session, p.id, external_id="t-001")
        t2 = _add_task(self.session, p.id, external_id="t-002")
        dep = TaskDependency(predecessor_id=t1.id, successor_id=t2.id, dependency_type="FS")
        self.session.add(dep)
        self.session.flush()

        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.dependencies), 1)
        d = bundle.dependencies[0]
        self.assertEqual(d.predecessor_external_task_id, "t-001")
        self.assertEqual(d.successor_external_task_id, "t-002")

    # ── Assignments ───────────────────────────────────────────────────────────

    def test_assignments_included_in_bundle(self):
        m = _add_member(self.session, external_id="m-001")
        p = _add_project(self.session)
        t = _add_task(self.session, p.id, external_id="t-001")
        a = Assignment(
            task_id=t.id, member_id=m.id,
            allocated_hours=8.0,
            start_date="2026-04-06", end_date="2026-04-06",
        )
        self.session.add(a)
        self.session.flush()

        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.resource_assignments), 1)
        ar = bundle.resource_assignments[0]
        self.assertEqual(ar.task_external_id, "t-001")
        self.assertEqual(ar.resource_external_id, "m-001")

    def test_allocation_percent_from_field_overrides(self):
        m = _add_member(self.session, external_id="m-001")
        p = _add_project(self.session)
        t = _add_task(self.session, p.id, external_id="t-001")
        a = Assignment(
            task_id=t.id, member_id=m.id,
            allocated_hours=0.0,
            start_date="2026-04-06", end_date="2026-04-06",
            field_overrides={"allocation_percent": 50},
        )
        self.session.add(a)
        self.session.flush()

        bundle = self.builder.build(self.session)
        ar = bundle.resource_assignments[0]
        self.assertEqual(ar.allocation_percent, 50)

    # ── Stable IDs ────────────────────────────────────────────────────────────

    def test_stable_snapshot_id(self):
        p = _add_project(self.session)
        _add_task(self.session, p.id, external_id="t-001")

        bundle1 = self.builder.build(self.session)
        bundle2 = self.builder.build(self.session)
        self.assertEqual(bundle1.snapshot.snapshot_id, bundle2.snapshot.snapshot_id)

    # ── All records share the snapshot_id ─────────────────────────────────────

    def test_all_records_have_matching_snapshot_id(self):
        m = _add_member(self.session, external_id="m-001")
        p = _add_project(self.session)
        t = _add_task(self.session, p.id, external_id="t-001")
        a = Assignment(
            task_id=t.id, member_id=m.id,
            allocated_hours=8.0,
            start_date="2026-04-06", end_date="2026-04-06",
        )
        self.session.add(a)
        self.session.flush()

        bundle = self.builder.build(self.session)
        sid = bundle.snapshot.snapshot_id
        for r in bundle.resources:
            self.assertEqual(r.source_snapshot_id, sid)
        for t_rec in bundle.tasks:
            self.assertEqual(t_rec.source_snapshot_id, sid)
        for ar in bundle.resource_assignments:
            self.assertEqual(ar.source_snapshot_id, sid)


    # ── Zero-effort / null-effort handling ──────────────────────────────────

    def test_zero_effort_task_gets_zero_not_none(self):
        """Tasks with estimated_hours=0 and buffer_hours=0 must get effort_hours=0.0,
        NOT None. Zero-effort tasks are milestones — the engine marks them SCHEDULED
        instantly so their successors can proceed."""
        p = _add_project(self.session)
        t = Task(
            external_id="t-milestone",
            project_id=p.id,
            name="Milestone",
            status="active",
            estimated_hours=0.0,
            buffer_hours=0.0,
            scheduled_start_date="2026-04-06",
            scheduled_end_date="2026-04-06",
        )
        self.session.add(t)
        self.session.flush()

        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.tasks), 1)
        self.assertEqual(bundle.tasks[0].effort_hours, 0.0)

    def test_null_effort_task_gets_none(self):
        """Tasks where both estimated_hours and buffer_hours are None (no estimate
        provided) must get effort_hours=None so the engine marks them UNSCHEDULABLE
        with 'missing_task_effort'."""
        p = _add_project(self.session)
        t = Task(
            external_id="t-no-estimate",
            project_id=p.id,
            name="No Estimate",
            status="active",
            estimated_hours=None,
            buffer_hours=None,
            scheduled_start_date="2026-04-06",
            scheduled_end_date="2026-04-06",
        )
        self.session.add(t)
        self.session.flush()

        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.tasks), 1)
        self.assertIsNone(bundle.tasks[0].effort_hours)

    # ── Date extension with non-FS dependencies ────────────────────────────

    def test_ss_dependency_pushes_start_date(self):
        """SS dependency: successor cannot start before predecessor starts.
        Date extension should push the successor's start date forward."""
        m = _add_member(self.session, external_id="m-001", weekly_hours=40.0)
        p = _add_project(self.session)
        # Predecessor starts Apr 15 (future)
        pred = _add_task(self.session, p.id, external_id="t-pred", name="Pred",
                         estimated_hours=8.0, start="2026-04-15", end="2026-04-15")
        # Successor originally starts Apr 8, due Apr 10
        succ = _add_task(self.session, p.id, external_id="t-succ", name="Succ",
                         estimated_hours=8.0, start="2026-04-08", end="2026-04-10")
        dep = TaskDependency(predecessor_id=pred.id, successor_id=succ.id,
                             dependency_type="SS")
        self.session.add(dep)
        # Assignments needed for prepare_and_build
        self.session.add(Assignment(task_id=pred.id, member_id=m.id,
                                     allocated_hours=0, start_date="2026-04-15",
                                     end_date="2026-04-15"))
        self.session.add(Assignment(task_id=succ.id, member_id=m.id,
                                     allocated_hours=0, start_date="2026-04-08",
                                     end_date="2026-04-10"))
        self.session.flush()

        bundle, _, log = self.builder.prepare_and_build(
            self.session, project_id=p.id)

        # The bundle gives the earliest possible start (_original_start for unpinned
        # tasks). The SS dep constraint is enforced by the engine, not the bundle.
        # But the end date should be extended to accommodate the effort.
        succ_rec = next(t for t in bundle.tasks if t.external_task_id == "t-succ")
        # End date must be extended (SS dep pushes start, so window needs to grow)
        self.assertGreaterEqual(succ_rec.due_date, "2026-04-15")

    def test_ff_dependency_extends_end_date(self):
        """FF dependency: successor cannot finish before predecessor finishes.
        Date extension should extend the successor's end date to match the
        predecessor's projected end (when it actually finishes based on capacity)."""
        m = _add_member(self.session, external_id="m-001", weekly_hours=40.0)
        p = _add_project(self.session)
        # Predecessor: 16h effort, 8h/day → needs 2 working days. Starts Apr 19 (Sun).
        # Working days: Sun-Thu. Apr 19=Sun, Apr 20=Mon → projected end = Apr 20.
        pred = _add_task(self.session, p.id, external_id="t-pred", name="Pred",
                         estimated_hours=16.0, start="2026-04-19", end="2026-04-22")
        # Successor originally due Apr 15 (before predecessor finishes)
        succ = _add_task(self.session, p.id, external_id="t-succ", name="Succ",
                         estimated_hours=8.0, start="2026-04-13", end="2026-04-15")
        dep = TaskDependency(predecessor_id=pred.id, successor_id=succ.id,
                             dependency_type="FF")
        self.session.add(dep)
        self.session.add(Assignment(task_id=pred.id, member_id=m.id,
                                     allocated_hours=0, start_date="2026-04-19",
                                     end_date="2026-04-22"))
        self.session.add(Assignment(task_id=succ.id, member_id=m.id,
                                     allocated_hours=0, start_date="2026-04-13",
                                     end_date="2026-04-15"))
        self.session.flush()

        bundle, _, log = self.builder.prepare_and_build(
            self.session, project_id=p.id)

        succ_rec = next(t for t in bundle.tasks if t.external_task_id == "t-succ")
        # FF dep should extend successor's end to at least Apr 20
        # (predecessor projects to finish Apr 20 = Sun+Mon with 16h at 8h/day)
        self.assertGreaterEqual(succ_rec.due_date, "2026-04-20")

    def test_sibling_tasks_date_extension_for_same_member(self):
        """Two tasks on the same member with 1-day windows that compete for
        capacity. The second pass should extend one task's end date so both fit."""
        m = _add_member(self.session, external_id="m-001", weekly_hours=40.0,
                        working_days=["Sun", "Mon", "Tue", "Wed", "Thu"])
        p = _add_project(self.session)
        # Both tasks: 8h effort on same day, member has 8h/day capacity
        # Combined: 16h needed, only 8h available on Apr 6 (Sun)
        t1 = _add_task(self.session, p.id, external_id="t-1", name="Task 1",
                       estimated_hours=8.0, start="2026-04-05", end="2026-04-05")
        t2 = _add_task(self.session, p.id, external_id="t-2", name="Task 2",
                       estimated_hours=8.0, start="2026-04-05", end="2026-04-05")
        self.session.add(Assignment(task_id=t1.id, member_id=m.id,
                                     allocated_hours=0, start_date="2026-04-05",
                                     end_date="2026-04-05"))
        self.session.add(Assignment(task_id=t2.id, member_id=m.id,
                                     allocated_hours=0, start_date="2026-04-05",
                                     end_date="2026-04-05"))
        self.session.flush()

        bundle, _, log = self.builder.prepare_and_build(
            self.session, project_id=p.id)

        # At least one task should have its end date extended beyond Apr 5
        ends = [t.due_date for t in bundle.tasks]
        self.assertTrue(
            any(e > "2026-04-05" for e in ends),
            f"Expected at least one task extended past Apr 5, got ends: {ends}"
        )

    def test_buffer_hours_included_in_effort_and_date_extension(self):
        """Buffer hours must be added to estimated_hours for total effort.
        The date extension must use total effort (estimated + buffer) to
        determine the scheduling window, NOT just estimated_hours."""
        m = _add_member(self.session, external_id="m-001", weekly_hours=40.0,
                        working_days=["Sun", "Mon", "Tue", "Wed", "Thu"])
        p = _add_project(self.session)
        # 8h estimated + 4h buffer = 12h total. At 8h/day, needs 2 days.
        # Window is only 1 day (Apr 6). Extension should expand to 2 days.
        t = Task(
            external_id="t-buffered",
            project_id=p.id,
            name="Buffered Task",
            status="active",
            estimated_hours=8.0,
            buffer_hours=4.0,
            scheduled_start_date="2026-04-06",
            scheduled_end_date="2026-04-06",
        )
        self.session.add(t)
        self.session.flush()
        self.session.add(Assignment(task_id=t.id, member_id=m.id,
                                     allocated_hours=0, start_date="2026-04-06",
                                     end_date="2026-04-06"))
        self.session.flush()

        bundle, _, log = self.builder.prepare_and_build(
            self.session, project_id=p.id)

        task_rec = next(r for r in bundle.tasks if r.external_task_id == "t-buffered")
        # effort_hours must be estimated + buffer = 12h
        self.assertAlmostEqual(task_rec.effort_hours, 12.0)
        # Window must be extended past Apr 6 to fit 12h
        self.assertGreater(task_rec.due_date, "2026-04-06")

    def test_field_override_dates_do_not_cap_extension(self):
        """If field_overrides has scheduled_end_date from a previous edit,
        it must NOT override the date extension. The scheduler should use
        the extended dates, not the stale override."""
        m = _add_member(self.session, external_id="m-001", weekly_hours=40.0,
                        working_days=["Sun", "Mon", "Tue", "Wed", "Thu"])
        p = _add_project(self.session)
        # Task with 24h effort in a 1-day window, plus a stale field_override
        t = Task(
            external_id="t-override",
            project_id=p.id,
            name="Override Task",
            status="active",
            estimated_hours=24.0,
            scheduled_start_date="2026-04-06",
            scheduled_end_date="2026-04-06",
            field_overrides={"scheduled_end_date": "2026-04-06"},
        )
        self.session.add(t)
        self.session.flush()
        self.session.add(Assignment(task_id=t.id, member_id=m.id,
                                     allocated_hours=0, start_date="2026-04-06",
                                     end_date="2026-04-06"))
        self.session.flush()

        bundle, _, log = self.builder.prepare_and_build(
            self.session, project_id=p.id)

        task_rec = next(r for r in bundle.tasks if r.external_task_id == "t-override")
        # Must be extended past Apr 6 (24h / 8h/day = 3 working days)
        self.assertGreater(task_rec.due_date, "2026-04-06")

    def test_parent_tasks_get_zero_effort(self):
        """Parent tasks (tasks that have children) must get effort=0.0 in the
        bundle so the engine marks them SCHEDULED instantly. This prevents
        dependencies through parent tasks from blocking leaf tasks."""
        m = _add_member(self.session, external_id="m-001")
        p = _add_project(self.session)
        parent = _add_task(self.session, p.id, external_id="t-parent",
                           name="Parent Phase", estimated_hours=None,
                           start="2026-04-06", end="2026-04-10")
        child = Task(
            external_id="t-child", project_id=p.id, name="Child Task",
            status="active", estimated_hours=8.0, parent_id=parent.id,
            hierarchy_depth=1,
            scheduled_start_date="2026-04-06", scheduled_end_date="2026-04-07",
        )
        self.session.add(child)
        self.session.flush()

        bundle = self.builder.build(self.session)

        parent_rec = next(t for t in bundle.tasks if t.external_task_id == "t-parent")
        child_rec = next(t for t in bundle.tasks if t.external_task_id == "t-child")
        # Parent gets 0 effort (container), child keeps real effort
        self.assertEqual(parent_rec.effort_hours, 0.0)
        self.assertAlmostEqual(child_rec.effort_hours, 8.0)

    def test_buffer_only_task_gets_buffer_as_effort(self):
        """Tasks with estimated_hours=None but buffer_hours set should use buffer
        as the effort (not become None)."""
        p = _add_project(self.session)
        t = Task(
            external_id="t-buffer-only",
            project_id=p.id,
            name="Buffer Only",
            status="active",
            estimated_hours=None,
            buffer_hours=2.0,
            scheduled_start_date="2026-04-06",
            scheduled_end_date="2026-04-06",
        )
        self.session.add(t)
        self.session.flush()

        bundle = self.builder.build(self.session)
        self.assertEqual(len(bundle.tasks), 1)
        self.assertAlmostEqual(bundle.tasks[0].effort_hours, 2.0)


if __name__ == "__main__":
    unittest.main()
