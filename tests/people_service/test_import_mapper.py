"""Tests for ImportToFloatMapper — syncs NormalizedSourceBundle into SQLite."""

import unittest
from contextlib import contextmanager
from dataclasses import dataclass
from typing import List, Optional
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.persistence.models import Assignment, Base, Member, Project, Task, TaskDependency
from services.people_service.import_mapper import ImportToFloatMapper


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _make_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()


# ── Minimal bundle stubs ──────────────────────────────────────────────────────

@dataclass
class _Resource:
    external_resource_id: str
    display_name: str = "Test User"
    default_daily_capacity_hours: float = 8.0


@dataclass
class _TaskRec:
    external_task_id: str
    project_external_id: str
    name: str
    effort_hours: Optional[float] = 16.0
    start_date: Optional[str] = "2026-04-06"
    due_date: Optional[str] = "2026-04-07"


@dataclass
class _DepRec:
    predecessor_external_task_id: str
    successor_external_task_id: str


@dataclass
class _AssignRec:
    task_external_id: str
    resource_external_id: str
    allocation_percent: Optional[float] = None


@dataclass
class _Bundle:
    resources: List[_Resource]
    tasks: List[_TaskRec]
    dependencies: List[_DepRec]
    resource_assignments: List[_AssignRec]


# ── Test class ────────────────────────────────────────────────────────────────

class ImportToFloatMapperTests(unittest.TestCase):

    def setUp(self):
        self.engine = _make_engine()
        self.session = _make_session(self.engine)
        self.mapper = ImportToFloatMapper()

    def tearDown(self):
        self.session.close()

    @contextmanager
    def _patch_db(self):
        """Patches get_db_session to yield our in-memory session."""
        @contextmanager
        def _fake_session():
            yield self.session

        with patch("services.people_service.import_mapper.get_db_session", _fake_session):
            yield

    def _sync(self, bundle):
        with self._patch_db():
            return self.mapper.sync_from_bundle(bundle)

    def _add_member(self, external_id="m-001", display_name="Alice"):
        m = Member(
            external_id=external_id,
            display_name=display_name,
            weekly_capacity_hours=40.0,
            working_days=["Sun", "Mon", "Tue", "Wed", "Thu"],
        )
        self.session.add(m)
        self.session.flush()
        return m

    # ── Members ───────────────────────────────────────────────────────────────

    def test_matched_member_not_created(self):
        self._add_member(external_id="m-001")
        bundle = _Bundle(
            resources=[_Resource("m-001")],
            tasks=[], dependencies=[], resource_assignments=[],
        )
        self._sync(bundle)
        count = self.session.query(Member).count()
        self.assertEqual(count, 1)  # no new member created

    def test_unmatched_member_in_counts(self):
        bundle = _Bundle(
            resources=[_Resource("m-unknown")],
            tasks=[], dependencies=[], resource_assignments=[],
        )
        counts = self._sync(bundle)
        self.assertIn("m-unknown", counts["unmatched_resources"])

    # ── Projects ──────────────────────────────────────────────────────────────

    def test_project_created_if_missing(self):
        bundle = _Bundle(
            resources=[],
            tasks=[_TaskRec("t-001", "proj-new", "Task A")],
            dependencies=[], resource_assignments=[],
        )
        counts = self._sync(bundle)
        self.assertEqual(counts["projects"], 1)
        proj = self.session.query(Project).filter_by(external_id="proj-new").first()
        self.assertIsNotNone(proj)

    def test_project_not_duplicated(self):
        # Pre-create the project
        p = Project(external_id="proj-001", name="Alpha", status="active")
        self.session.add(p)
        self.session.flush()

        bundle = _Bundle(
            resources=[],
            tasks=[_TaskRec("t-001", "proj-001", "Task A")],
            dependencies=[], resource_assignments=[],
        )
        counts = self._sync(bundle)
        self.assertEqual(counts["projects"], 0)

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def test_task_created_with_correct_fields(self):
        bundle = _Bundle(
            resources=[],
            tasks=[_TaskRec("t-001", "proj-001", "Task Alpha", effort_hours=24.0,
                            start_date="2026-04-06", due_date="2026-04-09")],
            dependencies=[], resource_assignments=[],
        )
        counts = self._sync(bundle)
        self.assertEqual(counts["tasks"], 1)
        t = self.session.query(Task).filter_by(external_id="t-001").first()
        self.assertIsNotNone(t)
        self.assertEqual(t.name, "Task Alpha")
        self.assertAlmostEqual(t.estimated_hours, 24.0)
        self.assertEqual(t.scheduled_start_date, "2026-04-06")
        self.assertEqual(t.scheduled_end_date, "2026-04-09")

    def test_task_field_overrides_not_overwritten(self):
        # Pre-create task with manual date override
        p = Project(external_id="proj-001", name="Alpha", status="active")
        self.session.add(p)
        self.session.flush()
        t = Task(
            external_id="t-001", project_id=p.id, name="Task A",
            status="active", estimated_hours=10.0,
            scheduled_start_date="2026-03-01",
            scheduled_end_date="2026-03-05",
            field_overrides={"scheduled_start_date": "2026-03-15"},
        )
        self.session.add(t)
        self.session.flush()

        bundle = _Bundle(
            resources=[],
            tasks=[_TaskRec("t-001", "proj-001", "Task A",
                            start_date="2026-04-06", due_date="2026-04-09")],
            dependencies=[], resource_assignments=[],
        )
        self._sync(bundle)
        self.session.refresh(t)
        # scheduled_start_date should remain unchanged (field_overrides has it)
        self.assertEqual(t.scheduled_start_date, "2026-03-01")
        self.assertEqual(t.field_overrides.get("scheduled_start_date"), "2026-03-15")

    # ── Dependencies ──────────────────────────────────────────────────────────

    def test_dependency_created(self):
        bundle = _Bundle(
            resources=[],
            tasks=[
                _TaskRec("t-001", "proj-001", "Task A"),
                _TaskRec("t-002", "proj-001", "Task B"),
            ],
            dependencies=[_DepRec("t-001", "t-002")],
            resource_assignments=[],
        )
        counts = self._sync(bundle)
        self.assertEqual(counts["dependencies"], 1)
        dep = self.session.query(TaskDependency).first()
        self.assertIsNotNone(dep)

    def test_duplicate_dependency_not_created(self):
        # Create tasks and a dependency first
        p = Project(external_id="proj-001", name="Alpha", status="active")
        self.session.add(p)
        self.session.flush()
        t1 = Task(external_id="t-001", project_id=p.id, name="A", status="active",
                  scheduled_start_date="2026-04-06", scheduled_end_date="2026-04-07",
                  estimated_hours=8.0)
        t2 = Task(external_id="t-002", project_id=p.id, name="B", status="active",
                  scheduled_start_date="2026-04-08", scheduled_end_date="2026-04-09",
                  estimated_hours=8.0)
        self.session.add_all([t1, t2])
        self.session.flush()
        dep = TaskDependency(predecessor_id=t1.id, successor_id=t2.id, dependency_type="FS")
        self.session.add(dep)
        self.session.flush()

        bundle = _Bundle(
            resources=[],
            tasks=[
                _TaskRec("t-001", "proj-001", "A"),
                _TaskRec("t-002", "proj-001", "B"),
            ],
            dependencies=[_DepRec("t-001", "t-002")],
            resource_assignments=[],
        )
        counts = self._sync(bundle)
        self.assertEqual(counts["dependencies"], 0)
        total_deps = self.session.query(TaskDependency).count()
        self.assertEqual(total_deps, 1)

    # ── Assignments ───────────────────────────────────────────────────────────

    def test_assignment_uses_zero_hours_placeholder(self):
        m = self._add_member("m-001")
        bundle = _Bundle(
            resources=[_Resource("m-001")],
            tasks=[_TaskRec("t-001", "proj-001", "Task A",
                            start_date="2026-04-06", due_date="2026-04-07")],
            dependencies=[],
            resource_assignments=[_AssignRec("t-001", "m-001")],
        )
        self._sync(bundle)
        a = self.session.query(Assignment).first()
        self.assertIsNotNone(a)
        self.assertEqual(a.allocated_hours, 0.0)

    def test_allocation_percent_stored_in_overrides(self):
        self._add_member("m-001")
        bundle = _Bundle(
            resources=[_Resource("m-001")],
            tasks=[_TaskRec("t-001", "proj-001", "Task A",
                            start_date="2026-04-06", due_date="2026-04-07")],
            dependencies=[],
            resource_assignments=[_AssignRec("t-001", "m-001", allocation_percent=75)],
        )
        self._sync(bundle)
        a = self.session.query(Assignment).first()
        self.assertEqual(a.field_overrides.get("allocation_percent"), 75)

    def test_assignment_skipped_if_member_unmatched(self):
        bundle = _Bundle(
            resources=[_Resource("m-unknown")],
            tasks=[_TaskRec("t-001", "proj-001", "Task A",
                            start_date="2026-04-06", due_date="2026-04-07")],
            dependencies=[],
            resource_assignments=[_AssignRec("t-001", "m-unknown")],
        )
        self._sync(bundle)
        count = self.session.query(Assignment).count()
        self.assertEqual(count, 0)

    # ── Return counts ─────────────────────────────────────────────────────────

    def test_returned_counts_accurate(self):
        self._add_member("m-001")
        bundle = _Bundle(
            resources=[_Resource("m-001")],
            tasks=[
                _TaskRec("t-001", "proj-001", "Task A",
                         start_date="2026-04-06", due_date="2026-04-07"),
                _TaskRec("t-002", "proj-001", "Task B",
                         start_date="2026-04-08", due_date="2026-04-09"),
            ],
            dependencies=[_DepRec("t-001", "t-002")],
            resource_assignments=[
                _AssignRec("t-001", "m-001"),
                _AssignRec("t-002", "m-001"),
            ],
        )
        counts = self._sync(bundle)
        self.assertIn("projects", counts)
        self.assertIn("tasks", counts)
        self.assertIn("dependencies", counts)
        self.assertIn("assignments", counts)
        self.assertIn("unmatched_resources", counts)
        self.assertEqual(counts["tasks"], 2)
        self.assertEqual(counts["assignments"], 2)
        self.assertEqual(counts["dependencies"], 1)


if __name__ == "__main__":
    unittest.main()
