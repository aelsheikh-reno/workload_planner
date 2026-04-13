"""Tests for AllocationOutputWriter and _round_up_half helper."""

import unittest
from dataclasses import dataclass
from typing import List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.persistence.models import Assignment, Base, Member, Project, Task
from services.schedule_service.allocation_writer import AllocationOutputWriter, _round_up_half


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


# ── Minimal stubs for DraftScheduleResult / TaskAllocationOutput / DraftTaskSchedule ──

@dataclass
class _FakeAlloc:
    task_external_id: str
    resource_external_id: str
    date: str
    allocated_hours: float


@dataclass
class _FakeTaskSchedule:
    task_external_id: str
    task_name: str
    unscheduled_effort_hours: float
    status: str


@dataclass
class _FakeDraftSchedule:
    allocation_outputs: List[_FakeAlloc]
    task_schedules: List[_FakeTaskSchedule]


def _fake_bundle():
    """Minimal bundle stub (only resource_assignments checked in writer — unused here)."""
    return None


def _make_seed_db(session):
    """Seed one member, one project, one task into the session."""
    m = Member(
        external_id="m-001", display_name="Alice",
        weekly_capacity_hours=40.0,
        working_days=["Sun", "Mon", "Tue", "Wed", "Thu"],
    )
    session.add(m)
    p = Project(external_id="proj-001", name="Alpha", status="active")
    session.add(p)
    session.flush()
    t = Task(
        external_id="t-001", project_id=p.id, name="Task A",
        status="active", estimated_hours=16.0,
        scheduled_start_date="2026-04-06",
        scheduled_end_date="2026-04-07",
    )
    session.add(t)
    session.flush()
    return m, p, t


# ── RoundUpHalf Tests ─────────────────────────────────────────────────────────

class RoundUpHalfTests(unittest.TestCase):

    def test_zero(self):
        self.assertEqual(_round_up_half(0.0), 0.0)

    def test_exact_half(self):
        self.assertEqual(_round_up_half(0.5), 0.5)

    def test_below_half(self):
        self.assertEqual(_round_up_half(0.3), 0.5)

    def test_above_half(self):
        self.assertEqual(_round_up_half(0.6), 1.0)

    def test_whole_number(self):
        self.assertEqual(_round_up_half(8.0), 8.0)

    def test_partial_6_3(self):
        self.assertEqual(_round_up_half(6.3), 6.5)

    def test_partial_6_5(self):
        self.assertEqual(_round_up_half(6.5), 6.5)

    def test_partial_6_6(self):
        self.assertEqual(_round_up_half(6.6), 7.0)

    def test_large_value(self):
        self.assertEqual(_round_up_half(39.1), 39.5)


# ── AllocationOutputWriter Tests ──────────────────────────────────────────────

class AllocationOutputWriterTests(unittest.TestCase):

    def setUp(self):
        self.session = _make_session()
        self.writer = AllocationOutputWriter()
        self.m, self.p, self.t = _make_seed_db(self.session)

    def tearDown(self):
        self.session.close()

    def _draft(self, allocs=None, schedules=None):
        return _FakeDraftSchedule(
            allocation_outputs=allocs or [],
            task_schedules=schedules or [],
        )

    # ── Dry run ───────────────────────────────────────────────────────────────

    def test_dry_run_returns_preview_rows_no_db_write(self):
        draft = self._draft(allocs=[
            _FakeAlloc("t-001", "m-001", "2026-04-06", 8.0),
        ])
        result = self.writer.write(draft, None, self.session, dry_run=True)
        self.assertEqual(result["written"], 0)
        self.assertIsNotNone(result["preview_rows"])
        self.assertEqual(len(result["preview_rows"]), 1)
        # No DB writes
        count = self.session.query(Assignment).count()
        self.assertEqual(count, 0)

    # ── Apply mode ────────────────────────────────────────────────────────────

    def test_apply_writes_assignments_to_db(self):
        draft = self._draft(allocs=[
            _FakeAlloc("t-001", "m-001", "2026-04-06", 8.0),
        ])
        result = self.writer.write(draft, None, self.session, dry_run=False)
        self.assertEqual(result["written"], 1)
        a = self.session.query(Assignment).filter_by(
            task_id=self.t.id, member_id=self.m.id
        ).first()
        self.assertIsNotNone(a)
        self.assertEqual(a.field_overrides.get("source"), "engine")

    def test_hours_aggregated_exactly(self):
        # Two daily allocs: 3.1 + 3.2 = 6.3 — exact sum, no additional rounding
        draft = self._draft(allocs=[
            _FakeAlloc("t-001", "m-001", "2026-04-06", 3.1),
            _FakeAlloc("t-001", "m-001", "2026-04-07", 3.2),
        ])
        self.writer.write(draft, None, self.session, dry_run=False)
        a = self.session.query(Assignment).filter_by(
            task_id=self.t.id, member_id=self.m.id
        ).first()
        self.assertEqual(a.allocated_hours, 6.3)

    def test_manual_override_assignment_preserved(self):
        # Pre-create manual assignment
        existing = Assignment(
            task_id=self.t.id, member_id=self.m.id,
            allocated_hours=10.0,
            start_date="2026-04-06", end_date="2026-04-06",
            field_overrides={"manual": True},
        )
        self.session.add(existing)
        self.session.flush()

        draft = self._draft(allocs=[
            _FakeAlloc("t-001", "m-001", "2026-04-06", 8.0),
        ])
        result = self.writer.write(draft, None, self.session, dry_run=False)
        self.assertEqual(result["skipped_manual"], 1)
        # Original hours untouched
        self.session.refresh(existing)
        self.assertEqual(existing.allocated_hours, 10.0)

    def test_stale_engine_assignments_deleted(self):
        # Add a second task
        t2 = Task(
            external_id="t-002", project_id=self.p.id, name="Task B",
            status="active", estimated_hours=8.0,
            scheduled_start_date="2026-04-06",
            scheduled_end_date="2026-04-06",
        )
        self.session.add(t2)
        self.session.flush()

        # Stale engine assignment for t2
        stale = Assignment(
            task_id=t2.id, member_id=self.m.id,
            allocated_hours=8.0,
            start_date="2026-04-06", end_date="2026-04-06",
            field_overrides={"source": "engine"},
        )
        self.session.add(stale)
        self.session.flush()

        # New run outputs t-001 allocations but processes both tasks
        # (t2 gets 0 allocations — unschedulable). Its stale assignment should
        # be cleaned because t2 IS in the engine's task_schedules scope.
        draft = self._draft(
            allocs=[_FakeAlloc("t-001", "m-001", "2026-04-06", 8.0)],
            schedules=[
                _FakeTaskSchedule("t-001", "Task A", 0.0, "scheduled"),
                _FakeTaskSchedule("t-002", "Task B", 8.0, "unschedulable"),
            ],
        )
        self.writer.write(draft, None, self.session, dry_run=False)

        # Stale engine assignment for t2 should be deleted (t2 was in scope)
        remaining = self.session.query(Assignment).filter_by(task_id=t2.id).count()
        self.assertEqual(remaining, 0)

    def test_seed_assignments_not_deleted(self):
        # Assignment without source="engine" (e.g. import)
        seed_assign = Assignment(
            task_id=self.t.id, member_id=self.m.id,
            allocated_hours=5.0,
            start_date="2026-04-06", end_date="2026-04-06",
            field_overrides={"source": "import"},
        )
        self.session.add(seed_assign)
        self.session.flush()

        # New run doesn't include t-001 at all
        draft = self._draft(allocs=[])
        self.writer.write(draft, None, self.session, dry_run=False)

        # Non-engine assignment survives
        remaining = self.session.query(Assignment).filter_by(task_id=self.t.id).count()
        self.assertEqual(remaining, 1)

    # ── Ghost tasks ───────────────────────────────────────────────────────────

    def test_ghost_tasks_reported(self):
        draft = self._draft(
            allocs=[],
            schedules=[
                _FakeTaskSchedule("t-001", "Task A", 4.0, "partially_schedulable"),
            ],
        )
        result = self.writer.write(draft, None, self.session, dry_run=True)
        self.assertEqual(len(result["ghost_tasks"]), 1)
        self.assertEqual(result["ghost_tasks"][0]["task_external_id"], "t-001")

    def test_ghost_task_hours_rounded_up(self):
        draft = self._draft(
            allocs=[],
            schedules=[
                _FakeTaskSchedule("t-001", "Task A", 3.3, "partially_schedulable"),
            ],
        )
        result = self.writer.write(draft, None, self.session, dry_run=True)
        self.assertEqual(result["ghost_tasks"][0]["unscheduled_hours"], 3.5)

    def test_scheduled_task_not_in_ghost_list(self):
        draft = self._draft(
            allocs=[],
            schedules=[
                _FakeTaskSchedule("t-001", "Task A", 0.0, "scheduled"),
            ],
        )
        result = self.writer.write(draft, None, self.session, dry_run=True)
        self.assertEqual(len(result["ghost_tasks"]), 0)

    # ── Return counts ─────────────────────────────────────────────────────────

    def test_returns_correct_counts(self):
        draft = self._draft(allocs=[
            _FakeAlloc("t-001", "m-001", "2026-04-06", 8.0),
        ])
        result = self.writer.write(draft, None, self.session, dry_run=False)
        self.assertIn("written", result)
        self.assertIn("skipped_manual", result)
        self.assertEqual(result["written"], 1)
        self.assertEqual(result["skipped_manual"], 0)


if __name__ == "__main__":
    unittest.main()
