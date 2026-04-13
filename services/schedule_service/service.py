"""Schedule calendar service — builds weekly/monthly views and handles drag-drop mutations."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from services.persistence import get_db_session
from services.persistence.models import Assignment, Member, Project, Task, TimeOff


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_date(d: str) -> date:
    return date.fromisoformat(d)


_DEFAULT_WORKING_DAYS = {"Sun", "Mon", "Tue", "Wed", "Thu"}


def _date_range(start: date, end: date, working_days: Optional[set] = None) -> List[date]:
    """Return all dates from start to end (inclusive).

    If working_days is provided, skip days not in the set (e.g. {"Sun","Mon","Tue","Wed","Thu"}).
    """
    wd = working_days if working_days is not None else _DEFAULT_WORKING_DAYS
    days = []
    current = start
    while current <= end:
        if current.strftime("%a") in wd:
            days.append(current)
        current += timedelta(days=1)
    return days


def _week_start(d: date) -> date:
    """Return the Sunday of the week containing d (Middle East week starts Sunday)."""
    # weekday(): Mon=0, ..., Sun=6
    days_since_sunday = (d.weekday() + 1) % 7
    return d - timedelta(days=days_since_sunday)


def _format_date(d: date) -> str:
    return d.isoformat()


def _col_label(d: date) -> str:
    return d.strftime("%a %-d %b")


def _assignment_to_dict(a: Assignment) -> Dict[str, Any]:
    task = a.task
    project = task.project if task else None
    # Merge field_overrides on top of base values
    overrides = a.field_overrides or {}
    return {
        "id": a.id,
        "task_id": a.task_id,
        "task_name": task.name if task else "",
        "task_external_id": task.external_id if task else "",
        "project_id": project.id if project else None,
        "project_name": project.name if project else "",
        "project_color": project.color if project else "#9E9E9E",
        "member_id": a.member_id,
        "allocated_hours": overrides.get("allocated_hours", a.allocated_hours),
        "start_date": overrides.get("start_date", a.start_date),
        "end_date": overrides.get("end_date", a.end_date),
        "has_overrides": bool(overrides),
    }


def _time_off_to_dict(t: TimeOff) -> Dict[str, Any]:
    return {
        "id": t.id,
        "member_id": t.member_id,
        "leave_type": t.leave_type,
        "start_date": t.start_date,
        "end_date": t.end_date,
        "note": t.note,
    }


def _utilization_tone(allocated: float, capacity: float) -> str:
    if capacity <= 0:
        return "neutral"
    ratio = allocated / capacity
    if ratio >= 1.0:
        return "red"
    if ratio >= 0.8:
        return "amber"
    return "green"


# ── Service ───────────────────────────────────────────────────────────────────


class ScheduleService:
    def build_calendar_view(
        self,
        view_type: str = "week",
        anchor_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the full calendar payload for the given view and date."""
        today = date.today()
        anchor = _parse_date(anchor_date) if anchor_date else today

        if view_type == "week":
            start = _week_start(anchor)
            end = start + timedelta(days=4)  # Sun–Thu (5 working days)
        else:  # month
            start = anchor.replace(day=1)
            # end of month (find first day of next month, subtract 1)
            if start.month == 12:
                end = date(start.year + 1, 1, 1) - timedelta(days=1)
            else:
                end = date(start.year, start.month + 1, 1) - timedelta(days=1)

        working_days = _date_range(start, end)
        columns = [{"date": _format_date(d), "label": _col_label(d)} for d in working_days]
        day_set = {_format_date(d) for d in working_days}

        with get_db_session() as session:
            members = (
                session.query(Member)
                .filter_by(is_active=True)
                .order_by(Member.display_name)
                .all()
            )

            # Load assignments that overlap with the view window
            assignments = (
                session.query(Assignment)
                .join(Assignment.task)
                .join(Task.project)
                .filter(
                    Assignment.start_date <= _format_date(end),
                    Assignment.end_date >= _format_date(start),
                )
                .all()
            )

            # Load time-off entries that overlap
            time_offs = (
                session.query(TimeOff)
                .filter(
                    TimeOff.start_date <= _format_date(end),
                    TimeOff.end_date >= _format_date(start),
                )
                .all()
            )

            # Index by member_id
            assignments_by_member: Dict[int, List[Assignment]] = {}
            for a in assignments:
                assignments_by_member.setdefault(a.member_id, []).append(a)

            time_offs_by_member: Dict[int, List[TimeOff]] = {}
            for t in time_offs:
                time_offs_by_member.setdefault(t.member_id, []).append(t)

            rows = []
            for member in members:
                member_assignments = assignments_by_member.get(member.id, [])
                member_time_offs = time_offs_by_member.get(member.id, [])
                member_working_days = set(member.working_days or _DEFAULT_WORKING_DAYS)
                daily_capacity = member.weekly_capacity_hours / max(len(member_working_days), 1)

                daily_hours: Dict[str, float] = {d: 0.0 for d in day_set}
                daily_assignments: Dict[str, List[Dict[str, Any]]] = {d: [] for d in day_set}
                daily_time_off: Dict[str, Optional[Dict[str, Any]]] = {d: None for d in day_set}

                # Place assignments into day buckets
                for a in member_assignments:
                    a_start = _parse_date(a.start_date)
                    a_end = _parse_date(a.end_date)
                    a_days = _date_range(a_start, a_end, member_working_days)
                    if not a_days:
                        continue
                    hours_per_day = a.allocated_hours / len(a_days)
                    a_dict = _assignment_to_dict(a)
                    for d in a_days:
                        key = _format_date(d)
                        if key in day_set:
                            daily_assignments[key].append({**a_dict, "hours_per_day": round(hours_per_day, 1)})
                            daily_hours[key] += hours_per_day

                # Place time-off into day buckets
                for t in member_time_offs:
                    t_start = _parse_date(t.start_date)
                    t_end = _parse_date(t.end_date)
                    for d in _date_range(t_start, t_end, member_working_days):
                        key = _format_date(d)
                        if key in day_set:
                            daily_time_off[key] = _time_off_to_dict(t)

                cells = []
                for d in working_days:
                    key = _format_date(d)
                    allocated = round(daily_hours[key], 1)
                    cells.append({
                        "date": key,
                        "assignments": daily_assignments[key],
                        "time_off": daily_time_off[key],
                        "total_allocated_hours": allocated,
                        "capacity_hours": daily_capacity,
                        "utilization_pct": round((allocated / daily_capacity * 100) if daily_capacity > 0 else 0),
                        "tone": _utilization_tone(allocated, daily_capacity),
                    })

                rows.append({
                    "member": {
                        "id": member.id,
                        "external_id": member.external_id,
                        "display_name": member.display_name,
                        "avatar_color": member.avatar_color,
                        "weekly_capacity_hours": member.weekly_capacity_hours,
                    },
                    "cells": cells,
                })

        return {
            "view_config": {
                "type": view_type,
                "start_date": _format_date(start),
                "end_date": _format_date(end),
                "anchor_date": _format_date(anchor),
            },
            "columns": columns,
            "rows": rows,
        }

    def create_assignment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with get_db_session() as session:
            assignment = Assignment(
                task_id=data["task_id"],
                member_id=data["member_id"],
                allocated_hours=float(data.get("allocated_hours", 8.0)),
                start_date=data["start_date"],
                end_date=data["end_date"],
            )
            session.add(assignment)
            session.flush()
            # Refresh with relationships
            session.refresh(assignment)
            return _assignment_to_dict(assignment)

    def move_assignment(self, assignment_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Drag-drop: update start_date, end_date, and optionally member_id."""
        with get_db_session() as session:
            a = session.query(Assignment).filter_by(id=assignment_id).first()
            if a is None:
                return None
            overrides = dict(a.field_overrides or {})
            if "new_start_date" in data:
                a.start_date = data["new_start_date"]
                overrides["start_date"] = data["new_start_date"]
            if "new_end_date" in data:
                a.end_date = data["new_end_date"]
                overrides["end_date"] = data["new_end_date"]
            if "new_member_id" in data:
                a.member_id = data["new_member_id"]
            a.field_overrides = overrides
            session.flush()
            session.refresh(a)
            return _assignment_to_dict(a)

    def update_assignment(self, assignment_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Resize/edit an assignment."""
        with get_db_session() as session:
            a = session.query(Assignment).filter_by(id=assignment_id).first()
            if a is None:
                return None
            overrides = dict(a.field_overrides or {})
            if "allocated_hours" in data:
                a.allocated_hours = float(data["allocated_hours"])
                overrides["allocated_hours"] = float(data["allocated_hours"])
            if "start_date" in data:
                a.start_date = data["start_date"]
                overrides["start_date"] = data["start_date"]
            if "end_date" in data:
                a.end_date = data["end_date"]
                overrides["end_date"] = data["end_date"]
            if "member_id" in data:
                a.member_id = data["member_id"]
            a.field_overrides = overrides
            session.flush()
            session.refresh(a)
            return _assignment_to_dict(a)

    def delete_assignment(self, assignment_id: int) -> bool:
        with get_db_session() as session:
            a = session.query(Assignment).filter_by(id=assignment_id).first()
            if a is None:
                return False
            session.delete(a)
            return True

    def get_assignment(self, assignment_id: int) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            a = (
                session.query(Assignment)
                .join(Assignment.task)
                .join(Task.project)
                .filter(Assignment.id == assignment_id)
                .first()
            )
            return _assignment_to_dict(a) if a else None
