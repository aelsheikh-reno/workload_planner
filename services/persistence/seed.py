"""Demo data seeder — populates the database on first startup."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import bcrypt

from .models import Assignment, Member, Project, Task, TaskDependency, TimeOff, User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


WORKING_DAYS_DEFAULT = ["Sun", "Mon", "Tue", "Wed", "Thu"]  # Middle East work week

DEMO_MEMBERS = [
    {
        "external_id": "user-ada",
        "display_name": "Ada Lovelace",
        "email": "ada@demo.com",
        "role": "manager",
        "weekly_capacity_hours": 40.0,
        "working_days": WORKING_DAYS_DEFAULT,
        "avatar_color": "#4CAF50",
    },
    {
        "external_id": "user-grace",
        "display_name": "Grace Hopper",
        "email": "grace@demo.com",
        "role": "team_member",
        "weekly_capacity_hours": 40.0,
        "working_days": WORKING_DAYS_DEFAULT,
        "avatar_color": "#2196F3",
    },
    {
        "external_id": "user-alan",
        "display_name": "Alan Turing",
        "email": "alan@demo.com",
        "role": "team_member",
        # 32h/week (part-time — effectively 4 days out of 5)
        "weekly_capacity_hours": 32.0,
        "working_days": WORKING_DAYS_DEFAULT,
        "avatar_color": "#FF9800",
    },
]

DEMO_PROJECTS = [
    {
        "external_id": "proj-alpha",
        "name": "Project Alpha",
        "color": "#2196F3",
        "status": "active",
        "start_date": "2026-04-06",
        "end_date": "2026-06-30",
    },
    {
        "external_id": "proj-beta",
        "name": "Project Beta",
        "color": "#9C27B0",
        "status": "active",
        "start_date": "2026-04-06",
        "end_date": "2026-05-31",
    },
]

# Dates adjusted to use Sun–Thu week starting 2026-04-05 (Sunday)
DEMO_TASKS = [
    {
        "external_id": "task-alpha-001",
        "project_key": "proj-alpha",
        "name": "Discovery & Requirements",
        "status": "active",
        "scheduled_start_date": "2026-04-06",
        "scheduled_end_date": "2026-04-10",
        "estimated_hours": 16.0,
    },
    {
        "external_id": "task-alpha-002",
        "project_key": "proj-alpha",
        "name": "Architecture Design",
        "status": "active",
        "scheduled_start_date": "2026-04-13",
        "scheduled_end_date": "2026-04-17",
        "estimated_hours": 24.0,
    },
    {
        "external_id": "task-alpha-003",
        "project_key": "proj-alpha",
        "name": "Backend Implementation",
        "status": "active",
        "scheduled_start_date": "2026-04-20",
        "scheduled_end_date": "2026-05-01",
        "estimated_hours": 40.0,
    },
    {
        "external_id": "task-beta-001",
        "project_key": "proj-beta",
        "name": "UI Prototyping",
        "status": "active",
        "scheduled_start_date": "2026-04-06",
        "scheduled_end_date": "2026-04-13",
        "estimated_hours": 20.0,
    },
    {
        "external_id": "task-beta-002",
        "project_key": "proj-beta",
        "name": "Integration Testing",
        "status": "active",
        "scheduled_start_date": "2026-04-20",
        "scheduled_end_date": "2026-04-30",
        "estimated_hours": 30.0,
    },
]

# FS dependency chains:
#   Alpha: task-001 → task-002 → task-003
#   Beta:  task-001 → task-002
DEMO_DEPENDENCIES = [
    ("task-alpha-001", "task-alpha-002"),
    ("task-alpha-002", "task-alpha-003"),
    ("task-beta-001",  "task-beta-002"),
]

# (task_external_id, member_external_id, start_date, end_date, allocated_hours)
# allocated_hours is a placeholder; "Run Schedule" overwrites with engine output
DEMO_ASSIGNMENTS = [
    ("task-alpha-001", "user-ada",   "2026-04-06", "2026-04-10", 16.0),
    ("task-alpha-002", "user-ada",   "2026-04-13", "2026-04-17", 24.0),
    ("task-alpha-003", "user-grace", "2026-04-20", "2026-05-01", 40.0),
    ("task-alpha-003", "user-ada",   "2026-04-20", "2026-04-24", 16.0),
    ("task-beta-001",  "user-grace", "2026-04-06", "2026-04-13", 20.0),
    ("task-beta-001",  "user-alan",  "2026-04-06", "2026-04-10", 10.0),
    ("task-beta-002",  "user-alan",  "2026-04-20", "2026-04-30", 30.0),
    ("task-beta-002",  "user-grace", "2026-04-27", "2026-04-30", 8.0),
]

# (member_external_id, leave_type, start_date, end_date, note)
DEMO_TIME_OFFS = [
    ("user-grace", "annual",         "2026-04-15", "2026-04-16", "Spring break"),
    ("user-alan",  "public_holiday", "2026-04-14", "2026-04-14", "Public holiday"),
]

DEMO_USERS = [
    {
        "email": "manager@demo.com",
        "display_name": "Demo Manager",
        "role": "manager",
        "password": "password",
    },
    {
        "email": "member@demo.com",
        "display_name": "Demo Team Member",
        "role": "team_member",
        "password": "password",
    },
]


def seed_demo_data(session: "Session") -> None:
    """Populate demo data if the database is empty."""
    if session.query(Member).count() > 0:
        return  # already seeded

    # Members
    member_map: dict[str, Member] = {}
    for m in DEMO_MEMBERS:
        member = Member(
            external_id=m["external_id"],
            display_name=m["display_name"],
            email=m["email"],
            role=m["role"],
            weekly_capacity_hours=m["weekly_capacity_hours"],
            working_days=m["working_days"],
            avatar_color=m["avatar_color"],
        )
        session.add(member)
        member_map[m["external_id"]] = member

    session.flush()

    # Projects
    project_map: dict[str, Project] = {}
    for p in DEMO_PROJECTS:
        project = Project(
            external_id=p["external_id"],
            name=p["name"],
            color=p["color"],
            status=p["status"],
            start_date=p["start_date"],
            end_date=p["end_date"],
        )
        session.add(project)
        project_map[p["external_id"]] = project

    session.flush()

    # Tasks
    task_map: dict[str, Task] = {}
    for t in DEMO_TASKS:
        task = Task(
            external_id=t["external_id"],
            project_id=project_map[t["project_key"]].id,
            name=t["name"],
            status=t["status"],
            scheduled_start_date=t["scheduled_start_date"],
            scheduled_end_date=t["scheduled_end_date"],
            estimated_hours=t["estimated_hours"],
        )
        session.add(task)
        task_map[t["external_id"]] = task

    session.flush()

    # Task Dependencies
    for pred_ext_id, succ_ext_id in DEMO_DEPENDENCIES:
        dep = TaskDependency(
            predecessor_id=task_map[pred_ext_id].id,
            successor_id=task_map[succ_ext_id].id,
            dependency_type="FS",
        )
        session.add(dep)

    # Assignments (placeholder hours — engine will overwrite on "Run Schedule")
    for task_ext_id, member_ext_id, start, end, hours in DEMO_ASSIGNMENTS:
        assignment = Assignment(
            task_id=task_map[task_ext_id].id,
            member_id=member_map[member_ext_id].id,
            allocated_hours=hours,
            start_date=start,
            end_date=end,
            field_overrides={"source": "seed"},
        )
        session.add(assignment)

    # Time Off
    for member_ext_id, leave_type, start, end, note in DEMO_TIME_OFFS:
        time_off = TimeOff(
            member_id=member_map[member_ext_id].id,
            leave_type=leave_type,
            start_date=start,
            end_date=end,
            note=note,
        )
        session.add(time_off)

    # Users
    for u in DEMO_USERS:
        password_hash = bcrypt.hashpw(
            u["password"].encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        user = User(
            email=u["email"],
            display_name=u["display_name"],
            role=u["role"],
            password_hash=password_hash,
        )
        session.add(user)

    session.commit()
