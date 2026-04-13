"""FloatApplication — SQLite-backed resource scheduling API.

All routes live under /api/float/*, /api/auth/*, /api/projects/*, /api/schedule/*,
/api/import, and /api/asana/*.

One database (float_planner.db), one backend, no in-memory workflow state.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs

from .transport import (
    JSON_HEADERS,
    ApiGatewayTransportError,
    _http_status_text,
    _read_json_body,
)
from services.auth_service import AuthError, AuthService
from services.people_service import PeopleService
from services.people_service.import_mapper import ImportToFloatMapper
from services.planning_engine_service import PlanningEngineService
from services.schedule_service import ScheduleService
from services.time_off_service import TimeOffService
from services.persistence import create_all_tables, get_db_session, seed_demo_data
from services.persistence.models import (
    AppConfig,
    DayAllocation,
    Member,
    PlanningRun,
    Project,
    Task,
    TaskDependency,
    Assignment,
)


# ── Route pattern matching ─────────────────────────────────────────────────────

class _Route:
    """A URL pattern that may include {name} path parameters."""
    def __init__(self, pattern: str) -> None:
        self._pattern = pattern
        self._regex = re.compile(
            "^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", re.escape(pattern)
                         .replace(r"\{", "{").replace(r"\}", "}")) + "$"
        )
        # Fix: re.escape escapes braces — redo substitution on raw pattern
        self._regex = re.compile(
            "^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern) + "$"
        )

    def match(self, path: str) -> Optional[Dict[str, str]]:
        m = self._regex.match(path)
        return m.groupdict() if m else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sync_task_dates_from_allocations(session, task_id: int) -> None:
    """Recalculate task scheduled_start_date and scheduled_end_date from DayAllocations.

    Effort stays unchanged — only dates are derived from actual allocations.
    """
    from sqlalchemy import func as sa_func
    task = session.query(Task).filter_by(id=task_id).first()
    if task is None:
        return
    min_date = session.query(sa_func.min(DayAllocation.date)).filter_by(task_id=task_id).scalar()
    max_date = session.query(sa_func.max(DayAllocation.date)).filter_by(task_id=task_id).scalar()
    if min_date:
        task.scheduled_start_date = min_date
    if max_date:
        task.scheduled_end_date = max_date


def _greedy_place(session, task_id, member_id, start_date_str, total_hours,
                  daily_cap, working_days_set, time_off_dates):
    """Place total_hours greedily on consecutive working days starting from start_date.

    Each day gets min(available_capacity, remaining_hours) where available capacity
    is daily_cap minus hours already committed by OTHER tasks for this member.

    Returns list of (date_str, hours) tuples.
    """
    from datetime import date as date_cls, timedelta
    from sqlalchemy import func as sa_func

    _day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    placements = []
    remaining = round(total_hours, 2)
    cursor = date_cls.fromisoformat(start_date_str)
    max_days = 365

    for _ in range(max_days):
        if remaining <= 0.01:
            break
        ds = cursor.isoformat()
        # Skip non-working days
        if _day_names[cursor.weekday()] not in working_days_set:
            cursor += timedelta(days=1)
            continue
        # Skip time-off days
        if ds in time_off_dates:
            cursor += timedelta(days=1)
            continue

        # Query committed hours for this member on this day (exclude current task)
        committed = session.query(
            sa_func.coalesce(sa_func.sum(DayAllocation.hours), 0.0)
        ).filter(
            DayAllocation.member_id == member_id,
            DayAllocation.date == ds,
            DayAllocation.task_id != task_id,
        ).scalar() or 0.0

        available = max(0.0, daily_cap - float(committed))
        if available <= 0.01:
            cursor += timedelta(days=1)
            continue

        alloc_hours = round(min(available, remaining), 2)
        placements.append((ds, alloc_hours))
        remaining = round(remaining - alloc_hours, 2)
        cursor += timedelta(days=1)

    return placements


# ── FloatApplication ───────────────────────────────────────────────────────────

class FloatApplication:
    """Single-database WSGI application for the resource scheduling tool."""

    def __init__(self) -> None:
        create_all_tables()
        seed_demo_data()

        self._auth_svc = AuthService()
        self._people_svc = PeopleService()
        self._schedule_svc = ScheduleService()
        self._time_off_svc = TimeOffService()
        self._engine_svc = PlanningEngineService()
        self._import_mapper = ImportToFloatMapper()

        self._routes: List[Tuple[str, _Route, Callable]] = [
            # ── Auth ──────────────────────────────────────────────────────────
            ("POST",   _Route("/api/auth/login"),                          self._handle_auth_login),
            ("GET",    _Route("/api/auth/me"),                             self._handle_auth_me),
            # ── Members ───────────────────────────────────────────────────────
            ("GET",    _Route("/api/float/members"),                        self._handle_list_members),
            ("POST",   _Route("/api/float/members"),                        self._handle_create_member),
            ("PATCH",  _Route("/api/float/members/{id}"),                   self._handle_update_member),
            ("DELETE", _Route("/api/float/members/{id}"),                   self._handle_delete_member),
            # ── Projects ──────────────────────────────────────────────────────
            ("GET",    _Route("/api/float/projects"),                       self._handle_list_projects),
            ("GET",    _Route("/api/float/projects/{id}"),                  self._handle_get_project),
            ("POST",   _Route("/api/float/projects"),                       self._handle_create_project),
            ("PATCH",  _Route("/api/float/projects/{id}"),                  self._handle_update_project),
            ("DELETE", _Route("/api/float/projects/{id}"),                  self._handle_archive_project),
            # ── Tasks ─────────────────────────────────────────────────────────
            ("GET",    _Route("/api/float/tasks"),                          self._handle_list_tasks),
            ("POST",   _Route("/api/float/tasks"),                          self._handle_create_task),
            ("PATCH",  _Route("/api/float/tasks/{id}"),                     self._handle_update_task),
            # ── Schedule calendar ─────────────────────────────────────────────
            ("GET",    _Route("/api/float/schedule"),                       self._handle_get_schedule),
            ("GET",    _Route("/api/schedule/calendar"),                    self._handle_get_day_calendar),
            ("POST",   _Route("/api/float/schedule/assignments"),            self._handle_create_assignment),
            ("POST",   _Route("/api/float/schedule/assignments/{id}/move"), self._handle_move_assignment),
            ("PATCH",  _Route("/api/float/schedule/assignments/{id}"),      self._handle_update_assignment),
            ("DELETE", _Route("/api/float/schedule/assignments/{id}"),      self._handle_delete_assignment),
            # ── Time off ──────────────────────────────────────────────────────
            ("GET",    _Route("/api/float/time-off"),                       self._handle_list_time_off),
            ("POST",   _Route("/api/float/time-off"),                       self._handle_create_time_off),
            ("PATCH",  _Route("/api/float/time-off/{id}"),                  self._handle_update_time_off),
            ("DELETE", _Route("/api/float/time-off/{id}"),                  self._handle_delete_time_off),
            # ── Import ────────────────────────────────────────────────────────
            ("POST",   _Route("/api/import"),                               self._handle_import),
            ("POST",   _Route("/api/import/asana"),                         self._handle_import_from_asana),
            ("POST",   _Route("/api/import/asana/stream"),                  self._handle_import_from_asana_stream),
            ("POST",   _Route("/api/import/preview"),                       self._handle_import_preview),
            ("POST",   _Route("/api/import/apply"),                        self._handle_import_apply),
            ("POST",   _Route("/api/import/stream"),                        self._handle_import_stream),
            # ── Scheduling engine ─────────────────────────────────────────────
            ("POST",   _Route("/api/schedule/run"),                         self._handle_run_schedule),
            ("GET",    _Route("/api/schedule/runs"),                        self._handle_list_runs),
            # ── Day-level reassignment ────────────────────────────────────────
            ("POST",   _Route("/api/schedule/reassign-day"),                self._handle_reassign_day),
            ("POST",   _Route("/api/schedule/reassign-chunk"),              self._handle_reassign_chunk),
            ("POST",   _Route("/api/schedule/clear"),                       self._handle_clear_schedule),
            ("POST",   _Route("/api/schedule/reset"),                       self._handle_reset_to_import),
            ("POST",   _Route("/api/schedule/pin"),                         self._handle_pin_allocation),
            ("POST",   _Route("/api/schedule/pin-task"),                    self._handle_pin_task),
            # ── Asana sync ────────────────────────────────────────────────────
            ("GET",    _Route("/api/asana/pull-preview"),                   self._handle_asana_pull_preview),
            ("POST",   _Route("/api/asana/pull-apply"),                     self._handle_asana_pull_apply),
            ("POST",   _Route("/api/asana/push"),                           self._handle_asana_push),
            # ── Per-project operations ───────────────────────────────────────
            ("POST",   _Route("/api/float/projects/{id}/push-asana"),       self._handle_project_push_asana),
            ("POST",   _Route("/api/float/projects/{id}/shift-start"),      self._handle_shift_project_start),
            ("GET",    _Route("/api/float/projects/{id}/members"),          self._handle_list_project_members),
            ("POST",   _Route("/api/float/projects/{id}/members"),          self._handle_add_project_members),
            ("DELETE", _Route("/api/float/projects/{id}/members/{member_id}"), self._handle_remove_project_member),
            # ── Settings ──────────────────────────────────────────────────────
            ("GET",    _Route("/api/settings"),                             self._handle_get_settings),
            ("POST",   _Route("/api/settings"),                             self._handle_post_settings),
            # ── Asana setup helpers ───────────────────────────────────────────
            ("GET",    _Route("/api/asana/workspaces"),                     self._handle_asana_workspaces),
            ("GET",    _Route("/api/asana/projects"),                       self._handle_asana_projects),
            # ── Member sync ───────────────────────────────────────────────────
            ("GET",    _Route("/api/asana/members/preview"),                self._handle_asana_members_preview),
            ("POST",   _Route("/api/asana/members/apply"),                  self._handle_asana_members_apply),
            # ── Health ────────────────────────────────────────────────────────
            ("GET",    _Route("/health"),                                   self._handle_health),
        ]

    # ── WSGI entry point ───────────────────────────────────────────────────────

    def __call__(self, environ: Dict[str, Any], start_response) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=False)

        for route_method, route_pattern, handler in self._routes:
            if method != route_method:
                continue
            path_params = route_pattern.match(path)
            if path_params is None:
                continue

            # For /api/import, read raw bytes (XML or JSON)
            if path in ("/api/import", "/api/import/stream", "/api/import/preview") and method == "POST":
                body = _read_raw_body(environ)
            else:
                body = _read_json_body(
                    body_stream=environ.get("wsgi.input"),
                    content_length=environ.get("CONTENT_LENGTH"),
                )

            try:
                result = handler(environ, path_params, query, body)
            except AuthError as exc:
                status_code, payload = exc.status, {"error": str(exc)}
                response_body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
                start_response("%d %s" % (status_code, _http_status_text(status_code)),
                               JSON_HEADERS + [("Content-Length", str(len(response_body)))])
                return [response_body]
            except ApiGatewayTransportError as exc:
                status_code = exc.status_code
                payload = {"error": {"code": exc.code, "message": exc.message}}
                response_body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
                start_response("%d %s" % (status_code, _http_status_text(status_code)),
                               JSON_HEADERS + [("Content-Length", str(len(response_body)))])
                return [response_body]
            except (ValueError, Exception) as exc:
                status_code = 400 if isinstance(exc, ValueError) else 500
                payload = {"error": str(exc)}
                response_body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
                start_response("%d %s" % (status_code, _http_status_text(status_code)),
                               JSON_HEADERS + [("Content-Length", str(len(response_body)))])
                return [response_body]

            # SSE streaming: handler returns ("SSE", generator)
            if isinstance(result, tuple) and len(result) == 2 and result[0] == "SSE":
                start_response("200 OK", [
                    ("Content-Type", "text/event-stream"),
                    ("Cache-Control", "no-cache"),
                    ("Access-Control-Allow-Origin", "*"),
                ])
                return result[1]

            status_code, payload = result

            response_body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
            start_response(
                "%d %s" % (status_code, _http_status_text(status_code)),
                JSON_HEADERS + [("Content-Length", str(len(response_body)))],
            )
            return [response_body]

        # 404
        response_body = json.dumps({"error": "Not found"}).encode("utf-8")
        start_response("404 Not Found", JSON_HEADERS + [("Content-Length", str(len(response_body)))])
        return [response_body]

    # ── Auth helpers ───────────────────────────────────────────────────────────

    def _current_user(self, environ):
        auth = environ.get("HTTP_AUTHORIZATION", "")
        if auth.startswith("Bearer "):
            try:
                return self._auth_svc.get_user_from_token(auth[7:])
            except Exception:
                return None
        return None

    def _require_auth(self, environ):
        user = self._current_user(environ)
        if user is None:
            raise AuthError("Authentication required.", status=401)
        return user

    # ── Auth handlers ──────────────────────────────────────────────────────────

    def _handle_auth_login(self, environ, path_params, query, body):
        data = body or {}
        email = data.get("email", "")
        password = data.get("password", "")
        if not email or not password:
            return 400, {"error": "email and password are required."}
        result = self._auth_svc.login(email, password)
        return 200, result

    def _handle_auth_me(self, environ, path_params, query, body):
        user = self._require_auth(environ)
        return 200, {"user": user}

    # ── Health ─────────────────────────────────────────────────────────────────

    def _handle_health(self, environ, path_params, query, body):
        return 200, {"status": "ok"}

    # ── Member handlers ────────────────────────────────────────────────────────

    def _handle_list_members(self, environ, path_params, query, body):
        include_inactive = query.get("includeInactive", ["false"])[0].lower() == "true"
        members = self._people_svc.list_members(include_inactive=include_inactive)
        return 200, {"members": members}

    def _handle_create_member(self, environ, path_params, query, body):
        self._require_auth(environ)
        data = body or {}
        if not data.get("display_name"):
            return 400, {"error": "display_name is required."}
        member = self._people_svc.create_member(data)
        return 201, {"member": member}

    def _handle_update_member(self, environ, path_params, query, body):
        self._require_auth(environ)
        member = self._people_svc.update_member(int(path_params["id"]), body or {})
        if member is None:
            return 404, {"error": "Member not found."}
        return 200, {"member": member}

    def _handle_delete_member(self, environ, path_params, query, body):
        self._require_auth(environ)
        ok = self._people_svc.deactivate_member(int(path_params["id"]))
        if not ok:
            return 404, {"error": "Member not found."}
        return 200, {"ok": True}

    # ── Project handlers ───────────────────────────────────────────────────────

    def _handle_list_projects(self, environ, path_params, query, body):
        include_archived = query.get("includeArchived", ["false"])[0].lower() == "true"
        projects = self._people_svc.list_projects(include_archived=include_archived)
        return 200, {"projects": projects}

    def _handle_get_project(self, environ, path_params, query, body):
        project_id = int(path_params["id"])
        with get_db_session() as session:
            from services.persistence.models import ProjectMember
            project = session.query(Project).filter_by(id=project_id).first()
            if project is None:
                return 404, {"error": "Project not found."}
            tasks = session.query(Task).filter_by(project_id=project_id).all()
            # Collect members from assignments AND project_members
            member_ids = set()
            for task in tasks:
                assigns = session.query(Assignment).filter_by(task_id=task.id).all()
                for a in assigns:
                    member_ids.add(a.member_id)
            # Also include members from ProjectMember table
            pm_rows = session.query(ProjectMember).filter_by(project_id=project_id).all()
            for pm in pm_rows:
                member_ids.add(pm.member_id)
            members = session.query(Member).filter(Member.id.in_(member_ids)).all() if member_ids else []

            task_ids = [t.id for t in tasks]
            deps = (
                session.query(TaskDependency)
                .filter(TaskDependency.predecessor_id.in_(task_ids))
                .all()
            ) if task_ids else []

            return 200, {
                "project": {
                    "id": project.id,
                    "external_id": project.external_id,
                    "name": project.name,
                    "status": project.status,
                    "start_date": project.start_date,
                    "end_date": project.end_date,
                    "color": project.color,
                    "asana_project_gid": project.asana_project_gid,
                },
                "tasks": [_serialize_task(t, session) for t in tasks],
                "members": [_serialize_member(m) for m in members],
                "dependencies": [
                    {
                        "predecessor_id": d.predecessor_id,
                        "successor_id": d.successor_id,
                        "dependency_type": d.dependency_type,
                    }
                    for d in deps
                ],
            }

    def _handle_create_project(self, environ, path_params, query, body):
        self._require_auth(environ)
        data = body or {}
        if not data.get("name"):
            return 400, {"error": "name is required."}
        project = self._people_svc.create_project(data)
        return 201, {"project": project}

    def _handle_update_project(self, environ, path_params, query, body):
        self._require_auth(environ)
        project = self._people_svc.update_project(int(path_params["id"]), body or {})
        if project is None:
            return 404, {"error": "Project not found."}
        return 200, {"project": project}

    def _handle_archive_project(self, environ, path_params, query, body):
        self._require_auth(environ)
        project_id = int(path_params["id"])
        permanent = query.get("permanent", ["false"])[0].lower() == "true"
        delete_from_asana = query.get("delete_from_asana", ["false"])[0].lower() == "true"

        asana_deleted = 0
        asana_errors = []

        if permanent and delete_from_asana:
            # Delete linked tasks from Asana before removing locally
            try:
                client = _get_asana_client()
                with get_db_session() as session:
                    tasks = session.query(Task).filter_by(project_id=project_id).all()
                    for t in tasks:
                        asana_gid = (t.field_overrides or {}).get("asana_gid")
                        if asana_gid:
                            try:
                                client.delete_task(asana_gid)
                                asana_deleted += 1
                            except Exception as exc:
                                asana_errors.append({"task_id": t.id, "asana_gid": asana_gid, "error": str(exc)})
            except Exception as exc:
                asana_errors.append({"error": "Could not connect to Asana: %s" % exc})

        if permanent:
            ok = self._people_svc.delete_project(project_id)
        else:
            ok = self._people_svc.archive_project(project_id)
        if not ok:
            return 404, {"error": "Project not found."}
        return 200, {"ok": True, "asana_deleted": asana_deleted, "asana_errors": asana_errors}

    # ── Task handlers ──────────────────────────────────────────────────────────

    def _handle_list_tasks(self, environ, path_params, query, body):
        project_id = query.get("projectId", [None])[0]
        member_id = query.get("memberId", [None])[0]
        tasks = self._people_svc.list_tasks(
            project_id=int(project_id) if project_id else None,
            member_id=int(member_id) if member_id else None,
        )
        return 200, {"tasks": tasks}

    def _handle_create_task(self, environ, path_params, query, body):
        self._require_auth(environ)
        data = body or {}
        if not data.get("name"):
            return 400, {"error": "name is required."}
        if not data.get("project_id"):
            return 400, {"error": "project_id is required."}
        task = self._people_svc.create_task(data)
        return 201, {"task": task}

    def _handle_update_task(self, environ, path_params, query, body):
        self._require_auth(environ)
        data = body or {}
        with get_db_session() as session:
            task = session.query(Task).filter_by(id=int(path_params["id"])).first()
            if task is None:
                return 404, {"error": "Task not found."}
            if "buffer_hours" in data:
                task.buffer_hours = float(data["buffer_hours"]) if data["buffer_hours"] is not None else None
            if "estimated_hours" in data:
                task.estimated_hours = float(data["estimated_hours"]) if data["estimated_hours"] is not None else None
            if "name" in data:
                task.name = data["name"]
            if "status" in data:
                task.status = data["status"]
            if "scheduled_start_date" in data:
                task.scheduled_start_date = data["scheduled_start_date"]
            if "scheduled_end_date" in data:
                task.scheduled_end_date = data["scheduled_end_date"]
            session.commit()
            return 200, {"task": _serialize_task(task)}

    # ── Schedule calendar (legacy coarse view) ────────────────────────────────

    def _handle_get_schedule(self, environ, path_params, query, body):
        view = query.get("view", ["week"])[0]
        date = query.get("date", [None])[0]
        calendar = self._schedule_svc.build_calendar_view(view_type=view, anchor_date=date)
        return 200, calendar

    def _handle_get_day_calendar(self, environ, path_params, query, body):
        """Return DayAllocation rows for a date range, grouped by member.

        Also returns per-member daily capacity and cross-project totals for utilization display.
        """
        start = query.get("start", [None])[0]
        end = query.get("end", [None])[0]
        if not start or not end:
            return 400, {"error": "start and end query params required (YYYY-MM-DD)"}

        project_id_param = query.get("projectId", [None])[0]

        with get_db_session() as session:
            q = session.query(DayAllocation).filter(
                DayAllocation.date >= start, DayAllocation.date <= end
            )
            if project_id_param:
                q = q.join(Task, DayAllocation.task_id == Task.id).filter(
                    Task.project_id == int(project_id_param)
                )
            rows = q.all()
            # Fetch tasks and members for names
            task_ids = {r.task_id for r in rows}
            member_ids = {r.member_id for r in rows}
            tasks_map = {t.id: t for t in session.query(Task).filter(Task.id.in_(task_ids)).all()} if task_ids else {}
            members_map = {m.id: m for m in session.query(Member).filter(Member.id.in_(member_ids)).all()} if member_ids else {}

            result = []
            for r in rows:
                task = tasks_map.get(r.task_id)
                member = members_map.get(r.member_id)
                result.append({
                    "id": r.id,
                    "task_id": r.task_id,
                    "task_external_id": task.external_id if task else None,
                    "task_name": task.name if task else None,
                    "member_id": r.member_id,
                    "member_external_id": member.external_id if member else None,
                    "member_name": member.display_name if member else None,
                    "date": r.date,
                    "hours": r.hours,
                    "source": r.source,
                    "pinned": bool(r.pinned) if hasattr(r, 'pinned') else False,
                })

            # Build per-member daily utilization (all projects combined)
            # Includes per-task breakdown for drill-down on click
            member_utilization = []
            if member_ids:
                # Get ALL allocations for these members across ALL projects in date range
                all_allocs = session.query(DayAllocation).filter(
                    DayAllocation.member_id.in_(member_ids),
                    DayAllocation.date >= start,
                    DayAllocation.date <= end,
                ).all()
                from collections import defaultdict
                totals_by_member_date = defaultdict(float)
                # Per-task breakdown: (member_id, date) -> [{task_name, project_name, hours}]
                breakdown_by_member_date = defaultdict(list)
                # Collect all task/project info needed
                alloc_task_ids = {da.task_id for da in all_allocs}
                alloc_tasks = {t.id: t for t in session.query(Task).filter(Task.id.in_(alloc_task_ids)).all()} if alloc_task_ids else {}
                alloc_proj_ids = {t.project_id for t in alloc_tasks.values()}
                alloc_projects = {p.id: p for p in session.query(Project).filter(Project.id.in_(alloc_proj_ids)).all()} if alloc_proj_ids else {}

                for da in all_allocs:
                    totals_by_member_date[(da.member_id, da.date)] += da.hours
                    t = alloc_tasks.get(da.task_id)
                    p = alloc_projects.get(t.project_id) if t else None
                    breakdown_by_member_date[(da.member_id, da.date)].append({
                        "task_name": t.name if t else str(da.task_id),
                        "project_name": p.name if p else "Unknown",
                        "project_color": p.color if p else "#999",
                        "hours": da.hours,
                    })

                # Load time-off for all members in range
                from services.persistence.models import TimeOff
                from datetime import date as date_cls, timedelta as td
                member_time_off = defaultdict(dict)  # mid -> {date_str: leave_type}
                for to in session.query(TimeOff).filter(
                    TimeOff.member_id.in_(member_ids)
                ).all():
                    try:
                        cur = date_cls.fromisoformat(to.start_date)
                        to_end = date_cls.fromisoformat(to.end_date)
                    except (ValueError, TypeError):
                        continue
                    while cur <= to_end:
                        ds = cur.isoformat()
                        if start <= ds <= end:
                            member_time_off[to.member_id][ds] = to.leave_type or "leave"
                        cur += td(days=1)

                for mid, member in members_map.items():
                    working_days = member.working_days or ["Sun", "Mon", "Tue", "Wed", "Thu"]
                    daily_cap = member.weekly_capacity_hours / max(len(working_days), 1)
                    days = {}
                    time_off_map = member_time_off.get(mid, {})
                    for (m_id, d), hrs in totals_by_member_date.items():
                        if m_id == mid:
                            days[d] = {
                                "allocated": round(hrs, 2),
                                "capacity": round(daily_cap, 2),
                                "tasks": breakdown_by_member_date.get((mid, d), []),
                                "time_off": time_off_map.get(d),
                            }
                    # Also add time-off days that have no allocations
                    for d, leave_type in time_off_map.items():
                        if d not in days:
                            days[d] = {
                                "allocated": 0,
                                "capacity": round(daily_cap, 2),
                                "tasks": [],
                                "time_off": leave_type,
                            }
                    member_utilization.append({
                        "member_id": mid,
                        "display_name": member.display_name,
                        "avatar_color": member.avatar_color,
                        "daily_capacity": round(daily_cap, 2),
                        "days": days,
                    })

        return 200, {"day_allocations": result, "member_utilization": member_utilization}

    def _handle_create_assignment(self, environ, path_params, query, body):
        self._require_auth(environ)
        data = body or {}
        for required in ("task_id", "member_id", "start_date", "end_date"):
            if not data.get(required):
                return 400, {"error": f"{required} is required."}
        assignment = self._schedule_svc.create_assignment(data)
        # Sync task dates from allocations
        with get_db_session() as session:
            _sync_task_dates_from_allocations(session, int(data["task_id"]))
            session.commit()
        return 201, {"assignment": assignment}

    def _handle_move_assignment(self, environ, path_params, query, body):
        self._require_auth(environ)
        # Look up the assignment's task_id before moving
        with get_db_session() as session:
            assign = session.query(Assignment).filter_by(id=int(path_params["id"])).first()
            task_id = assign.task_id if assign else None
        result = self._schedule_svc.move_assignment(int(path_params["id"]), body or {})
        if result is None:
            return 404, {"error": "Assignment not found."}
        if task_id:
            with get_db_session() as session:
                _sync_task_dates_from_allocations(session, task_id)
                session.commit()
        return 200, {"assignment": result}

    def _handle_update_assignment(self, environ, path_params, query, body):
        self._require_auth(environ)
        with get_db_session() as session:
            assign = session.query(Assignment).filter_by(id=int(path_params["id"])).first()
            task_id = assign.task_id if assign else None
        result = self._schedule_svc.update_assignment(int(path_params["id"]), body or {})
        if result is None:
            return 404, {"error": "Assignment not found."}
        if task_id:
            with get_db_session() as session:
                _sync_task_dates_from_allocations(session, task_id)
                session.commit()
        return 200, {"assignment": result}

    def _handle_delete_assignment(self, environ, path_params, query, body):
        self._require_auth(environ)
        with get_db_session() as session:
            assign = session.query(Assignment).filter_by(id=int(path_params["id"])).first()
            task_id = assign.task_id if assign else None
        ok = self._schedule_svc.delete_assignment(int(path_params["id"]))
        if not ok:
            return 404, {"error": "Assignment not found."}
        if task_id:
            with get_db_session() as session:
                _sync_task_dates_from_allocations(session, task_id)
                session.commit()
        return 200, {"ok": True}

    # ── Time-off handlers ──────────────────────────────────────────────────────

    def _handle_list_time_off(self, environ, path_params, query, body):
        member_id = query.get("memberId", [None])[0]
        start_date = query.get("startDate", [None])[0]
        end_date = query.get("endDate", [None])[0]
        entries = self._time_off_svc.list_time_offs(
            member_id=int(member_id) if member_id else None,
            start_date=start_date,
            end_date=end_date,
        )
        return 200, {"time_offs": entries}

    def _handle_create_time_off(self, environ, path_params, query, body):
        self._require_auth(environ)
        data = body or {}
        for required in ("member_id", "start_date", "end_date"):
            if not data.get(required):
                return 400, {"error": f"{required} is required."}
        entry = self._time_off_svc.create_time_off(data)
        return 201, {"time_off": entry}

    def _handle_update_time_off(self, environ, path_params, query, body):
        self._require_auth(environ)
        entry = self._time_off_svc.update_time_off(int(path_params["id"]), body or {})
        if entry is None:
            return 404, {"error": "Time-off entry not found."}
        return 200, {"time_off": entry}

    def _handle_delete_time_off(self, environ, path_params, query, body):
        self._require_auth(environ)
        ok = self._time_off_svc.delete_time_off(int(path_params["id"]))
        if not ok:
            return 404, {"error": "Time-off entry not found."}
        return 200, {"ok": True}

    # ── Import handler ─────────────────────────────────────────────────────────

    def _handle_import(self, environ, path_params, query, body):
        """Accept XML (MS Project) or JSON (Asana) and sync to SQLite.

        body is raw bytes here (set by the WSGI dispatch for /api/import).
        """
        self._require_auth(environ)
        from services.integration_service import IntegrationService

        if not body:
            return 400, {"error": "Request body is required."}

        # Detect XML (MS Project) vs JSON (Asana)
        if isinstance(body, (bytes, bytearray)):
            raw_text = body.lstrip()
            is_xml = raw_text[:5] in (b"<?xml", b"<Proj")
        else:
            raw_text = (body or b"")
            is_xml = False

        if is_xml:
            # MS Project XML — handled by Phase 2 parser
            from services.integration_service.msproject_parser import MSProjectXMLParser
            bundle = MSProjectXMLParser().parse(body if isinstance(body, bytes) else body.encode())
        else:
            # Asana / JSON payload
            import json as _json
            if isinstance(body, (bytes, bytearray)):
                payload = _json.loads(body.decode("utf-8"))
            else:
                payload = body  # already a dict (json body reader)
            integration_service = IntegrationService()
            bundle = integration_service.import_source_plan(payload)

        counts = self._import_mapper.sync_from_bundle(bundle)

        return 200, {
            "snapshot_id": bundle.snapshot.snapshot_id,
            "project_id": counts.get("project_id"),
            "projects": counts.get("projects", 0),
            "projects_updated": counts.get("projects_updated", 0),
            "tasks": counts.get("tasks", 0),
            "tasks_updated": counts.get("tasks_updated", 0),
            "dependencies": counts.get("dependencies", 0),
            "dependencies_updated": counts.get("dependencies_updated", 0),
            "assignments": counts.get("assignments", 0),
            "unmatched_resources": counts.get("unmatched_resources", []),
            "start_date": counts.get("start_date"),
            "end_date": counts.get("end_date"),
            "discovered_member_ids": counts.get("discovered_member_ids", []),
        }

    @staticmethod
    def _extract_asana_effort(task_data):
        """Extract effort hours from an Asana task.

        Checks built-in estimated_hours first, then falls back to
        custom field named 'Estimated time' (value in minutes).
        """
        # Built-in field
        if task_data.get("estimated_hours"):
            return float(task_data["estimated_hours"])
        # Custom field (stored in minutes)
        for cf in task_data.get("custom_fields") or []:
            name = (cf.get("name") or "").lower()
            if name in ("estimated time", "estimate", "effort", "time estimate"):
                val = cf.get("number_value")
                if val is not None and val > 0:
                    return round(float(val) / 60, 2)  # minutes → hours
        return None

    def _handle_import_from_asana(self, environ, path_params, query, body):
        """Pull tasks from an Asana project and sync to SQLite."""
        self._require_auth(environ)
        data = body or {}
        asana_project_gid = data.get("asana_project_gid")
        if not asana_project_gid:
            return 400, {"error": "asana_project_gid is required."}

        try:
            client = _get_asana_client()
        except Exception as exc:
            return 400, {"error": "Asana not configured: %s" % exc}

        # 1. Fetch project info
        try:
            asana_project = client.get_project(asana_project_gid)
        except Exception as exc:
            return 400, {"error": "Could not fetch Asana project: %s" % exc}

        # 2. Fetch all tasks
        try:
            asana_tasks = client.get_tasks(asana_project_gid)
        except Exception as exc:
            return 400, {"error": "Could not fetch tasks: %s" % exc}

        # Track completed task GIDs (import them but mark as completed)
        completed_task_gids = {t["gid"] for t in asana_tasks if t.get("completed")}

        # 3. Fetch dependencies per task
        task_deps: dict = {}  # task_gid → [predecessor_gid, ...]
        for t in asana_tasks:
            try:
                deps = client.get_task_dependencies(t["gid"])
                if deps:
                    task_deps[t["gid"]] = [d["gid"] for d in deps]
            except Exception:
                pass  # dependencies are optional

        # 4. Collect unique assignees and auto-create missing members
        assignee_gids = set()
        for t in asana_tasks:
            assignee = t.get("assignee")
            if assignee and assignee.get("gid"):
                assignee_gids.add(assignee["gid"])

        members_created = 0
        with get_db_session() as session:
            from services.persistence.models import Member
            for gid in assignee_gids:
                existing = session.query(Member).filter_by(external_id=gid).first()
                if existing is None:
                    # Fetch user details from Asana
                    try:
                        workspace_gid = _get_config("asana_workspace_gid") or ""
                        users = client.get_workspace_users(workspace_gid) if workspace_gid else []
                        user_info = next((u for u in users if u["gid"] == gid), None)
                    except Exception:
                        user_info = None

                    display_name = (user_info or {}).get("name", "Asana User %s" % gid[:8])
                    email = (user_info or {}).get("email")
                    member = Member(
                        external_id=gid,
                        display_name=display_name,
                        email=email,
                        role="team_member",
                        weekly_capacity_hours=40.0,
                    )
                    session.add(member)
                    members_created += 1
            session.commit()

        # 5. Build NormalizedSourceBundle
        from services.integration_service.contracts import (
            NormalizedDependencyRecord,
            NormalizedResourceAssignmentRecord,
            NormalizedResourceRecord,
            NormalizedSourceBundle,
            NormalizedTaskRecord,
            SourceArtifact,
            SourceReadiness,
            SourceSnapshot,
        )
        import hashlib

        project_ext_id = "asana-project-%s" % asana_project_gid

        # Build hierarchy depth map by traversing parent chains
        gid_to_parent_gid = {}
        for t in asana_tasks:
            parent = t.get("parent")
            if parent and parent.get("gid"):
                gid_to_parent_gid[t["gid"]] = parent["gid"]

        def _depth(gid, visited=None):
            if visited is None:
                visited = set()
            if gid in visited:
                return 0
            visited.add(gid)
            parent_gid = gid_to_parent_gid.get(gid)
            if parent_gid:
                return 1 + _depth(parent_gid, visited)
            return 0

        task_records = []
        resource_records = []
        assignment_records = []
        dep_records = []

        for t in asana_tasks:
            task_ext_id = "asana-task-%s" % t["gid"]
            parent_gid = gid_to_parent_gid.get(t["gid"])
            parent_task_id = ("asana-task-%s" % parent_gid) if parent_gid else None
            depth = _depth(t["gid"])

            task_records.append(NormalizedTaskRecord(
                task_id=hashlib.sha1(task_ext_id.encode()).hexdigest()[:16],
                source_snapshot_id="",
                source_system="asana",
                external_task_id=task_ext_id,
                project_id=hashlib.sha1(project_ext_id.encode()).hexdigest()[:16],
                project_external_id=project_ext_id,
                parent_task_id=parent_task_id,
                name=t.get("name", "Untitled"),
                hierarchy_path=[task_ext_id],
                hierarchy_depth=depth,
                effort_hours=self._extract_asana_effort(t),
                start_date=t.get("start_on"),
                due_date=t.get("due_on"),
            ))

            # Assignment
            assignee = t.get("assignee")
            if assignee and assignee.get("gid"):
                assignment_records.append(NormalizedResourceAssignmentRecord(
                    assignment_id=hashlib.sha1(
                        ("%s-%s" % (task_ext_id, assignee["gid"])).encode()
                    ).hexdigest()[:16],
                    source_snapshot_id="",
                    source_system="asana",
                    task_id=hashlib.sha1(task_ext_id.encode()).hexdigest()[:16],
                    task_external_id=task_ext_id,
                    resource_id=hashlib.sha1(
                        ("resource-asana-%s" % assignee["gid"]).encode()
                    ).hexdigest()[:16],
                    resource_external_id=assignee["gid"],
                    allocation_percent=100,
                ))

        # Resource records for each assignee
        for gid in assignee_gids:
            resource_records.append(NormalizedResourceRecord(
                resource_id=hashlib.sha1(
                    ("resource-asana-%s" % gid).encode()
                ).hexdigest()[:16],
                source_snapshot_id="",
                source_system="asana",
                external_resource_id=gid,
                display_name=gid,
                calendar_id=hashlib.sha1(("cal-asana-%s" % gid).encode()).hexdigest()[:16],
                calendar_name=None,
                default_daily_capacity_hours=8.0,
                working_days=["Sun", "Mon", "Tue", "Wed", "Thu"],
                availability_ratio=1.0,
            ))

        # Dependencies
        for task_gid, pred_gids in task_deps.items():
            succ_ext = "asana-task-%s" % task_gid
            for pred_gid in pred_gids:
                pred_ext = "asana-task-%s" % pred_gid
                dep_records.append(NormalizedDependencyRecord(
                    dependency_id=hashlib.sha1(
                        ("%s-%s" % (pred_ext, succ_ext)).encode()
                    ).hexdigest()[:16],
                    source_snapshot_id="",
                    source_system="asana",
                    predecessor_task_id=hashlib.sha1(pred_ext.encode()).hexdigest()[:16],
                    successor_task_id=hashlib.sha1(succ_ext.encode()).hexdigest()[:16],
                    predecessor_external_task_id=pred_ext,
                    successor_external_task_id=succ_ext,
                    dependency_type="FS",
                ))

        content_hash = hashlib.sha1(
            ("%d-%d-%d" % (len(task_records), len(dep_records), len(assignment_records))).encode()
        ).hexdigest()[:16]

        artifact = SourceArtifact(
            artifact_id=content_hash,
            external_artifact_id=asana_project_gid,
            source_system="asana",
            captured_at="",
            payload_digest=content_hash,
            raw_payload={},
        )
        snapshot = SourceSnapshot(
            snapshot_id=content_hash,
            artifact_id=content_hash,
            source_system="asana",
            captured_at="",
            project_count=1,
            task_count=len(task_records),
            dependency_count=len(dep_records),
            assignment_count=len(assignment_records),
            issue_count=0,
        )
        readiness = SourceReadiness(
            state="ready" if task_records else "empty",
            runnable=len(task_records) > 0,
            blocking_issue_count=0,
            advisory_issue_count=0,
            total_issue_count=0,
        )

        bundle = NormalizedSourceBundle(
            artifact=artifact,
            snapshot=snapshot,
            project_mappings=[],
            task_mappings=[],
            resource_mappings=[],
            tasks=task_records,
            dependencies=dep_records,
            resource_assignments=assignment_records,
            resources=resource_records,
            resource_exceptions=[],
            issue_facts=[],
            source_readiness=readiness,
        )

        # 6. Sync to SQLite (pass completed external IDs so mapper sets status)
        completed_ext_ids = {"asana-task-%s" % gid for gid in completed_task_gids}
        counts = self._import_mapper.sync_from_bundle(bundle, completed_ext_ids=completed_ext_ids)

        # 7. Auto-link and store Asana GIDs on tasks
        discovered_member_ids = []
        with get_db_session() as session:
            from services.persistence.models import Member
            # Link project
            if counts.get("project_ext_id"):
                proj = session.query(Project).filter_by(
                    external_id=counts["project_ext_id"]
                ).first()
                if proj:
                    proj.asana_project_gid = asana_project_gid
                    if asana_project.get("name"):
                        proj.name = asana_project["name"]

            # Store asana_gid in field_overrides for each task
            for t in asana_tasks:
                task_ext_id = "asana-task-%s" % t["gid"]
                task = session.query(Task).filter_by(external_id=task_ext_id).first()
                if task:
                    overrides = dict(task.field_overrides or {})
                    overrides["asana_gid"] = t["gid"]
                    task.field_overrides = overrides

            # Collect discovered member IDs and auto-add to ProjectMember
            from services.persistence.models import ProjectMember
            proj_id = counts.get("project_id")
            for gid in assignee_gids:
                m = session.query(Member).filter_by(external_id=gid).first()
                if m:
                    discovered_member_ids.append(m.id)
                    # Auto-create ProjectMember row if not exists
                    if proj_id:
                        existing_pm = session.query(ProjectMember).filter_by(
                            project_id=int(proj_id), member_id=m.id
                        ).first()
                        if existing_pm is None:
                            session.add(ProjectMember(project_id=int(proj_id), member_id=m.id))

            session.commit()

        return 200, {
            "project_id": counts.get("project_id"),
            "projects": counts.get("projects", 0),
            "tasks": counts.get("tasks", 0),
            "dependencies": counts.get("dependencies", 0),
            "dependencies_updated": counts.get("dependencies_updated", 0),
            "assignments": counts.get("assignments", 0),
            "members_created": members_created,
            "unmatched_resources": counts.get("unmatched_resources", []),
            "start_date": counts.get("start_date"),
            "end_date": counts.get("end_date"),
            "discovered_member_ids": discovered_member_ids,
        }

    # ── Scheduling engine ──────────────────────────────────────────────────────

    # ── SSE Import Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _sse_event(event_type, data):
        """Format a single SSE event as bytes."""
        payload = json.dumps(data, default=str)
        return f"event: {event_type}\ndata: {payload}\n\n".encode("utf-8")

    def _handle_import_from_asana_stream(self, environ, path_params, query, body):
        """SSE streaming version of Asana import with item-by-item progress."""
        self._require_auth(environ)
        data = body or {}
        asana_project_gid = data.get("asana_project_gid")
        if not asana_project_gid:
            return 400, {"error": "asana_project_gid is required."}

        bff = self

        def generate():
            try:
                from services.persistence.models import ProjectMember

                yield bff._sse_event("progress", {"step": "init", "message": "Initializing Asana connection...", "current": 0, "total": 0})

                client = _get_asana_client()
                if not client:
                    yield bff._sse_event("error", {"message": "Asana PAT not configured. Go to Settings."})
                    return

                # Step 1: Fetch project
                yield bff._sse_event("progress", {"step": "project", "message": "Fetching project info...", "current": 0, "total": 0})
                project_data = client.get_project(asana_project_gid)
                project_name = project_data.get("name", "Unknown")
                yield bff._sse_event("log", {"message": f"Project: {project_name}"})

                # Step 2: Fetch tasks
                yield bff._sse_event("progress", {"step": "tasks", "message": "Fetching tasks from Asana...", "current": 0, "total": 0})
                raw_tasks = client.get_tasks(asana_project_gid)
                task_count = len(raw_tasks)
                yield bff._sse_event("progress", {"step": "tasks", "message": f"Found {task_count} tasks", "current": task_count, "total": task_count})
                yield bff._sse_event("log", {"message": f"Fetched {task_count} tasks"})

                # Step 3: Fetch dependencies per task
                completed_gids = set()
                deps_by_task = {}
                for i, t in enumerate(raw_tasks):
                    gid = t.get("gid", "")
                    name = t.get("name", "?")
                    if t.get("completed"):
                        completed_gids.add(gid)
                    yield bff._sse_event("progress", {
                        "step": "dependencies",
                        "message": f"Fetching dependencies: {name}",
                        "current": i + 1, "total": task_count,
                    })
                    try:
                        preds = client.get_task_dependencies(gid)
                        if preds:
                            deps_by_task[gid] = preds
                            yield bff._sse_event("log", {"message": f"  {name}: {len(preds)} predecessor(s)"})
                    except Exception:
                        pass  # some tasks may not support deps

                # Step 4: Auto-create members
                assignee_gids = set()
                for t in raw_tasks:
                    a = t.get("assignee")
                    if a and a.get("gid"):
                        assignee_gids.add(a["gid"])
                yield bff._sse_event("progress", {"step": "members", "message": f"Checking {len(assignee_gids)} assignees...", "current": 0, "total": len(assignee_gids)})

                members_created = 0
                with get_db_session() as session:
                    for i, agid in enumerate(assignee_gids):
                        existing = session.query(Member).filter_by(external_id=agid).first()
                        if not existing:
                            # Fetch user info from Asana
                            try:
                                workspace_gid = project_data.get("workspace", {}).get("gid")
                                if workspace_gid:
                                    users = client.get_workspace_users(workspace_gid)
                                    user = next((u for u in users if u.get("gid") == agid), None)
                                    if user:
                                        session.add(Member(
                                            external_id=agid,
                                            display_name=user.get("name", f"User {agid}"),
                                            email=user.get("email"),
                                            weekly_capacity_hours=40.0,
                                            working_days=["Sun", "Mon", "Tue", "Wed", "Thu"],
                                            is_active=True,
                                        ))
                                        members_created += 1
                                        yield bff._sse_event("log", {"message": f"  Created member: {user.get('name')}"})
                            except Exception:
                                pass
                        yield bff._sse_event("progress", {"step": "members", "message": f"Processing assignees...", "current": i + 1, "total": len(assignee_gids)})
                    session.commit()

                # Step 5: Build bundle and sync
                yield bff._sse_event("progress", {"step": "sync", "message": "Building import bundle...", "current": 0, "total": 0})

                # Call the existing import handler logic to build bundle and sync
                # We pass the pre-fetched data to avoid re-fetching
                status, result = bff._handle_import_from_asana(
                    environ, path_params, query,
                    {"asana_project_gid": asana_project_gid},
                )

                if status == 200:
                    yield bff._sse_event("progress", {
                        "step": "sync",
                        "message": f"Synced {result.get('tasks', 0)} tasks, {result.get('dependencies', 0)} dependencies",
                        "current": result.get("tasks", 0), "total": result.get("tasks", 0),
                    })
                    yield bff._sse_event("log", {"message": f"Tasks: {result.get('tasks', 0)}"})
                    yield bff._sse_event("log", {"message": f"Dependencies: {result.get('dependencies', 0)}"})
                    yield bff._sse_event("log", {"message": f"Assignments: {result.get('assignments', 0)}"})
                    if members_created:
                        yield bff._sse_event("log", {"message": f"Members created: {members_created}"})
                    yield bff._sse_event("complete", result)
                else:
                    yield bff._sse_event("error", {"message": result.get("error", "Import failed")})

            except Exception as exc:
                yield bff._sse_event("error", {"message": str(exc)})

        return "SSE", generate()

    def _handle_import_apply(self, environ, path_params, query, body):
        """Step 2 of two-step MS Project import: apply with resource mapping.

        Body (JSON): {
            "xml_base64": "...",          # base64-encoded XML file
            "resource_mapping": {         # resource_external_id → member_id
                "msproject-res-1": 8,
                "msproject-res-2": 12
            }
        }
        """
        self._require_auth(environ)
        data = body or {}
        xml_b64 = data.get("xml_base64")
        resource_mapping = data.get("resource_mapping", {})

        if not xml_b64:
            return 400, {"error": "xml_base64 is required."}

        import base64
        try:
            xml_bytes = base64.b64decode(xml_b64)
        except Exception:
            return 400, {"error": "Invalid base64 encoding."}

        from services.integration_service.msproject_parser import MSProjectXMLParser
        try:
            bundle = MSProjectXMLParser().parse(xml_bytes)
        except ValueError as exc:
            return 400, {"error": str(exc)}

        counts = self._import_mapper.sync_from_bundle(bundle, resource_mapping=resource_mapping)

        # Auto-create ProjectMember rows for mapped members
        if counts.get("project_id"):
            from services.persistence.models import ProjectMember
            with get_db_session() as session:
                for mid in set(resource_mapping.values()):
                    if mid is None:
                        continue
                    existing = session.query(ProjectMember).filter_by(
                        project_id=counts["project_id"], member_id=int(mid)).first()
                    if not existing:
                        session.add(ProjectMember(project_id=counts["project_id"], member_id=int(mid)))
                session.commit()

        return 200, {
            "snapshot_id": bundle.snapshot.snapshot_id,
            "project_id": counts.get("project_id"),
            "projects": counts.get("projects", 0),
            "tasks": counts.get("tasks", 0),
            "dependencies": counts.get("dependencies", 0),
            "assignments": counts.get("assignments", 0),
            "unmatched_resources": counts.get("unmatched_resources", []),
            "start_date": counts.get("start_date"),
            "end_date": counts.get("end_date"),
            "discovered_member_ids": list(set(int(v) for v in resource_mapping.values() if v)),
        }

    def _handle_import_preview(self, environ, path_params, query, body):
        """Parse MS Project XML and return resources + summary without importing.

        Used as step 1 of the two-step import: preview → map resources → import.
        Returns resources found in the XML so the user can map them to members.
        """
        self._require_auth(environ)
        if not body:
            return 400, {"error": "Request body is required."}

        from services.integration_service.msproject_parser import MSProjectXMLParser
        from services.persistence.models import Member

        try:
            bundle = MSProjectXMLParser().parse(body if isinstance(body, bytes) else body.encode())
        except ValueError as exc:
            return 400, {"error": str(exc)}

        # Extract resource info for mapping UI
        resources_to_map = []
        with get_db_session() as session:
            all_members = [{"id": m.id, "external_id": m.external_id, "display_name": m.display_name}
                           for m in session.query(Member).filter_by(is_active=True).all()]

            for res in bundle.resources:
                # Check if already matched
                matched_member = session.query(Member).filter_by(external_id=res.external_resource_id).first()
                # Also try name match as a suggestion
                name_match = None
                if not matched_member and res.display_name:
                    name_match = session.query(Member).filter(
                        Member.display_name.ilike(f"%{res.display_name}%"),
                        Member.is_active == True,
                    ).first()

                # Count tasks assigned to this resource
                task_count = sum(
                    1 for a in bundle.resource_assignments
                    if a.resource_id == res.resource_id
                )

                resources_to_map.append({
                    "resource_external_id": res.external_resource_id,
                    "resource_name": res.display_name,
                    "daily_capacity": res.default_daily_capacity_hours,
                    "task_count": task_count,
                    "matched_member_id": matched_member.id if matched_member else None,
                    "matched_member_name": matched_member.display_name if matched_member else None,
                    "suggested_member_id": name_match.id if name_match else None,
                    "suggested_member_name": name_match.display_name if name_match else None,
                })

        # Task summary
        leaf_count = 0
        parent_count = 0
        parent_ext_ids = {t.parent_task_id for t in bundle.tasks if t.parent_task_id}
        for t in bundle.tasks:
            ext = t.external_task_id
            if ext in parent_ext_ids:
                parent_count += 1
            else:
                leaf_count += 1

        return 200, {
            "project_name": bundle.tasks[0].project_external_id if bundle.tasks else "Unknown",
            "task_count": len(bundle.tasks),
            "leaf_task_count": leaf_count,
            "parent_task_count": parent_count,
            "dependency_count": len(bundle.dependencies),
            "resources": resources_to_map,
            "available_members": all_members,
            "has_unmatched": any(r["matched_member_id"] is None for r in resources_to_map),
        }

    def _handle_import_stream(self, environ, path_params, query, body):
        """SSE streaming version of MS Project XML import."""
        self._require_auth(environ)
        raw_body = body  # already read as raw bytes

        bff = self

        def generate():
            try:
                yield bff._sse_event("progress", {"step": "parse", "message": "Parsing XML file...", "current": 0, "total": 0})

                from services.integration_service.msproject_parser import MSProjectXMLParser
                parser = MSProjectXMLParser()
                bundle = parser.parse(raw_body)

                task_count = len(bundle.tasks)
                resource_count = len(bundle.resources)
                dep_count = len(bundle.dependencies)
                yield bff._sse_event("progress", {"step": "parse", "message": f"Parsed {task_count} tasks, {resource_count} resources", "current": task_count, "total": task_count})
                yield bff._sse_event("log", {"message": f"Tasks: {task_count}"})
                yield bff._sse_event("log", {"message": f"Resources: {resource_count}"})
                yield bff._sse_event("log", {"message": f"Dependencies: {dep_count}"})

                # Log each task
                for i, t in enumerate(bundle.tasks):
                    yield bff._sse_event("progress", {
                        "step": "import",
                        "message": f"Importing: {t.name}",
                        "current": i + 1, "total": task_count,
                    })
                    yield bff._sse_event("log", {"message": f"  [{i+1}/{task_count}] {t.name} ({t.effort_hours or 0}h)"})

                # Sync to DB
                yield bff._sse_event("progress", {"step": "sync", "message": "Writing to database...", "current": 0, "total": 0})

                status, result = bff._handle_import(environ, path_params, query, raw_body)

                if status == 200:
                    yield bff._sse_event("progress", {"step": "sync", "message": "Import complete", "current": 1, "total": 1})
                    yield bff._sse_event("log", {"message": f"Assignments: {result.get('assignments', 0)}"})
                    if result.get("unmatched_resources"):
                        yield bff._sse_event("log", {"message": f"Unmatched resources: {', '.join(result['unmatched_resources'])}"})
                    yield bff._sse_event("complete", result)
                else:
                    yield bff._sse_event("error", {"message": result.get("error", "Import failed")})

            except Exception as exc:
                yield bff._sse_event("error", {"message": str(exc)})

        return "SSE", generate()

    def _handle_run_schedule(self, environ, path_params, query, body):
        """Run the planning engine over SQLite data and write DayAllocation rows.

        Body: {
            "dry_run": true|false,
            "project_id": int?,
            "member_ids": [int]?,
            "task_ids": [int]?,            # optional: only schedule these tasks
            "schedule_start_date": str?,    # optional: override start date (YYYY-MM-DD)
            "distribution_mode": str?,      # "engine" (default) | "even"
            "chunk_hours": float?,          # hours per day for even distribution
            "respect_dates": bool?          # even mode: use each task's original start/end dates
        }
        """
        self._require_auth(environ)
        body_data = body or {}
        dry_run = bool(body_data.get("dry_run", False))
        preflight = bool(body_data.get("preflight", False))
        project_id = body_data.get("project_id")
        member_ids = body_data.get("member_ids")
        task_ids = body_data.get("task_ids")  # optional task filter
        schedule_start_date = body_data.get("schedule_start_date")  # optional start date override
        distribution_mode = body_data.get("distribution_mode", "engine")  # "engine" or "even"
        chunk_hours = body_data.get("chunk_hours")  # hours per day for even distribution
        respect_dates = bool(body_data.get("respect_dates", False))  # even mode: use task's own dates
        ownership_resolutions = body_data.get("ownership_resolutions")  # conflict resolutions from popup
        debug_mode = bool(body_data.get("debug", False))  # include bundle/dep traces in engine_log

        from services.schedule_service.sqlite_bundle_builder import SQLiteSourceBundleBuilder
        from services.schedule_service.allocation_writer import AllocationOutputWriter

        # ── Preflight mode: detect ownership conflicts, don't schedule ────
        if preflight and project_id and member_ids:
            with get_db_session() as session:
                conflicts = SQLiteSourceBundleBuilder().analyze_ownership_conflicts(
                    session, project_id=project_id, member_ids=member_ids,
                    task_ids=task_ids,
                )
            return 200, {"ownership_conflicts": conflicts}

        run_id = str(uuid.uuid4())
        now = _now_iso()

        with get_db_session() as session:
            run = PlanningRun(run_id=run_id, status="running", triggered_at=now)
            session.add(run)
            session.commit()

        try:
            # Save original task dates before engine modifies them
            with get_db_session() as session:
                task_query = session.query(Task).filter(Task.status != "cancelled")
                if project_id:
                    task_query = task_query.filter_by(project_id=int(project_id))
                if task_ids:
                    task_query = task_query.filter(Task.id.in_([int(t) for t in task_ids]))
                for t in task_query.all():
                    overrides = dict(t.field_overrides or {})
                    if "_original_start" not in overrides and t.scheduled_start_date:
                        overrides["_original_start"] = t.scheduled_start_date
                    if "_original_end" not in overrides and t.scheduled_end_date:
                        overrides["_original_end"] = t.scheduled_end_date
                    t.field_overrides = overrides
                session.commit()

            # ── Even distribution mode ────────────────────────────────────────
            if distribution_mode == "even":
                return self._run_even_distribution(
                    run_id=run_id, project_id=project_id, member_ids=member_ids,
                    task_ids=task_ids, schedule_start_date=schedule_start_date,
                    chunk_hours=float(chunk_hours) if chunk_hours else 4.0,
                    dry_run=dry_run, respect_dates=respect_dates,
                )

            # ── Engine distribution mode (default) ────────────────────────────
            # Pre-process and build bundle (assignments, effort overrides, date extensions)
            engine_log = []
            try:
                with get_db_session() as session:
                    bundle, overscheduled_tasks, prep_log = SQLiteSourceBundleBuilder().prepare_and_build(
                        session, project_id=project_id, member_ids=member_ids,
                        task_ids=task_ids, schedule_start_date=schedule_start_date,
                        ownership_resolutions=ownership_resolutions,
                    )
                    engine_log.extend(prep_log)
            except ValueError as ve:
                # Check if this is a parent_task_dependencies blocking error
                import json as _json_err
                try:
                    err_data = _json_err.loads(str(ve))
                    if err_data.get("code") == "parent_task_dependencies":
                        _update_run(run_id, "failed", error=err_data["message"])
                        return 422, err_data
                except (ValueError, TypeError, KeyError):
                    pass
                raise

            if not bundle.source_readiness.runnable:
                _update_run(run_id, "failed", error="No runnable data — add members and tasks first.")
                return 422, {"error": "No runnable data. Add members and tasks first."}

            if debug_mode:
                engine_log.append("── DEBUG: Bundle Tasks ──")
                for _bt in bundle.tasks:
                    engine_log.append(
                        f"  BUNDLE task={_bt.name!r} ext={_bt.external_task_id} "
                        f"start={_bt.start_date} due={_bt.due_date} effort={_bt.effort_hours} "
                        f"parent={_bt.parent_task_id}"
                    )
                engine_log.append("── DEBUG: Bundle Dependencies ──")
                for _bd in bundle.dependencies:
                    _pred_name = next((t.name for t in bundle.tasks if t.task_id == _bd.predecessor_task_id), "?")
                    _succ_name = next((t.name for t in bundle.tasks if t.task_id == _bd.successor_task_id), "?")
                    engine_log.append(
                        f"  DEP {_pred_name!r} ({_bd.predecessor_external_task_id}) "
                        f"--{_bd.dependency_type}--> "
                        f"{_succ_name!r} ({_bd.successor_external_task_id})"
                    )
                engine_log.append("── DEBUG: end ──")

            draft_schedule = self._engine_svc.build_draft_schedule(bundle=bundle)

            # Log engine results
            if debug_mode:
                # Build lookup for predecessor names
                _task_name_by_id = {t.task_id: t.name for t in bundle.tasks}
                _ts_by_id = {ts.task_id: ts for ts in draft_schedule.task_schedules}
                engine_log.append("── DEBUG: Engine Processing ──")
                for ts in draft_schedule.task_schedules:
                    pred_details = []
                    for pid in ts.predecessor_task_ids:
                        ps = _ts_by_id.get(pid)
                        pred_details.append(
                            f"{_task_name_by_id.get(pid, pid)}[{ps.status if ps else '?'}, "
                            f"end={ps.scheduled_end_date if ps else '?'}]"
                        )
                    engine_log.append(
                        f"  ENGINE task={ts.task_name!r} requested=[{ts.requested_start_date} to {ts.requested_due_date}] "
                        f"-> {ts.status} [{ts.scheduled_start_date} to {ts.scheduled_end_date}] "
                        f"effort={ts.required_effort_hours}h scheduled={ts.scheduled_effort_hours}h "
                        f"preds=[{', '.join(pred_details)}]"
                    )
                engine_log.append("── DEBUG: end ──")

            for ts in draft_schedule.task_schedules:
                engine_log.append(
                    f"Engine: '{ts.task_name}' -> {ts.status} "
                    f"({ts.scheduled_effort_hours}h scheduled, {ts.unscheduled_effort_hours}h unscheduled) "
                    f"[{ts.scheduled_start_date} to {ts.scheduled_end_date}]"
                )
            for issue in draft_schedule.schedule_issues:
                engine_log.append(f"Issue: {issue.code} ({issue.task_external_id}) - {issue.message}")

            with get_db_session() as session:
                summary = AllocationOutputWriter().write(
                    draft_schedule=draft_schedule,
                    bundle=bundle,
                    session=session,
                    dry_run=dry_run,
                )
                if not dry_run:
                    for ts in draft_schedule.task_schedules:
                        if ts.status != "scheduled":
                            continue
                        task = session.query(Task).filter_by(external_id=ts.task_external_id).first()
                        if task is None:
                            continue
                        overrides = task.field_overrides or {}
                        if "scheduled_start_date" not in overrides and ts.scheduled_start_date:
                            task.scheduled_start_date = ts.scheduled_start_date
                        if "scheduled_end_date" not in overrides and ts.scheduled_end_date:
                            task.scheduled_end_date = ts.scheduled_end_date
                    session.commit()

                    # ── Roll up parent/summary task dates from children ───
                    # Parent tasks are containers — after scheduling, their
                    # dates should reflect the span of their scheduled children.
                    if project_id:
                        _proj_id = int(project_id)
                        _all_proj_tasks = session.query(Task).filter_by(project_id=_proj_id).all()
                        _parent_id_set = {t.parent_id for t in _all_proj_tasks if t.parent_id}
                        if _parent_id_set:
                            for parent in session.query(Task).filter(Task.id.in_(_parent_id_set)).all():
                                children = session.query(Task).filter_by(parent_id=parent.id).all()
                                child_starts = [c.scheduled_start_date for c in children if c.scheduled_start_date]
                                child_ends = [c.scheduled_end_date for c in children if c.scheduled_end_date]
                                if child_starts:
                                    parent.scheduled_start_date = min(child_starts)
                                if child_ends:
                                    parent.scheduled_end_date = max(child_ends)
                            session.commit()
                engine_log.append(f"Writer: {summary['written']} allocations written, {summary.get('skipped_manual', 0)} pinned skipped")

            _update_run(
                run_id, "succeeded",
                written=summary["written"] if not dry_run else 0,
                ghost_count=len(summary.get("ghost_tasks", [])),
            )

            return 200, {
                "run_id": run_id,
                "status": draft_schedule.schedule_state,
                "dry_run": dry_run,
                "assignments_written": summary["written"] if not dry_run else 0,
                "skipped_manual": summary.get("skipped_manual", 0),
                "ghost_tasks": summary.get("ghost_tasks", []),
                "preview_rows": summary.get("preview_rows") if dry_run else None,
                "overscheduled_tasks": overscheduled_tasks,
                "engine_log": engine_log,
            }

        except Exception as exc:
            _update_run(run_id, "failed", error=str(exc))
            raise

    def _run_even_distribution(self, run_id, project_id, member_ids, task_ids,
                               schedule_start_date, chunk_hours, dry_run,
                               respect_dates=False):
        """Distribute task effort evenly across working days at a fixed chunk_hours/day.

        Each task is allocated chunk_hours per working day starting from schedule_start_date
        (or the task's own start date if not provided) until effort is exhausted.

        If respect_dates=True, each task uses its own original start/end dates as the
        scheduling window instead of chaining sequentially. This may overload a resource
        if tasks overlap, but preserves the imported schedule structure.
        """
        from datetime import date as date_cls, timedelta
        from services.persistence.models import Assignment, DayAllocation, Member

        engine_log = []
        engine_log.append(f"Even distribution: chunk_hours={chunk_hours}, start={schedule_start_date}, respect_dates={respect_dates}")

        with get_db_session() as session:
            # Resolve members
            if member_ids:
                int_member_ids = [int(m) for m in member_ids]
            else:
                int_member_ids = [m.id for m in session.query(Member).filter_by(is_active=True).all()]

            if not int_member_ids:
                _update_run(run_id, "failed", error="No members selected.")
                return 422, {"error": "No members selected."}

            # Load tasks in scope
            task_query = session.query(Task).filter(Task.status.notin_(["cancelled", "completed"]))
            if project_id:
                task_query = task_query.filter_by(project_id=int(project_id))
            if task_ids:
                task_query = task_query.filter(Task.id.in_([int(t) for t in task_ids]))
            all_tasks = task_query.order_by(Task.id).all()

            if not all_tasks:
                _update_run(run_id, "failed", error="No tasks to schedule.")
                return 422, {"error": "No tasks to schedule."}

            # Identify parent tasks (they don't get allocations directly)
            parent_ids = {t.parent_id for t in all_tasks if t.parent_id}
            leaf_tasks = [t for t in all_tasks if t.id not in parent_ids]

            # Clear existing allocations for these tasks
            # Keep pinned only if they belong to in-scope members
            task_id_set = {t.id for t in all_tasks}
            stale = session.query(DayAllocation).filter(
                DayAllocation.task_id.in_(task_id_set),
            ).all()
            cleared = 0
            for da in stale:
                if da.member_id not in member_id_set:
                    # Always delete allocations for out-of-scope members
                    session.delete(da)
                    cleared += 1
                elif not da.pinned:
                    session.delete(da)
                    cleared += 1
            session.flush()
            engine_log.append(f"Cleanup: cleared {cleared} stale allocations")

            # Compute pinned hours per task
            from sqlalchemy import func as sa_func
            pinned_hours = {}
            for t in leaf_tasks:
                ph = session.query(
                    sa_func.coalesce(sa_func.sum(DayAllocation.hours), 0.0)
                ).filter_by(task_id=t.id).scalar() or 0.0
                pinned_hours[t.id] = float(ph)

            # Determine working days from first member
            first_member = session.query(Member).filter(Member.id.in_(int_member_ids)).first()
            working_day_names = first_member.working_days or ["Sun", "Mon", "Tue", "Wed", "Thu"]
            day_name_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
            working_day_nums = {day_name_map[d] for d in working_day_names if d in day_name_map}

            def is_working_day(d):
                return d.weekday() in working_day_nums

            # Start date
            if schedule_start_date:
                cursor_date = date_cls.fromisoformat(schedule_start_date)
            else:
                cursor_date = date_cls.today()

            # Distribute each member's tasks evenly
            # Assign tasks round-robin to members, then schedule each member's tasks sequentially
            member_task_map = {mid: [] for mid in int_member_ids}

            # Use existing assignments if available, else round-robin
            # If assignment points to a member NOT in scope, reassign it
            rr_index = 0
            member_id_set = set(int_member_ids)
            for t in leaf_tasks:
                existing = session.query(Assignment).filter_by(task_id=t.id).first()
                if existing and existing.member_id in member_id_set:
                    member_task_map[existing.member_id].append(t)
                else:
                    mid = int_member_ids[rr_index % len(int_member_ids)]
                    member_task_map[mid].append(t)
                    if existing:
                        # Reassign to in-scope member
                        existing.member_id = mid
                        existing.start_date = schedule_start_date or cursor_date.isoformat()
                        existing.end_date = schedule_start_date or cursor_date.isoformat()
                        session.flush()
                    else:
                        session.add(Assignment(
                            task_id=t.id, member_id=mid, allocated_hours=0.0,
                            start_date=schedule_start_date or cursor_date.isoformat(),
                            end_date=schedule_start_date or cursor_date.isoformat(),
                            field_overrides={"source": "auto"},
                        ))
                    rr_index += 1

            written = 0
            ghost_tasks = []
            preview_rows = [] if dry_run else None

            for mid in int_member_ids:
                member = session.query(Member).filter_by(id=mid).first()
                if not member:
                    continue
                member_cursor = date_cls.fromisoformat(schedule_start_date) if schedule_start_date else cursor_date

                for t in member_task_map[mid]:
                    total_effort = (t.estimated_hours or 0.0) + (t.buffer_hours or 0.0)
                    remaining = max(0.0, total_effort - pinned_hours.get(t.id, 0.0))
                    if remaining <= 0:
                        engine_log.append(f"Task '{t.name}': fully pinned, skip")
                        continue

                    # Determine scheduling window for this task
                    if respect_dates:
                        # Use task's own original dates
                        overrides = t.field_overrides or {}
                        orig_start = overrides.get("_original_start") or t.scheduled_start_date
                        orig_end = overrides.get("_original_end") or t.scheduled_end_date
                        if not orig_start or not orig_end:
                            engine_log.append(f"Task '{t.name}': no dates, skipping")
                            continue
                        task_cursor = date_cls.fromisoformat(orig_start)
                        task_end_limit = date_cls.fromisoformat(orig_end)
                    else:
                        task_cursor = member_cursor
                        task_end_limit = None  # no end limit — just exhaust effort

                    task_start = task_cursor
                    hours_placed = 0.0
                    max_days = 365  # safety limit

                    for _ in range(max_days):
                        if hours_placed >= remaining:
                            break
                        if task_end_limit and task_cursor > task_end_limit:
                            break
                        if not is_working_day(task_cursor):
                            task_cursor += timedelta(days=1)
                            continue

                        day_hours = min(chunk_hours, remaining - hours_placed)
                        if not dry_run:
                            session.add(DayAllocation(
                                task_id=t.id,
                                member_id=mid,
                                date=task_cursor.isoformat(),
                                hours=round(day_hours, 2),
                                source="engine",
                                pinned=False,
                            ))
                        else:
                            preview_rows.append({
                                "task_id": t.id,
                                "task_name": t.name,
                                "member_id": mid,
                                "member_name": member.display_name,
                                "date": task_cursor.isoformat(),
                                "hours": round(day_hours, 2),
                            })
                        hours_placed += day_hours
                        written += 1
                        task_cursor += timedelta(days=1)

                    task_end = task_cursor - timedelta(days=1)

                    # Update task dates (only when not respecting original dates)
                    if not dry_run and not respect_dates:
                        t.scheduled_start_date = task_start.isoformat()
                        t.scheduled_end_date = task_end.isoformat()

                    # In sequential mode, advance member cursor past this task
                    if not respect_dates:
                        member_cursor = task_cursor

                    unplaced = remaining - hours_placed
                    if unplaced > 0.01:
                        ghost_tasks.append({
                            "task_external_id": t.external_id,
                            "task_name": t.name,
                            "unscheduled_hours": round(unplaced, 2),
                        })

                    engine_log.append(
                        f"Even: '{t.name}' -> {member.display_name}: "
                        f"{round(hours_placed, 2)}h across {task_start} to {task_end} "
                        f"({chunk_hours}h/day)"
                        f"{' [respect_dates]' if respect_dates else ''}"
                    )

            if not dry_run:
                session.commit()

        _update_run(run_id, "succeeded", written=written if not dry_run else 0,
                    ghost_count=len(ghost_tasks))

        return 200, {
            "run_id": run_id,
            "status": "scheduled" if not ghost_tasks else "partially_schedulable",
            "dry_run": dry_run,
            "assignments_written": written if not dry_run else 0,
            "skipped_manual": 0,
            "ghost_tasks": ghost_tasks,
            "preview_rows": preview_rows,
            "overscheduled_tasks": [],
            "engine_log": engine_log,
        }

    def _handle_list_runs(self, environ, path_params, query, body):
        with get_db_session() as session:
            runs = session.query(PlanningRun).order_by(PlanningRun.triggered_at.desc()).limit(20).all()
            return 200, {"runs": [
                {
                    "run_id": r.run_id,
                    "status": r.status,
                    "triggered_at": r.triggered_at,
                    "completed_at": r.completed_at,
                    "written_count": r.written_count,
                    "ghost_task_count": r.ghost_task_count,
                }
                for r in runs
            ]}

    # ── Day-level reassignment ─────────────────────────────────────────────────

    def _handle_reassign_day(self, environ, path_params, query, body):
        """Move a specific day's allocation from one member to another.

        Body: {task_external_id, date, from_member_external_id, to_member_external_id}
        """
        self._require_auth(environ)
        data = body or {}
        for f in ("task_external_id", "date", "from_member_external_id", "to_member_external_id"):
            if not data.get(f):
                return 400, {"error": f"{f} is required."}

        with get_db_session() as session:
            task = session.query(Task).filter_by(external_id=data["task_external_id"]).first()
            from_member = session.query(Member).filter_by(external_id=data["from_member_external_id"]).first()
            to_member = session.query(Member).filter_by(external_id=data["to_member_external_id"]).first()

            if task is None:
                return 404, {"error": "Task not found."}
            if from_member is None:
                return 404, {"error": "from_member not found."}
            if to_member is None:
                return 404, {"error": "to_member not found."}

            date = data["date"]

            # Validate target date is a working day for the target member
            from datetime import date as date_cls
            _day_names_check = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            try:
                d_obj = date_cls.fromisoformat(date)
                to_wd = set(to_member.working_days or ["Sun", "Mon", "Tue", "Wed", "Thu"])
                if _day_names_check[d_obj.weekday()] not in to_wd:
                    return 400, {"error": f"{date} is a non-working day for {to_member.display_name}."}
            except (ValueError, TypeError):
                pass

            # Find the source allocation
            existing = session.query(DayAllocation).filter_by(
                task_id=task.id, member_id=from_member.id, date=date
            ).first()
            if existing is None:
                return 404, {"error": f"No allocation found for {data['task_external_id']} on {date}."}

            hours = existing.hours
            session.delete(existing)

            # Upsert to target member as manual
            target = session.query(DayAllocation).filter_by(
                task_id=task.id, member_id=to_member.id, date=date
            ).first()
            if target is None:
                session.add(DayAllocation(
                    task_id=task.id, member_id=to_member.id,
                    date=date, hours=hours, source="manual",
                ))
            else:
                target.hours += hours
                target.source = "manual"

            # Sync task dates from actual allocations
            _sync_task_dates_from_allocations(session, task.id)
            session.commit()
            return 200, {
                "ok": True,
                "task_external_id": data["task_external_id"],
                "date": date,
                "hours": hours,
                "from": data["from_member_external_id"],
                "to": data["to_member_external_id"],
            }

    def _handle_reassign_chunk(self, environ, path_params, query, body):
        """Move allocation chunk(s) to a different member and/or date.

        Body: {task_external_id, from_date, from_member_external_id,
               to_member_external_id, to_date, mode: "single"|"remaining"}
        """
        self._require_auth(environ)
        from datetime import date as date_cls, timedelta
        data = body or {}
        for f in ("task_external_id", "from_date", "from_member_external_id",
                  "to_member_external_id", "to_date", "mode"):
            if not data.get(f):
                return 400, {"error": "%s is required." % f}

        mode = data["mode"]  # "single" or "remaining"
        if mode not in ("single", "remaining"):
            return 400, {"error": "mode must be 'single' or 'remaining'."}

        with get_db_session() as session:
            task = session.query(Task).filter_by(external_id=data["task_external_id"]).first()
            from_member = session.query(Member).filter_by(external_id=data["from_member_external_id"]).first()
            to_member = session.query(Member).filter_by(external_id=data["to_member_external_id"]).first()

            if task is None:
                return 404, {"error": "Task not found."}
            if from_member is None or to_member is None:
                return 404, {"error": "Member not found."}

            from_date = data["from_date"]
            to_date = data["to_date"]

            try:
                date_cls.fromisoformat(to_date)
                date_cls.fromisoformat(from_date)
            except (ValueError, TypeError):
                return 400, {"error": "Invalid date format."}

            # Find allocations to move
            alloc_query = session.query(DayAllocation).filter_by(
                task_id=task.id, member_id=from_member.id,
            )
            if mode == "single":
                alloc_query = alloc_query.filter_by(date=from_date)
            else:
                alloc_query = alloc_query.filter(DayAllocation.date >= from_date)

            allocs = alloc_query.order_by(DayAllocation.date).all()
            if not allocs:
                return 404, {"error": "No allocations found."}

            # Setup capacity params for target member
            to_wd = set(to_member.working_days or ["Sun", "Mon", "Tue", "Wed", "Thu"])
            daily_cap = to_member.weekly_capacity_hours / max(len(to_wd), 1)

            # Load time-off dates for target member
            from services.persistence.models import TimeOff
            time_off_dates = set()
            for to_rec in session.query(TimeOff).filter_by(member_id=to_member.id).all():
                try:
                    cur = date_cls.fromisoformat(to_rec.start_date)
                    end = date_cls.fromisoformat(to_rec.end_date)
                except (ValueError, TypeError):
                    continue
                while cur <= end:
                    time_off_dates.add(cur.isoformat())
                    cur += timedelta(days=1)

            moved = 0

            if mode == "remaining":
                # ── Remaining: greedy-place all selected chunks from to_date ──
                total_hours = sum(a.hours for a in allocs)
                for alloc in allocs:
                    session.delete(alloc)
                session.flush()

                placements = _greedy_place(
                    session, task.id, to_member.id, to_date,
                    total_hours, daily_cap, to_wd, time_off_dates,
                )
                for ds, hrs in placements:
                    session.add(DayAllocation(
                        task_id=task.id, member_id=to_member.id,
                        date=ds, hours=hrs, source="manual",
                    ))
                    moved += 1
                session.flush()

            else:
                # ── Single: move chunk + trailing chunks forward, recalc preceding ──
                # Get ALL chunks for this task+member to split into before/after
                all_task_allocs = (
                    session.query(DayAllocation)
                    .filter_by(task_id=task.id, member_id=from_member.id)
                    .order_by(DayAllocation.date)
                    .all()
                )

                # Split: chunks before from_date stay, from_date + after move forward
                before_chunks = [a for a in all_task_allocs if a.date < from_date]
                moving_chunks = [a for a in all_task_allocs if a.date >= from_date]

                # Phase 1: move selected chunk + all following chunks to to_date
                moving_total = sum(a.hours for a in moving_chunks)
                for a in moving_chunks:
                    session.delete(a)
                session.flush()

                placements = _greedy_place(
                    session, task.id, to_member.id, to_date,
                    moving_total, daily_cap, to_wd, time_off_dates,
                )
                for ds, hrs in placements:
                    session.add(DayAllocation(
                        task_id=task.id, member_id=to_member.id,
                        date=ds, hours=hrs, source="manual",
                    ))
                    moved += 1
                session.flush()

                # Phase 2: recalculate preceding chunks greedily in place
                if before_chunks:
                    before_total = sum(a.hours for a in before_chunks)
                    earliest_date = before_chunks[0].date
                    for a in before_chunks:
                        session.delete(a)
                    session.flush()

                    from_wd = set(from_member.working_days or ["Sun", "Mon", "Tue", "Wed", "Thu"])
                    from_daily_cap = from_member.weekly_capacity_hours / max(len(from_wd), 1)
                    from_time_off = set()
                    for to_rec in session.query(TimeOff).filter_by(member_id=from_member.id).all():
                        try:
                            cur = date_cls.fromisoformat(to_rec.start_date)
                            end = date_cls.fromisoformat(to_rec.end_date)
                        except (ValueError, TypeError):
                            continue
                        while cur <= end:
                            from_time_off.add(cur.isoformat())
                            cur += timedelta(days=1)

                    replacements = _greedy_place(
                        session, task.id, from_member.id, earliest_date,
                        before_total, from_daily_cap, from_wd, from_time_off,
                    )
                    for ds, hrs in replacements:
                        session.add(DayAllocation(
                            task_id=task.id, member_id=from_member.id,
                            date=ds, hours=hrs, source="manual",
                        ))
                    session.flush()

            # Sync task dates from actual allocations
            _sync_task_dates_from_allocations(session, task.id)
            session.commit()
            return 200, {"ok": True, "moved": moved}

    def _handle_clear_schedule(self, environ, path_params, query, body):
        """Hard reset: clear ALL allocations for a project (only pinned survive).

        Also resets task dates back to their original values so the next
        engine run starts from a clean slate.
        """
        self._require_auth(environ)
        data = body or {}
        project_id = data.get("project_id")
        if not project_id:
            return 400, {"error": "project_id is required."}

        cleared = 0
        with get_db_session() as session:
            tasks = session.query(Task).filter_by(project_id=int(project_id)).all()
            task_ids = [t.id for t in tasks]
            if task_ids:
                # Delete ALL DayAllocations except pinned ones
                all_allocs = session.query(DayAllocation).filter(
                    DayAllocation.task_id.in_(task_ids),
                ).all()
                for da in all_allocs:
                    if da.pinned:
                        continue
                    session.delete(da)
                    cleared += 1
                # Delete auto-created and engine-created Assignments
                all_assigns = session.query(Assignment).filter(
                    Assignment.task_id.in_(task_ids),
                ).all()
                for a in all_assigns:
                    overrides = a.field_overrides or {}
                    src = overrides.get("source", "")
                    if src in ("auto", "engine"):
                        session.delete(a)
                # Reset task dates back to original values
                # Original dates are stored in field_overrides if the engine changed them;
                # otherwise restore from the _original_dates saved on first engine run.
                for t in tasks:
                    overrides = t.field_overrides or {}
                    if "_original_start" in overrides:
                        t.scheduled_start_date = overrides["_original_start"]
                    if "_original_end" in overrides:
                        t.scheduled_end_date = overrides["_original_end"]
            session.commit()
        return 200, {"ok": True, "cleared": cleared}

    def _handle_reset_to_import(self, environ, path_params, query, body):
        """Reset project schedule back to the state right after import.

        Supports two modes:
        - preflight=true: Returns pinned allocation details without changing anything.
          The frontend shows a confirmation dialog if pinned work exists.
        - preflight=false (default): Executes the reset.
          - include_pinned=true: Wipes everything including pinned allocations.
          - include_pinned=false (default): Preserves pinned allocations and their
            task dates. Only resets unpinned tasks to import state.
        """
        self._require_auth(environ)
        data = body or {}
        project_id = data.get("project_id")
        if not project_id:
            return 400, {"error": "project_id is required."}
        preflight = bool(data.get("preflight", False))
        include_pinned = bool(data.get("include_pinned", False))

        from services.persistence.models import ProjectMember

        with get_db_session() as session:
            project = session.query(Project).filter_by(id=int(project_id)).first()
            if project is None:
                return 404, {"error": "Project not found."}

            tasks = session.query(Task).filter_by(project_id=int(project_id)).all()
            task_ids = [t.id for t in tasks]

            # ── Preflight: report pinned allocations ─────────────────────
            if preflight:
                pinned_details = []
                if task_ids:
                    pinned_allocs = session.query(DayAllocation).filter(
                        DayAllocation.task_id.in_(task_ids),
                        DayAllocation.pinned == True,
                    ).all()
                    # Group by task
                    from collections import defaultdict
                    by_task = defaultdict(list)
                    for da in pinned_allocs:
                        by_task[da.task_id].append(da)
                    for tid, allocs in by_task.items():
                        t = next((t for t in tasks if t.id == tid), None)
                        member = session.query(Member).filter_by(
                            id=allocs[0].member_id).first() if allocs else None
                        pinned_details.append({
                            "task_id": tid,
                            "task_name": t.name if t else "?",
                            "member_name": member.display_name if member else "?",
                            "pinned_hours": round(sum(a.hours for a in allocs), 2),
                            "pinned_days": len(allocs),
                            "dates": sorted(set(a.date for a in allocs)),
                        })
                return 200, {
                    "has_pinned": len(pinned_details) > 0,
                    "pinned_count": len(pinned_details),
                    "pinned_details": pinned_details,
                }

            # ── Execute reset ────────────────────────────────────────────
            allocs_deleted = 0
            assigns_deleted = 0
            assigns_restored = 0
            pinned_kept = 0

            # Find tasks with pinned allocations (to preserve if !include_pinned)
            tasks_with_pinned = set()
            if not include_pinned and task_ids:
                for da in session.query(DayAllocation).filter(
                    DayAllocation.task_id.in_(task_ids),
                    DayAllocation.pinned == True,
                ).all():
                    tasks_with_pinned.add(da.task_id)

            if task_ids:
                # Delete DayAllocations
                all_allocs = session.query(DayAllocation).filter(
                    DayAllocation.task_id.in_(task_ids),
                ).all()
                for da in all_allocs:
                    if not include_pinned and da.pinned:
                        pinned_kept += 1
                        continue  # preserve pinned
                    session.delete(da)
                    allocs_deleted += 1

                # Delete Assignments (but preserve assignments for pinned tasks)
                all_assigns = session.query(Assignment).filter(
                    Assignment.task_id.in_(task_ids),
                ).all()
                for a in all_assigns:
                    if not include_pinned and a.task_id in tasks_with_pinned:
                        continue  # preserve assignment for pinned task
                    session.delete(a)
                    assigns_deleted += 1

                session.flush()

                # Reset task dates to originals and re-create import assignments
                # Skip tasks with pinned allocations (their dates/assignments stay)
                restored_member_ids = set()
                for t in tasks:
                    if not include_pinned and t.id in tasks_with_pinned:
                        # Keep pinned task's current state — collect its member
                        a = session.query(Assignment).filter_by(task_id=t.id).first()
                        if a:
                            restored_member_ids.add(a.member_id)
                        continue

                    overrides = dict(t.field_overrides or {})

                    # Restore original dates
                    if "_original_start" in overrides:
                        t.scheduled_start_date = overrides["_original_start"]
                    if "_original_end" in overrides:
                        t.scheduled_end_date = overrides["_original_end"]

                    # Re-create import assignment from stored assignee
                    imp_member_id = overrides.get("_import_assignee_member_id")
                    if imp_member_id:
                        start = overrides.get("_original_start") or t.scheduled_start_date
                        end = overrides.get("_original_end") or t.scheduled_end_date
                        if start and end:
                            session.add(Assignment(
                                task_id=t.id,
                                member_id=int(imp_member_id),
                                allocated_hours=0.0,
                                start_date=start,
                                end_date=end,
                                field_overrides={"source": "import", "allocation_percent": 100},
                            ))
                            assigns_restored += 1
                            restored_member_ids.add(int(imp_member_id))

                    # Clear scheduling overrides but keep import metadata
                    for key in ["_original_start", "_original_end",
                                "scheduled_start_date", "scheduled_end_date"]:
                        overrides.pop(key, None)
                    t.field_overrides = overrides

                # Rebuild ProjectMember rows from restored + pinned members
                for pm in session.query(ProjectMember).filter_by(project_id=int(project_id)).all():
                    session.delete(pm)
                session.flush()

                for mid in restored_member_ids:
                    session.add(ProjectMember(project_id=int(project_id), member_id=mid))

            session.commit()

        # Fallback: if no assignments were restored from stored data,
        # try re-syncing from Asana to recover them
        asana_synced = False
        if assigns_restored == 0 and project.asana_project_gid:
            try:
                status, result = self._handle_import_from_asana(
                    environ, {}, {},
                    {"asana_project_gid": project.asana_project_gid},
                )
                if status == 200:
                    asana_synced = True
                    assigns_restored = result.get("assignments", 0)
            except Exception:
                pass

        return 200, {
            "ok": True,
            "allocations_deleted": allocs_deleted,
            "assignments_deleted": assigns_deleted,
            "assignments_restored": assigns_restored,
            "pinned_kept": pinned_kept,
            "asana_synced": asana_synced,
        }

    def _handle_pin_allocation(self, environ, path_params, query, body):
        """Pin or unpin a specific DayAllocation.

        Body: {task_id, member_id, date, pinned: true|false}
        """
        self._require_auth(environ)
        data = body or {}
        for f in ("task_id", "member_id", "date", "pinned"):
            if f not in data:
                return 400, {"error": f"{f} is required."}

        with get_db_session() as session:
            da = session.query(DayAllocation).filter_by(
                task_id=int(data["task_id"]),
                member_id=int(data["member_id"]),
                date=data["date"],
            ).first()
            if da is None:
                return 404, {"error": "Allocation not found."}
            da.pinned = bool(data["pinned"])
            session.commit()
            return 200, {"ok": True, "pinned": da.pinned}

    def _handle_pin_task(self, environ, path_params, query, body):
        """Pin or unpin ALL DayAllocations for a task.

        Body: {task_id, pinned: true|false}
        """
        self._require_auth(environ)
        data = body or {}
        if "task_id" not in data or "pinned" not in data:
            return 400, {"error": "task_id and pinned are required."}

        with get_db_session() as session:
            allocs = session.query(DayAllocation).filter_by(
                task_id=int(data["task_id"]),
            ).all()
            count = 0
            for da in allocs:
                da.pinned = bool(data["pinned"])
                count += 1
            session.commit()
            return 200, {"ok": True, "pinned": bool(data["pinned"]), "count": count}

    # ── Asana sync handlers ────────────────────────────────────────────────────

    def _handle_asana_pull_preview(self, environ, path_params, query, body):
        """Compare Asana tasks against SQLite and return a delta list."""
        self._require_auth(environ)
        client = _get_asana_client()
        if client is None:
            return 503, {"error": "Asana not configured. Set ASANA_PAT and ASANA_PROJECT_GID env vars."}

        project_gid = _get_config("asana_project_gid") or os.environ.get("ASANA_PROJECT_GID", "")
        asana_tasks = client.get_tasks(project_gid)

        with get_db_session() as session:
            delta = []
            for at in asana_tasks:
                local = session.query(Task).filter_by(external_id=at["gid"]).first()
                if local is None:
                    delta.append({"gid": at["gid"], "name": at.get("name"), "action": "new_in_asana",
                                   "asana": at, "local": None})
                    continue
                for field, asana_val, local_val in [
                    ("due_on", at.get("due_on"), local.scheduled_end_date),
                    ("start_on", at.get("start_on"), local.scheduled_start_date),
                ]:
                    if asana_val != local_val:
                        delta.append({
                            "gid": at["gid"], "name": at.get("name"),
                            "action": "field_changed", "field": field,
                            "asana_value": asana_val, "local_value": local_val,
                        })
        return 200, {"delta": delta}

    def _handle_asana_pull_apply(self, environ, path_params, query, body):
        """Apply selected delta items from Asana pull to SQLite."""
        self._require_auth(environ)
        items = (body or {}).get("items", [])
        applied = 0
        with get_db_session() as session:
            for item in items:
                task = session.query(Task).filter_by(external_id=item.get("gid")).first()
                if task is None:
                    continue
                field = item.get("field")
                value = item.get("asana_value")
                if field == "due_on":
                    task.scheduled_end_date = value
                    applied += 1
                elif field == "start_on":
                    task.scheduled_start_date = value
                    applied += 1
            session.commit()
        return 200, {"applied": applied}

    def _handle_asana_push(self, environ, path_params, query, body):
        """Push current schedule (DayAllocation summary) back to Asana."""
        self._require_auth(environ)
        client = _get_asana_client()
        if client is None:
            return 503, {"error": "Asana not configured. Set ASANA_PAT and ASANA_PROJECT_GID env vars."}

        pushed = 0
        errors = []
        with get_db_session() as session:
            tasks = session.query(Task).all()
            for task in tasks:
                allocs = session.query(DayAllocation).filter_by(task_id=task.id).all()
                if not allocs:
                    continue
                dates = [a.date for a in allocs]
                start_on = min(dates)
                due_on = max(dates)
                # Find primary assignee (member with most hours)
                hours_by_member: Dict[int, float] = {}
                for a in allocs:
                    hours_by_member[a.member_id] = hours_by_member.get(a.member_id, 0) + a.hours
                primary_member_id = max(hours_by_member, key=hours_by_member.get)
                member = session.query(Member).filter_by(id=primary_member_id).first()

                fields = {"start_on": start_on, "due_on": due_on}
                if member and member.external_id:
                    fields["assignee"] = member.external_id

                try:
                    client.update_task(task.external_id, fields)
                    pushed += 1
                except Exception as exc:
                    errors.append({"task": task.external_id, "error": str(exc)})

        return 200, {"pushed": pushed, "errors": errors}

    # ── Project-scoped Asana push ──────────────────────────────────────────────

    def _handle_project_push_asana(self, environ, path_params, query, body):
        """Create/update tasks in Asana for a project, set parents and dependencies.

        Stores back the Asana GID in task.field_overrides["asana_gid"] for new tasks.
        """
        self._require_auth(environ)
        project_id = int(path_params["id"])

        client = _get_asana_client()
        if client is None:
            return 503, {"error": "Asana PAT not configured."}

        with get_db_session() as session:
            project = session.query(Project).filter_by(id=project_id).first()
            if project is None:
                return 404, {"error": "Project not found."}
            if not project.asana_project_gid:
                return 422, {"error": "Project is not linked to an Asana project. Link it on the Import screen."}

            asana_project_gid = project.asana_project_gid
            tasks = session.query(Task).filter_by(project_id=project_id).all()

            # Topological sort: tasks with parent_id=None first, then children
            # (simple two-pass: level 0 first, then by hierarchy_depth ascending)
            tasks_sorted = sorted(tasks, key=lambda t: (t.hierarchy_depth or 0, t.id))

            # Build hours-per-member per task to find primary assignee
            def _primary_assignee(task):
                allocs = session.query(DayAllocation).filter_by(task_id=task.id).all()
                if not allocs:
                    return None
                hours_by_member: Dict[int, float] = {}
                for a in allocs:
                    hours_by_member[a.member_id] = hours_by_member.get(a.member_id, 0) + a.hours
                member_id = max(hours_by_member, key=hours_by_member.get)
                return session.query(Member).filter_by(id=member_id).first()

            local_id_to_asana_gid: Dict[int, str] = {}
            created = 0
            updated = 0
            errors = []

            # Phase A — upsert tasks
            for task in tasks_sorted:
                try:
                    asana_gid = task.field_overrides.get("asana_gid") if task.field_overrides else None
                    fields: Dict[str, Any] = {
                        "name": task.name,
                    }
                    if task.scheduled_start_date:
                        fields["start_on"] = task.scheduled_start_date
                    if task.scheduled_end_date:
                        fields["due_on"] = task.scheduled_end_date
                    if task.estimated_hours:
                        fields["notes"] = "Estimated effort: %.1fh" % task.estimated_hours

                    # Assignee — use member.external_id if it looks like an Asana GID
                    assignee = _primary_assignee(task)
                    if assignee and assignee.external_id and assignee.external_id.isdigit() and len(assignee.external_id) > 8:
                        fields["assignee"] = assignee.external_id

                    # Parent (subtask relationship)
                    if task.parent_id and task.parent_id in local_id_to_asana_gid:
                        fields["parent"] = local_id_to_asana_gid[task.parent_id]

                    if asana_gid:
                        client.update_task(asana_gid, fields)
                        updated += 1
                    else:
                        fields["projects"] = [asana_project_gid]
                        new_task = client.create_task(fields)
                        asana_gid = new_task.get("gid", "")
                        if asana_gid:
                            overrides = dict(task.field_overrides or {})
                            overrides["asana_gid"] = asana_gid
                            task.field_overrides = overrides
                        created += 1

                    local_id_to_asana_gid[task.id] = asana_gid

                except Exception as exc:
                    errors.append({"task_id": task.id, "task_name": task.name, "error": str(exc)})

            session.flush()

            # Phase B — set FS dependencies
            task_ids = [t.id for t in tasks_sorted]
            deps = session.query(TaskDependency).filter(
                TaskDependency.predecessor_id.in_(task_ids),
                TaskDependency.successor_id.in_(task_ids),
            ).all()

            deps_set = 0
            for dep in deps:
                if dep.dependency_type != "FS":
                    continue
                successor_gid = local_id_to_asana_gid.get(dep.successor_id)
                predecessor_gid = local_id_to_asana_gid.get(dep.predecessor_id)
                if not successor_gid or not predecessor_gid:
                    continue
                try:
                    client.add_dependencies(successor_gid, [predecessor_gid])
                    deps_set += 1
                except Exception as exc:
                    errors.append({"dep": "%s→%s" % (dep.predecessor_id, dep.successor_id), "error": str(exc)})

            session.commit()

        return 200, {"created": created, "updated": updated, "deps_set": deps_set, "errors": errors}

    # ── Settings handlers ──────────────────────────────────────────────────────

    def _handle_get_settings(self, environ, path_params, query, body):
        return 200, {
            "asana_pat_set": bool(_get_config("asana_pat")),
            "asana_workspace_gid": _get_config("asana_workspace_gid"),
            "asana_project_gid": _get_config("asana_project_gid"),
        }

    def _handle_post_settings(self, environ, path_params, query, body):
        self._require_auth(environ)
        data = body or {}
        if "asana_pat" in data:
            pat = data["asana_pat"] or ""
            if not pat:
                # Empty string means "remove PAT"
                with get_db_session() as session:
                    for key in ("asana_pat", "asana_workspace_gid", "asana_project_gid"):
                        row = session.query(AppConfig).filter_by(key=key).first()
                        if row:
                            session.delete(row)
                    session.commit()
            else:
                from services.integration_service.asana_client import AsanaClient
                try:
                    client = AsanaClient(pat)
                    workspaces = client.get_workspaces()
                except Exception as exc:
                    return 400, {"error": "Invalid PAT: %s" % str(exc)}
                _set_config("asana_pat", pat)
                if workspaces:
                    _set_config("asana_workspace_gid", workspaces[0]["gid"])
        if "asana_project_gid" in data:
            _set_config("asana_project_gid", data["asana_project_gid"] or "")
        return 200, {"ok": True}

    # ── Project start date shift ─────────────────────────────────────────────

    def _handle_shift_project_start(self, environ, path_params, query, body):
        """Shift all task dates in a project by the offset between the current
        earliest start and the new_start_date."""
        self._require_auth(environ)
        from datetime import date, timedelta

        project_id = int(path_params["id"])
        data = body or {}
        new_start = data.get("new_start_date")
        if not new_start:
            return 400, {"error": "new_start_date is required."}

        with get_db_session() as session:
            project = session.query(Project).filter_by(id=project_id).first()
            if project is None:
                return 404, {"error": "Project not found."}

            tasks = session.query(Task).filter_by(project_id=project_id).all()
            start_dates = [t.scheduled_start_date for t in tasks if t.scheduled_start_date]
            if not start_dates:
                return 400, {"error": "No tasks with start dates to shift."}

            current_earliest = min(start_dates)
            try:
                old_date = date.fromisoformat(current_earliest)
                new_date = date.fromisoformat(new_start)
            except (ValueError, TypeError):
                return 400, {"error": "Invalid date format. Use YYYY-MM-DD."}

            offset = (new_date - old_date).days
            if offset == 0:
                return 200, {"ok": True, "shifted": 0}

            shifted = 0
            for t in tasks:
                changed = False
                if t.scheduled_start_date:
                    try:
                        d = date.fromisoformat(t.scheduled_start_date)
                        t.scheduled_start_date = (d + timedelta(days=offset)).isoformat()
                        changed = True
                    except (ValueError, TypeError):
                        pass
                if t.scheduled_end_date:
                    try:
                        d = date.fromisoformat(t.scheduled_end_date)
                        t.scheduled_end_date = (d + timedelta(days=offset)).isoformat()
                        changed = True
                    except (ValueError, TypeError):
                        pass
                if changed:
                    shifted += 1

            # Update project dates too
            if project.start_date:
                try:
                    d = date.fromisoformat(project.start_date)
                    project.start_date = (d + timedelta(days=offset)).isoformat()
                except (ValueError, TypeError):
                    pass
            if project.end_date:
                try:
                    d = date.fromisoformat(project.end_date)
                    project.end_date = (d + timedelta(days=offset)).isoformat()
                except (ValueError, TypeError):
                    pass

            session.commit()
        return 200, {"ok": True, "shifted": shifted, "offset_days": offset}

    # ── Project members ───────────────────────────────────────────────────────

    def _handle_list_project_members(self, environ, path_params, query, body):
        self._require_auth(environ)
        from services.persistence.models import Member, ProjectMember
        project_id = int(path_params["id"])
        with get_db_session() as session:
            rows = (
                session.query(ProjectMember, Member)
                .join(Member, ProjectMember.member_id == Member.id)
                .filter(ProjectMember.project_id == project_id)
                .all()
            )
            members = []
            for pm, m in rows:
                members.append({
                    "id": m.id,
                    "display_name": m.display_name,
                    "email": m.email,
                    "role": m.role,
                    "weekly_capacity_hours": m.weekly_capacity_hours,
                    "working_days": m.working_days,
                    "avatar_color": m.avatar_color,
                    "project_role": pm.role,
                })
        return 200, {"members": members}

    def _handle_add_project_members(self, environ, path_params, query, body):
        self._require_auth(environ)
        from services.persistence.models import ProjectMember
        project_id = int(path_params["id"])
        data = body or {}
        member_ids = data.get("member_ids", [])
        if not member_ids:
            return 400, {"error": "member_ids is required."}

        added = 0
        with get_db_session() as session:
            project = session.query(Project).filter_by(id=project_id).first()
            if project is None:
                return 404, {"error": "Project not found."}
            for mid in member_ids:
                existing = session.query(ProjectMember).filter_by(
                    project_id=project_id, member_id=int(mid)
                ).first()
                if existing is None:
                    session.add(ProjectMember(project_id=project_id, member_id=int(mid)))
                    added += 1
            session.commit()
        return 200, {"ok": True, "added": added}

    def _handle_remove_project_member(self, environ, path_params, query, body):
        self._require_auth(environ)
        from services.persistence.models import ProjectMember
        project_id = int(path_params["id"])
        member_id = int(path_params["member_id"])
        data = body or {}
        force = data.get("force", False)

        with get_db_session() as session:
            # Check for allocations before removing
            task_ids = [t.id for t in session.query(Task).filter_by(project_id=project_id).all()]
            affected_allocs = []
            if task_ids:
                affected_allocs = session.query(DayAllocation).filter(
                    DayAllocation.member_id == member_id,
                    DayAllocation.task_id.in_(task_ids),
                ).all()

            if affected_allocs and not force:
                # Return affected tasks for reassignment UI
                task_hours = {}
                for da in affected_allocs:
                    task_hours[da.task_id] = task_hours.get(da.task_id, 0.0) + da.hours
                affected_tasks = []
                for tid, hours in task_hours.items():
                    t = session.query(Task).filter_by(id=tid).first()
                    if t:
                        affected_tasks.append({"id": t.id, "name": t.name, "hours": hours, "external_id": t.external_id})
                return 409, {
                    "error": "Member has allocated tasks. Reassign first.",
                    "affected_tasks": affected_tasks,
                }

            # Remove ProjectMember row if it exists
            pm = session.query(ProjectMember).filter_by(
                project_id=project_id, member_id=member_id
            ).first()
            if pm:
                session.delete(pm)

            # Also remove any assignments for this member on project tasks
            if task_ids:
                for a in session.query(Assignment).filter(
                    Assignment.task_id.in_(task_ids),
                    Assignment.member_id == member_id,
                ).all():
                    session.delete(a)

            session.commit()
        return 200, {"ok": True}

    # ── Asana setup helpers ────────────────────────────────────────────────────

    def _handle_asana_workspaces(self, environ, path_params, query, body):
        self._require_auth(environ)
        client = _get_asana_client()
        if client is None:
            return 503, {"error": "Asana PAT not configured."}
        workspaces = client.get_workspaces()
        return 200, {"workspaces": workspaces}

    def _handle_asana_projects(self, environ, path_params, query, body):
        self._require_auth(environ)
        client = _get_asana_client()
        if client is None:
            return 503, {"error": "Asana PAT not configured."}
        workspace_gid = _get_config("asana_workspace_gid")
        if not workspace_gid:
            return 422, {"error": "No workspace detected. Re-save your PAT."}
        projects = client.get_projects(workspace_gid)
        return 200, {"projects": projects}

    # ── Member sync handlers ───────────────────────────────────────────────────

    def _handle_asana_members_preview(self, environ, path_params, query, body):
        self._require_auth(environ)
        client = _get_asana_client()
        if client is None:
            return 503, {"error": "Asana PAT not configured."}
        workspace_gid = _get_config("asana_workspace_gid")
        if not workspace_gid:
            return 422, {"error": "No workspace configured."}

        asana_users = client.get_workspace_users(workspace_gid)

        with get_db_session() as session:
            local_members = session.query(Member).all()
            local_by_ext = {m.external_id: m for m in local_members}
            asana_by_gid = {u["gid"]: u for u in asana_users}

            to_add = []
            for u in asana_users:
                if u["gid"] not in local_by_ext:
                    to_add.append({"gid": u["gid"], "name": u.get("name"), "email": u.get("email")})

            to_update = []
            for ext_id, member in local_by_ext.items():
                asana_user = asana_by_gid.get(ext_id)
                if asana_user is None:
                    continue
                changes = {}
                if asana_user.get("name") and asana_user["name"] != member.display_name:
                    changes["display_name"] = {"from": member.display_name, "to": asana_user["name"]}
                if asana_user.get("email") and asana_user["email"] != (member.email or ""):
                    changes["email"] = {"from": member.email, "to": asana_user["email"]}
                if changes:
                    to_update.append({"gid": ext_id, "name": member.display_name, "changes": changes})

            to_delete = []
            for ext_id, member in local_by_ext.items():
                # Only flag members whose external_id looks like an Asana GID (numeric string)
                if ext_id not in asana_by_gid and ext_id.isdigit():
                    to_delete.append({"id": member.id, "ext_id": ext_id, "name": member.display_name})

        return 200, {"to_add": to_add, "to_update": to_update, "to_delete": to_delete}

    def _handle_asana_members_apply(self, environ, path_params, query, body):
        """Apply selected member changes from Asana preview.

        Body: {"add": [gid,...], "update": [gid,...], "delete": [gid,...]}
        """
        self._require_auth(environ)
        client = _get_asana_client()
        if client is None:
            return 503, {"error": "Asana PAT not configured."}
        workspace_gid = _get_config("asana_workspace_gid")
        if not workspace_gid:
            return 422, {"error": "No workspace configured."}

        asana_users = {u["gid"]: u for u in client.get_workspace_users(workspace_gid)}
        data = body or {}
        added = updated = deleted = 0

        with get_db_session() as session:
            for gid in (data.get("add") or []):
                u = asana_users.get(gid)
                if not u:
                    continue
                session.add(Member(
                    external_id=gid,
                    display_name=u.get("name") or gid,
                    email=u.get("email"),
                    weekly_capacity_hours=40.0,
                    working_days=["Sun", "Mon", "Tue", "Wed", "Thu"],
                ))
                added += 1

            for gid in (data.get("update") or []):
                u = asana_users.get(gid)
                m = session.query(Member).filter_by(external_id=gid).first()
                if not u or not m:
                    continue
                if u.get("name"):
                    m.display_name = u["name"]
                if u.get("email"):
                    m.email = u["email"]
                updated += 1

            for gid in (data.get("delete") or []):
                m = session.query(Member).filter_by(external_id=gid).first()
                if m:
                    session.delete(m)
                    deleted += 1

            session.commit()

        return 200, {"added": added, "updated": updated, "deleted": deleted}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read_raw_body(environ) -> Optional[bytes]:
    """Read raw request body as bytes."""
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except (ValueError, TypeError):
        length = 0
    if length > 0:
        return environ["wsgi.input"].read(length)
    return None


def _serialize_task(task: Task, session=None) -> dict:
    result = {
        "id": task.id,
        "external_id": task.external_id,
        "project_id": task.project_id,
        "parent_id": task.parent_id,
        "hierarchy_depth": task.hierarchy_depth or 0,
        "name": task.name,
        "status": task.status,
        "estimated_hours": task.estimated_hours,
        "buffer_hours": task.buffer_hours,
        "scheduled_start_date": task.scheduled_start_date,
        "scheduled_end_date": task.scheduled_end_date,
        "field_overrides": task.field_overrides,
    }
    if session is not None:
        # Derive assignees from DayAllocations (source of truth), falling back to Assignments
        alloc_member_ids = [
            row[0] for row in
            session.query(DayAllocation.member_id).filter_by(task_id=task.id).distinct().all()
        ]
        if not alloc_member_ids:
            alloc_member_ids = [a.member_id for a in session.query(Assignment).filter_by(task_id=task.id).all()]
        if alloc_member_ids:
            members = session.query(Member).filter(Member.id.in_(alloc_member_ids)).all()
            result["assignees"] = [
                {"id": m.id, "display_name": m.display_name, "avatar_color": m.avatar_color}
                for m in members
            ]
        else:
            result["assignees"] = []
    return result


def _serialize_member(member: Member) -> dict:
    return {
        "id": member.id,
        "external_id": member.external_id,
        "display_name": member.display_name,
        "weekly_capacity_hours": member.weekly_capacity_hours,
        "working_days": member.working_days,
        "is_active": member.is_active,
        "role": member.role,
        "avatar_color": member.avatar_color,
    }


def _update_run(
    run_id: str,
    status: str,
    written: int = 0,
    ghost_count: int = 0,
    error: Optional[str] = None,
) -> None:
    """Update PlanningRun status in SQLite."""
    with get_db_session() as session:
        run = session.query(PlanningRun).filter_by(run_id=run_id).first()
        if run:
            run.status = status
            run.completed_at = _now_iso()
            run.written_count = written
            run.ghost_task_count = ghost_count
            if error:
                run.error_message = error
            session.commit()


def _get_config(key: str) -> Optional[str]:
    """Read a value from the AppConfig table."""
    with get_db_session() as session:
        row = session.query(AppConfig).filter_by(key=key).first()
        return row.value if row else None


def _set_config(key: str, value: str) -> None:
    """Write a value to the AppConfig table (upsert)."""
    with get_db_session() as session:
        row = session.query(AppConfig).filter_by(key=key).first()
        if row:
            row.value = value
        else:
            session.add(AppConfig(key=key, value=value))
        session.commit()


def _get_asana_client():
    """Return an AsanaClient using the DB-stored PAT (falls back to env var)."""
    pat = _get_config("asana_pat") or os.environ.get("ASANA_PAT", "")
    if not pat:
        return None
    try:
        from services.integration_service.asana_client import AsanaClient
        return AsanaClient(pat)
    except ImportError:
        return None


# ── Dummy progressor (keeps server.py compatible) ─────────────────────────────

class _NoopProgressor:
    def start(self): pass
    def stop(self): pass


@dataclass(frozen=True)
class FloatRuntime:
    workflow_auto_progressor: Any = None

    def __post_init__(self):
        object.__setattr__(self, "workflow_auto_progressor", _NoopProgressor())


# ── Factory ────────────────────────────────────────────────────────────────────

def build_float_runtime() -> Tuple[FloatRuntime, FloatApplication]:
    """Build the unified FloatApplication (single DB, no in-memory state)."""
    app = FloatApplication()
    runtime = FloatRuntime()
    return runtime, app
