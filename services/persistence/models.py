"""SQLAlchemy ORM models for the Float-replacement persistence layer."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _utcnow():
    return datetime.now(timezone.utc)


def _default_working_days():
    return ["Sun", "Mon", "Tue", "Wed", "Thu"]


class Member(Base):
    """A team member (resource) that can be assigned to tasks."""
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(128), unique=True, nullable=False, index=True)
    display_name = Column(String(256), nullable=False)
    email = Column(String(256), unique=True, nullable=True)
    role = Column(String(64), nullable=False, default="team_member")  # manager | team_member
    weekly_capacity_hours = Column(Float, nullable=False, default=40.0)
    # Working days as short names: "Sun","Mon","Tue","Wed","Thu","Fri","Sat"
    # Default: Sunday–Thursday (Middle East work week)
    working_days = Column(JSON, nullable=False, default=_default_working_days)
    avatar_color = Column(String(16), nullable=False, default="#4A90D9")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    assignments = relationship("Assignment", back_populates="member", cascade="all, delete-orphan")
    time_offs = relationship("TimeOff", back_populates="member", cascade="all, delete-orphan")


class Project(Base):
    """A project that groups tasks."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(128), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False)
    color = Column(String(16), nullable=False, default="#2196F3")
    status = Column(String(64), nullable=False, default="active")  # active | archived
    start_date = Column(String(16), nullable=True)   # ISO date string YYYY-MM-DD
    end_date = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    asana_project_gid = Column(String(128), nullable=True)

    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    project_members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")


class Task(Base):
    """A task that can be assigned to members."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(128), unique=True, nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    hierarchy_depth = Column(Integer, nullable=False, default=0)
    name = Column(String(512), nullable=False)
    status = Column(String(64), nullable=False, default="active")  # active | completed | cancelled
    scheduled_start_date = Column(String(16), nullable=True)
    scheduled_end_date = Column(String(16), nullable=True)
    estimated_hours = Column(Float, nullable=True)
    buffer_hours = Column(Float, nullable=True, default=None)
    # Stores manual edits on top of imported values.
    # Read-path: effective_value = field_overrides.get(field) or imported_value
    field_overrides = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    project = relationship("Project", back_populates="tasks")
    parent = relationship("Task", back_populates="children", remote_side="Task.id", foreign_keys="[Task.parent_id]")
    children = relationship("Task", back_populates="parent", foreign_keys="[Task.parent_id]")
    assignments = relationship("Assignment", back_populates="task", cascade="all, delete-orphan")
    day_allocations = relationship("DayAllocation", back_populates="task", cascade="all, delete-orphan")
    # Tasks this task depends on (predecessors)
    predecessor_links = relationship(
        "TaskDependency",
        foreign_keys="TaskDependency.successor_id",
        back_populates="successor",
        cascade="all, delete-orphan",
    )
    # Tasks that depend on this task (successors)
    successor_links = relationship(
        "TaskDependency",
        foreign_keys="TaskDependency.predecessor_id",
        back_populates="predecessor",
        cascade="all, delete-orphan",
    )


class TaskDependency(Base):
    """Finish-to-Start (and other) dependency links between tasks."""
    __tablename__ = "task_dependencies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    predecessor_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    successor_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    # FS = Finish-to-Start (default), SS = Start-to-Start,
    # FF = Finish-to-Finish, SF = Start-to-Finish
    dependency_type = Column(String(4), nullable=False, default="FS")

    __table_args__ = (UniqueConstraint("predecessor_id", "successor_id", name="uq_task_dependency"),)

    predecessor = relationship("Task", foreign_keys=[predecessor_id], back_populates="successor_links")
    successor = relationship("Task", foreign_keys=[successor_id], back_populates="predecessor_links")


class Assignment(Base):
    """Links a member to a task for a specific date range with allocated hours."""
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    allocated_hours = Column(Float, nullable=False, default=0.0)
    start_date = Column(String(16), nullable=False)   # YYYY-MM-DD
    end_date = Column(String(16), nullable=False)     # YYYY-MM-DD
    # field_overrides tracks source and manual edits:
    #   {"source": "engine"} → written by planning engine (can be overwritten)
    #   {"source": "engine", "manual": true} → manually edited, engine respects as constraint
    #   {"allocation_percent": 50} → allocation weight hint for engine
    field_overrides = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    task = relationship("Task", back_populates="assignments")
    member = relationship("Member", back_populates="assignments")


class TimeOff(Base):
    """A time-off entry for a member (leave, public holiday, etc.)."""
    __tablename__ = "time_off"

    id = Column(Integer, primary_key=True, autoincrement=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    leave_type = Column(String(64), nullable=False, default="annual")
    # annual | sick | public_holiday | custom
    start_date = Column(String(16), nullable=False)  # YYYY-MM-DD
    end_date = Column(String(16), nullable=False)    # YYYY-MM-DD
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    member = relationship("Member", back_populates="time_offs")


class DayAllocation(Base):
    """Per-day allocation of a task to a member — written by engine or manual drag."""
    __tablename__ = "day_allocations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    date = Column(String(10), nullable=False)    # "YYYY-MM-DD"
    hours = Column(Float, nullable=False)
    # "engine" = written by scheduling engine (replaceable on next run)
    # "manual" = manually reassigned by user
    source = Column(String(20), nullable=False, default="engine")
    # pinned = True means engine must respect this allocation as a hard constraint
    # Only meaningful for source="manual". Unpinned manual allocs are replaced on Run Schedule.
    pinned = Column(Boolean, nullable=False, default=False)

    __table_args__ = (UniqueConstraint("task_id", "member_id", "date", name="uq_day_allocation"),)

    task = relationship("Task", back_populates="day_allocations")
    member = relationship("Member")


class PlanningRun(Base):
    """Tracks scheduling engine runs (replaces in-memory workflow orchestrator)."""
    __tablename__ = "planning_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), unique=True, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")  # pending|running|succeeded|failed
    triggered_at = Column(String(30), nullable=False)
    completed_at = Column(String(30), nullable=True)
    ghost_task_count = Column(Integer, nullable=False, default=0)
    written_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)


class AppConfig(Base):
    """Key-value store for application configuration (e.g. Asana PAT, project GID)."""
    __tablename__ = "app_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class ProjectMember(Base):
    """Associates a member with a project (team membership, not task assignment)."""
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False)
    role = Column(String(64), nullable=True)
    added_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (UniqueConstraint("project_id", "member_id", name="uq_project_member"),)

    project = relationship("Project", back_populates="project_members")
    member = relationship("Member")


class User(Base):
    """An application user that can log in."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(256), unique=True, nullable=False, index=True)
    display_name = Column(String(256), nullable=False)
    role = Column(String(64), nullable=False, default="team_member")  # manager | team_member
    password_hash = Column(String(512), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
