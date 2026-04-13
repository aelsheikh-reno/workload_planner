"""People & Projects CRUD service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.persistence import get_db_session
from services.persistence.models import Assignment, Member, Project, Task


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _member_to_dict(m: Member) -> Dict[str, Any]:
    return {
        "id": m.id,
        "external_id": m.external_id,
        "display_name": m.display_name,
        "email": m.email,
        "role": m.role,
        "weekly_capacity_hours": m.weekly_capacity_hours,
        "working_days": m.working_days,
        "avatar_color": m.avatar_color,
        "is_active": m.is_active,
    }


def _project_to_dict(p: Project, task_count: int = 0) -> Dict[str, Any]:
    return {
        "id": p.id,
        "external_id": p.external_id,
        "name": p.name,
        "color": p.color,
        "status": p.status,
        "start_date": p.start_date,
        "end_date": p.end_date,
        "task_count": task_count,
        "asana_project_gid": p.asana_project_gid,
    }


def _task_to_dict(t: Task) -> Dict[str, Any]:
    return {
        "id": t.id,
        "external_id": t.external_id,
        "project_id": t.project_id,
        "name": t.name,
        "status": t.status,
        "scheduled_start_date": t.scheduled_start_date,
        "scheduled_end_date": t.scheduled_end_date,
        "estimated_hours": t.estimated_hours,
        "field_overrides": t.field_overrides or {},
    }


class PeopleService:
    # ── Members ────────────────────────────────────────────────────────────

    def list_members(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            q = session.query(Member)
            if not include_inactive:
                q = q.filter_by(is_active=True)
            return [_member_to_dict(m) for m in q.order_by(Member.display_name).all()]

    def get_member(self, member_id: int) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            m = session.query(Member).filter_by(id=member_id, is_active=True).first()
            return _member_to_dict(m) if m else None

    def create_member(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with get_db_session() as session:
            member = Member(
                external_id=data.get("external_id") or f"user-{uuid.uuid4().hex[:8]}",
                display_name=data["display_name"],
                email=data.get("email"),
                role=data.get("role", "team_member"),
                weekly_capacity_hours=float(data.get("weekly_capacity_hours", 40.0)),
                avatar_color=data.get("avatar_color", "#4A90D9"),
            )
            session.add(member)
            session.flush()
            return _member_to_dict(member)

    def update_member(self, member_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            member = session.query(Member).filter_by(id=member_id).first()
            if member is None:
                return None
            for field in ("display_name", "email", "role", "weekly_capacity_hours", "avatar_color", "working_days"):
                if field in data:
                    setattr(member, field, data[field])
            session.flush()
            return _member_to_dict(member)

    def deactivate_member(self, member_id: int) -> bool:
        with get_db_session() as session:
            member = session.query(Member).filter_by(id=member_id).first()
            if member is None:
                return False
            member.is_active = False
            return True

    # ── Projects ───────────────────────────────────────────────────────────

    def list_projects(self, include_archived: bool = False) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            q = session.query(Project)
            if not include_archived:
                q = q.filter_by(status="active")
            projects = q.order_by(Project.name).all()
            result = []
            for p in projects:
                count = session.query(Task).filter_by(project_id=p.id, status="active").count()
                result.append(_project_to_dict(p, task_count=count))
            return result

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            p = session.query(Project).filter_by(id=project_id).first()
            if p is None:
                return None
            count = session.query(Task).filter_by(project_id=p.id, status="active").count()
            return _project_to_dict(p, task_count=count)

    def create_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with get_db_session() as session:
            project = Project(
                external_id=data.get("external_id") or f"proj-{uuid.uuid4().hex[:8]}",
                name=data["name"],
                color=data.get("color", "#2196F3"),
                status=data.get("status", "active"),
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
            )
            session.add(project)
            session.flush()
            return _project_to_dict(project)

    def update_project(self, project_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            project = session.query(Project).filter_by(id=project_id).first()
            if project is None:
                return None
            for field in ("name", "color", "status", "start_date", "end_date", "asana_project_gid"):
                if field in data:
                    setattr(project, field, data[field])
            session.flush()
            count = session.query(Task).filter_by(project_id=project.id, status="active").count()
            return _project_to_dict(project, task_count=count)

    def archive_project(self, project_id: int) -> bool:
        with get_db_session() as session:
            project = session.query(Project).filter_by(id=project_id).first()
            if project is None:
                return False
            project.status = "archived"
            return True

    def delete_project(self, project_id: int) -> bool:
        """Hard-delete a project and all its tasks, dependencies, and assignments."""
        with get_db_session() as session:
            project = session.query(Project).filter_by(id=project_id).first()
            if project is None:
                return False
            session.delete(project)
            return True

    # ── Tasks ──────────────────────────────────────────────────────────────

    def list_tasks(
        self,
        project_id: Optional[int] = None,
        member_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with get_db_session() as session:
            q = session.query(Task).filter(Task.status != "cancelled")
            if project_id is not None:
                q = q.filter_by(project_id=project_id)
            if member_id is not None:
                # tasks that have at least one assignment for this member
                task_ids = [
                    a.task_id
                    for a in session.query(Assignment.task_id).filter_by(member_id=member_id).distinct()
                ]
                q = q.filter(Task.id.in_(task_ids))
            return [_task_to_dict(t) for t in q.order_by(Task.scheduled_start_date).all()]

    def create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with get_db_session() as session:
            task = Task(
                external_id=data.get("external_id") or f"task-{uuid.uuid4().hex[:8]}",
                project_id=data["project_id"],
                name=data["name"],
                status=data.get("status", "active"),
                scheduled_start_date=data.get("scheduled_start_date"),
                scheduled_end_date=data.get("scheduled_end_date"),
                estimated_hours=data.get("estimated_hours"),
            )
            session.add(task)
            session.flush()
            return _task_to_dict(task)

    def update_task(self, task_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            task = session.query(Task).filter_by(id=task_id).first()
            if task is None:
                return None
            # Plain fields
            for field in ("name", "status", "estimated_hours"):
                if field in data:
                    setattr(task, field, data[field])
            # Date fields go into field_overrides to preserve import values
            overrides = dict(task.field_overrides or {})
            for date_field in ("scheduled_start_date", "scheduled_end_date"):
                if date_field in data:
                    overrides[date_field] = data[date_field]
                    setattr(task, date_field, data[date_field])
            task.field_overrides = overrides
            session.flush()
            return _task_to_dict(task)
