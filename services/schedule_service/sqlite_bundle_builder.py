"""Builds a NormalizedSourceBundle from the SQLite database.

This is the bridge between the Float SQLite store and the Planning Engine.
The engine only understands NormalizedSourceBundle — this class translates
the SQLite models into that contract so the engine can run.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from datetime import date, timedelta
from typing import TYPE_CHECKING, Dict, List, Tuple

from services.integration_service.contracts import (
    NormalizedDependencyRecord,
    NormalizedResourceAssignmentRecord,
    NormalizedResourceExceptionRecord,
    NormalizedResourceRecord,
    NormalizedSourceBundle,
    NormalizedTaskRecord,
    SourceArtifact,
    SourceReadiness,
    SourceSnapshot,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


class SQLiteSourceBundleBuilder:
    """Reads the SQLite store and builds a NormalizedSourceBundle for the planning engine."""

    def build(
        self,
        session: "Session",
        project_id: int = None,
        member_ids: list = None,
        effort_overrides: dict = None,
        task_ids: list = None,
        schedule_start_date: str = None,
    ) -> NormalizedSourceBundle:
        from services.persistence.models import Assignment, DayAllocation, Member, Task, TaskDependency, TimeOff

        # ── 1. Members → NormalizedResourceRecord ─────────────────────────────
        member_query = session.query(Member).filter_by(is_active=True)
        if member_ids:
            member_query = member_query.filter(Member.id.in_(member_ids))
        members = member_query.all()
        resources: List[NormalizedResourceRecord] = []
        for m in members:
            working_days = m.working_days or ["Sun", "Mon", "Tue", "Wed", "Thu"]
            daily_capacity = m.weekly_capacity_hours / max(len(working_days), 1)
            resources.append(NormalizedResourceRecord(
                resource_id=_stable_id("resource", str(m.id)),
                source_snapshot_id="",  # filled below after snapshot is built
                source_system="sqlite",
                external_resource_id=m.external_id,
                display_name=m.display_name,
                calendar_id=_stable_id("calendar", str(m.id)),
                calendar_name=None,
                default_daily_capacity_hours=daily_capacity,
                working_days=working_days,
                availability_ratio=1.0,
            ))

        # ── 2. Time Off → NormalizedResourceExceptionRecord (one per day) ─────
        member_ext_to_resource_id = {r.external_resource_id: r.resource_id for r in resources}
        time_offs = session.query(TimeOff).all()
        resource_exceptions: List[NormalizedResourceExceptionRecord] = []
        for to in time_offs:
            member = session.query(Member).filter_by(id=to.member_id).first()
            if member is None:
                continue
            resource_id = member_ext_to_resource_id.get(member.external_id)
            if resource_id is None:
                continue
            try:
                start = date.fromisoformat(to.start_date)
                end = date.fromisoformat(to.end_date)
            except (ValueError, TypeError):
                continue
            current = start
            while current <= end:
                resource_exceptions.append(NormalizedResourceExceptionRecord(
                    exception_id=_stable_id("exception", str(to.id), current.isoformat()),
                    source_snapshot_id="",
                    source_system="sqlite",
                    resource_id=resource_id,
                    resource_external_id=member.external_id,
                    date=current.isoformat(),
                    available_capacity_hours=0.0,
                    reason=to.leave_type,
                ))
                current += timedelta(days=1)

        # ── 3. Tasks → NormalizedTaskRecord ───────────────────────────────────
        if task_ids:
            int_task_id_list = [int(t) for t in task_ids]
            # Also include predecessor tasks (even completed/already scheduled)
            # so the engine can resolve dependency chains.
            from services.persistence.models import TaskDependency as _TD
            pred_ids = set()
            dep_rows = session.query(_TD).filter(_TD.successor_id.in_(int_task_id_list)).all()
            for dr in dep_rows:
                pred_ids.add(dr.predecessor_id)
            # Recursively find transitive predecessors
            frontier = set(pred_ids)
            while frontier:
                deeper = set()
                for dr in session.query(_TD).filter(_TD.successor_id.in_(frontier)).all():
                    if dr.predecessor_id not in pred_ids:
                        deeper.add(dr.predecessor_id)
                        pred_ids.add(dr.predecessor_id)
                frontier = deeper
            all_needed_ids = set(int_task_id_list) | pred_ids
            # Selected tasks: exclude cancelled/completed; predecessors: include all (even completed)
            task_query = session.query(Task).filter(Task.status != "cancelled")
            if project_id is not None:
                task_query = task_query.filter(Task.project_id == project_id)
            task_query = task_query.filter(Task.id.in_(all_needed_ids))
        else:
            task_query = session.query(Task).filter(Task.status.notin_(["cancelled", "completed"]))
            if project_id is not None:
                task_query = task_query.filter(Task.project_id == project_id)
        tasks = task_query.all()
        task_records: List[NormalizedTaskRecord] = []
        task_int_id_to_record: dict = {}
        _effort_overrides = effort_overrides or {}
        # Track which tasks are context-only predecessors (not user-selected)
        _context_only_ids = set()
        if task_ids:
            _selected_set = set(int(t) for t in task_ids)
            _context_only_ids = {t.id for t in tasks if t.id not in _selected_set}
        # Parent tasks are containers — they don't carry effort. Give them 0
        # so the engine marks them SCHEDULED instantly and their dependents
        # can proceed. Only leaf tasks (no children) carry real effort.
        _parent_ids = {t.parent_id for t in tasks if t.parent_id}

        for t in tasks:
            task_id = _stable_id("task", str(t.id))
            # Context-only predecessors get 0 effort so engine marks them as "done"
            if t.id in _context_only_ids:
                task_effort = 0.0
            elif t.id in _parent_ids:
                # Parent tasks are containers — 0 effort so engine auto-SCHEDULEs them
                task_effort = 0.0
            elif t.id in _effort_overrides:
                task_effort = _effort_overrides[t.id]
            else:
                if t.estimated_hours is None and t.buffer_hours is None:
                    task_effort = None
                else:
                    task_effort = (t.estimated_hours or 0.0) + (t.buffer_hours or 0.0)
            # Unpinned tasks use _original_start so the engine can re-optimize
            # when capacity is freed. Pinned tasks keep their current start.
            _has_pinned = session.query(DayAllocation).filter_by(
                task_id=t.id, pinned=True).first() is not None
            _overrides = t.field_overrides or {}
            if _has_pinned or t.id in _context_only_ids:
                effective_start = t.scheduled_start_date
            else:
                effective_start = _overrides.get("_original_start") or t.scheduled_start_date
            # schedule_start_date override takes precedence if explicitly provided
            if schedule_start_date and t.id not in _context_only_ids:
                effective_start = schedule_start_date
            task_records.append(NormalizedTaskRecord(
                task_id=task_id,
                source_snapshot_id="",
                source_system="sqlite",
                external_task_id=t.external_id,
                project_id=_stable_id("project", str(t.project_id)),
                project_external_id=str(t.project_id),  # project external_id resolved below
                parent_task_id=None,
                name=t.name,
                hierarchy_path=[task_id],
                hierarchy_depth=0,
                effort_hours=task_effort,
                start_date=effective_start,
                due_date=t.scheduled_end_date,
            ))
            task_int_id_to_record[t.id] = task_records[-1]

        # Fix project_external_id using actual project external_id from DB
        from services.persistence.models import Project
        projects = session.query(Project).all()
        project_id_to_external: dict = {p.id: p.external_id for p in projects}
        task_records_fixed: List[NormalizedTaskRecord] = []
        for rec in task_records:
            t_db = next((t for t in tasks if _stable_id("task", str(t.id)) == rec.task_id), None)
            if t_db is None:
                task_records_fixed.append(rec)
                continue
            proj_ext = project_id_to_external.get(t_db.project_id, str(t_db.project_id))
            task_records_fixed.append(NormalizedTaskRecord(
                task_id=rec.task_id,
                source_snapshot_id=rec.source_snapshot_id,
                source_system=rec.source_system,
                external_task_id=rec.external_task_id,
                project_id=_stable_id("project", str(t_db.project_id)),
                project_external_id=proj_ext,
                parent_task_id=rec.parent_task_id,
                name=rec.name,
                hierarchy_path=rec.hierarchy_path,
                hierarchy_depth=rec.hierarchy_depth,
                effort_hours=rec.effort_hours,
                start_date=rec.start_date,
                due_date=rec.due_date,
            ))
        task_records = task_records_fixed
        # Rebuild lookup after fix
        task_records_fixed = task_records
        task_int_id_to_record = {
            t.id: next(r for r in task_records if r.external_task_id == t.external_id)
            for t in tasks
        }

        # ── 4. Task Dependencies → NormalizedDependencyRecord ─────────────────
        deps = session.query(TaskDependency).all()
        dep_records: List[NormalizedDependencyRecord] = []
        for dep in deps:
            pred_rec = task_int_id_to_record.get(dep.predecessor_id)
            succ_rec = task_int_id_to_record.get(dep.successor_id)
            if pred_rec is None or succ_rec is None:
                continue
            # Skip deps involving parent/summary tasks — they are containers,
            # not schedulable units. Their dates span all children and would
            # incorrectly constrain leaf task scheduling.
            if dep.predecessor_id in _parent_ids or dep.successor_id in _parent_ids:
                continue
            dep_records.append(NormalizedDependencyRecord(
                dependency_id=_stable_id("dep", str(dep.id)),
                source_snapshot_id="",
                source_system="sqlite",
                predecessor_task_id=pred_rec.task_id,
                successor_task_id=succ_rec.task_id,
                predecessor_external_task_id=pred_rec.external_task_id,
                successor_external_task_id=succ_rec.external_task_id,
                dependency_type=dep.dependency_type or "FS",
            ))

        # ── 5. Assignments → NormalizedResourceAssignmentRecord ───────────────
        assignments = session.query(Assignment).all()
        assignment_records: List[NormalizedResourceAssignmentRecord] = []
        for a in assignments:
            task_rec = task_int_id_to_record.get(a.task_id)
            member = session.query(Member).filter_by(id=a.member_id).first()
            if task_rec is None or member is None:
                continue
            resource_id = member_ext_to_resource_id.get(member.external_id)
            if resource_id is None:
                continue
            allocation_percent = a.field_overrides.get("allocation_percent")
            assignment_records.append(NormalizedResourceAssignmentRecord(
                assignment_id=_stable_id("assignment", str(a.id)),
                source_snapshot_id="",
                source_system="sqlite",
                task_id=task_rec.task_id,
                task_external_id=task_rec.external_task_id,
                resource_id=resource_id,
                resource_external_id=member.external_id,
                allocation_percent=allocation_percent,
            ))

        # ── 5b. Cross-project capacity deductions ──────────────────────────────
        # Load ALL DayAllocations for in-scope members (across ALL projects) that
        # are NOT part of the current scheduling scope. This ensures the engine sees
        # the member's TRUE remaining availability per day.
        # Also handles manual allocations that reduce (not eliminate) capacity.
        try:
            from collections import defaultdict
            from services.persistence.models import DayAllocation

            # Collect task IDs in the current scheduling scope
            in_scope_task_ids = {t.id for t in tasks}

            # Load ALL allocations for in-scope members — manual from any project,
            # plus engine/manual allocations from OTHER projects
            member_db_ids = set()
            for m in members:
                member_db_ids.add(m.id)

            committed_by_key = defaultdict(float)  # (member_id, date) → hours
            committed_member_ids = set()

            if member_db_ids:
                # All allocations for these members
                all_allocs = session.query(DayAllocation).filter(
                    DayAllocation.member_id.in_(member_db_ids)
                ).all()
                for da in all_allocs:
                    if da.task_id in in_scope_task_ids and da.source == "engine":
                        # Engine allocations for in-scope tasks will be regenerated
                        continue
                    if da.task_id in in_scope_task_ids and da.source == "manual" and not da.pinned:
                        # Unpinned manual allocations for in-scope tasks will be replanned
                        continue
                    # Pinned manual in-scope + all out-of-scope allocations reduce capacity
                    committed_by_key[(da.member_id, da.date)] += da.hours
                    committed_member_ids.add(da.member_id)

            manual_by_key = committed_by_key
            manual_member_ids = committed_member_ids

            # Build member lookup for daily capacity
            member_capacity_cache = {}
            for mid in manual_member_ids:
                member = session.query(Member).filter_by(id=mid).first()
                if member is None:
                    continue
                resource_id = member_ext_to_resource_id.get(member.external_id)
                if resource_id is None:
                    continue
                working_days = member.working_days or ["Sun", "Mon", "Tue", "Wed", "Thu"]
                daily_cap = member.weekly_capacity_hours / max(len(working_days), 1)
                member_capacity_cache[mid] = (member.external_id, resource_id, daily_cap)

            for (mid, d), manual_hours in manual_by_key.items():
                if mid not in member_capacity_cache:
                    continue
                ext_id, resource_id, daily_cap = member_capacity_cache[mid]
                remaining_capacity = max(0.0, daily_cap - manual_hours)
                resource_exceptions.append(NormalizedResourceExceptionRecord(
                    exception_id=_stable_id("manual-da", str(mid), d),
                    source_snapshot_id="",
                    source_system="sqlite",
                    resource_id=resource_id,
                    resource_external_id=ext_id,
                    date=d,
                    available_capacity_hours=remaining_capacity,
                    reason="manual_reassignment",
                ))
        except Exception:
            pass  # DayAllocation table may not exist yet on first run

        # ── 6. Build SourceArtifact + SourceSnapshot ──────────────────────────
        content_hash = _stable_id(
            str(len(resources)),
            str(len(task_records)),
            str(len(dep_records)),
            str(len(assignment_records)),
        )
        artifact_id = _stable_id("artifact", "sqlite", content_hash)
        snapshot_id = _stable_id("snapshot", "sqlite", content_hash)

        artifact = SourceArtifact(
            artifact_id=artifact_id,
            external_artifact_id=artifact_id,
            source_system="sqlite",
            captured_at=date.today().isoformat(),
            payload_digest=content_hash,
            raw_payload={},
        )
        snapshot = SourceSnapshot(
            snapshot_id=snapshot_id,
            artifact_id=artifact_id,
            source_system="sqlite",
            captured_at=date.today().isoformat(),
            project_count=len(projects),
            task_count=len(task_records),
            dependency_count=len(dep_records),
            assignment_count=len(assignment_records),
            issue_count=0,
        )

        # Backfill snapshot_id into all records (frozen dataclasses require replacement)
        def _with_snapshot(rec, snapshot_id=snapshot_id):
            fields = {f.name: getattr(rec, f.name) for f in dataclasses.fields(rec)}
            fields["source_snapshot_id"] = snapshot_id
            return rec.__class__(**fields)

        resources = [_with_snapshot(r) for r in resources]
        resource_exceptions = [_with_snapshot(e) for e in resource_exceptions]
        task_records = [_with_snapshot(t) for t in task_records]
        dep_records = [_with_snapshot(d) for d in dep_records]
        assignment_records = [_with_snapshot(a) for a in assignment_records]

        source_readiness = SourceReadiness(
            state="ready" if task_records else "empty",
            runnable=len(task_records) > 0,
            blocking_issue_count=0,
            advisory_issue_count=0,
            total_issue_count=0,
        )

        return NormalizedSourceBundle(
            artifact=artifact,
            snapshot=snapshot,
            project_mappings=[],
            task_mappings=[],
            resource_mappings=[],
            tasks=task_records,
            dependencies=dep_records,
            resource_assignments=assignment_records,
            resources=resources,
            resource_exceptions=resource_exceptions,
            issue_facts=[],
            source_readiness=source_readiness,
        )

    def analyze_ownership_conflicts(
        self,
        session: "Session",
        project_id: int,
        member_ids: list,
        task_ids: list = None,
    ) -> List[dict]:
        """Detect tasks where the current owner can't be used or has capacity issues.

        Returns a list of conflict dicts, each with options for the user to choose from.
        Called as a preflight before scheduling so the user can resolve conflicts.
        """
        from services.persistence.models import (
            Assignment, DayAllocation, Member, Task, TaskDependency, TimeOff, ProjectMember,
        )
        from sqlalchemy import func as sa_func
        from datetime import date, timedelta

        int_project_id = int(project_id)
        int_member_ids = [int(m) for m in member_ids]
        int_member_id_set = set(int_member_ids)
        int_task_ids = [int(t) for t in task_ids] if task_ids else None

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        # Load tasks in scope
        task_query = session.query(Task).filter(
            Task.status.notin_(["cancelled", "completed"]),
            Task.project_id == int_project_id,
        )
        if int_task_ids:
            task_query = task_query.filter(Task.id.in_(int_task_ids))
        all_tasks = task_query.all()
        parent_ids = {t.parent_id for t in all_tasks if t.parent_id}
        leaf_tasks = [t for t in all_tasks if t.id not in parent_ids]

        # Build member capacity info
        members_by_id = {
            m.id: m for m in session.query(Member).filter_by(is_active=True).all()
        }

        def _project_dates_for_member(task, member_id):
            """Walk from task's earliest possible start, accumulating member's
            available capacity until task effort is placed. Returns (projected_start, projected_end).
            Uses _original_start for unpinned tasks (engine is free to optimize)."""
            m = members_by_id.get(member_id)
            if not m or not task.scheduled_start_date:
                return None, None
            # Pinned tasks keep their current start; unpinned use earliest possible
            has_pinned = session.query(DayAllocation).filter_by(
                task_id=task.id, pinned=True).first() is not None
            if has_pinned:
                effective_start = task.scheduled_start_date
            else:
                overrides = task.field_overrides or {}
                effective_start = overrides.get("_original_start") or task.scheduled_start_date
            total_effort = (task.estimated_hours or 0.0) + (task.buffer_hours or 0.0)
            if total_effort <= 0:
                return effective_start, effective_start
            daily_cap = m.weekly_capacity_hours / max(len(m.working_days or []), 1)
            wd_set = set(m.working_days or [])

            # Load cross-project + other-task allocations for this member
            allocs_by_date = {}
            for row_date, row_hours in session.query(
                DayAllocation.date, sa_func.sum(DayAllocation.hours),
            ).filter_by(member_id=member_id).group_by(DayAllocation.date).all():
                allocs_by_date[row_date] = float(row_hours or 0)

            # Load time-off
            time_off_dates = set()
            for to in session.query(TimeOff).filter_by(member_id=member_id).all():
                try:
                    to_s = date.fromisoformat(to.start_date)
                    to_e = date.fromisoformat(to.end_date)
                except (ValueError, TypeError):
                    continue
                cur = to_s
                while cur <= to_e:
                    time_off_dates.add(cur.isoformat())
                    cur += timedelta(days=1)

            accumulated = 0.0
            first_work_date = None
            d = date.fromisoformat(effective_start)
            max_walk = 365  # safety limit
            for _ in range(max_walk):
                ds = d.isoformat()
                if day_names[d.weekday()] in wd_set and ds not in time_off_dates:
                    committed = allocs_by_date.get(ds, 0.0)
                    avail = max(0.0, daily_cap - committed)
                    if avail > 0 and first_work_date is None:
                        first_work_date = ds
                    accumulated += avail
                if accumulated >= total_effort:
                    return first_work_date or ds, d.isoformat()
                d += timedelta(days=1)
            return first_work_date or d.isoformat(), d.isoformat()  # fallback

        conflicts = []
        for t in leaf_tasks:
            total_effort = (t.estimated_hours or 0.0) + (t.buffer_hours or 0.0)
            if total_effort <= 0:
                continue

            assign = session.query(Assignment).filter_by(task_id=t.id).first()
            current_owner_id = assign.member_id if assign else None
            current_owner = members_by_id.get(current_owner_id) if current_owner_id else None

            # Determine conflict type
            if current_owner_id is None:
                issue = "no_owner"
            elif current_owner_id not in int_member_id_set:
                issue = "owner_not_in_scope"
            else:
                # Owner is in scope — check capacity
                _, proj_end = _project_dates_for_member(t, current_owner_id)
                orig_end = t.scheduled_end_date
                if proj_end and orig_end and proj_end > orig_end:
                    # Calculate how many extra days
                    try:
                        delta = (date.fromisoformat(proj_end) - date.fromisoformat(orig_end)).days
                    except (ValueError, TypeError):
                        delta = 0
                    if delta > 5:  # more than a week slip → flag as tight
                        issue = "capacity_tight"
                    else:
                        continue  # minor extension, no conflict
                else:
                    continue  # fits fine, no conflict

            # Build options
            options = []

            # Option: keep current owner (even if not in scope)
            if current_owner_id and current_owner:
                proj_start, proj_end = _project_dates_for_member(t, current_owner_id)
                options.append({
                    "action": "keep",
                    "label": f"Keep {current_owner.display_name} ({proj_start} to {proj_end})",
                    "target_member_id": current_owner_id,
                    "target_member_name": current_owner.display_name,
                    "projected_start": proj_start,
                    "projected_end": proj_end,
                })

            # Options: reassign to each in-scope member
            member_options = []
            for mid in int_member_ids:
                if mid == current_owner_id:
                    continue
                m = members_by_id.get(mid)
                if not m:
                    continue
                proj_start, proj_end = _project_dates_for_member(t, mid)
                member_options.append({
                    "action": "reassign",
                    "label": f"Reassign to {m.display_name} ({proj_start} to {proj_end})",
                    "target_member_id": mid,
                    "target_member_name": m.display_name,
                    "projected_start": proj_start,
                    "projected_end": proj_end,
                })
            # Sort by earliest projected end
            member_options.sort(key=lambda x: x["projected_end"] or "9999")
            options.extend(member_options)

            # Determine recommendation
            if issue == "no_owner":
                recommendation = "reassign"
                rec_id = member_options[0]["target_member_id"] if member_options else None
                rec_name = member_options[0]["target_member_name"] if member_options else None
            elif issue == "owner_not_in_scope":
                # Recommend reassigning to earliest-finishing in-scope member
                recommendation = "reassign"
                rec_id = member_options[0]["target_member_id"] if member_options else None
                rec_name = member_options[0]["target_member_name"] if member_options else None
            else:  # capacity_tight
                recommendation = "keep"
                rec_id = current_owner_id
                rec_name = current_owner.display_name if current_owner else None

            _t_overrides = t.field_overrides or {}
            conflicts.append({
                "task_id": t.id,
                "task_name": t.name,
                "effort_hours": total_effort,
                "current_owner_id": current_owner_id,
                "current_owner_name": current_owner.display_name if current_owner else None,
                "issue": issue,
                "recommendation": recommendation,
                "recommended_member_id": rec_id,
                "recommended_member_name": rec_name,
                "original_start": _t_overrides.get("_original_start") or t.scheduled_start_date,
                "original_end": _t_overrides.get("_original_end") or t.scheduled_end_date,
                "options": options,
            })

        return conflicts

    def prepare_and_build(
        self,
        session: "Session",
        project_id: int = None,
        member_ids: list = None,
        task_ids: list = None,
        schedule_start_date: str = None,
        ownership_resolutions: dict = None,
    ) -> Tuple[NormalizedSourceBundle, list, list]:
        """Pre-process (ensure assignments, compute effort overrides) then build bundle.

        Returns (bundle, overscheduled_tasks, log).

        Raises ValueError with a JSON-serializable dict if parent/summary task
        dependencies are detected (these block scheduling).

        Args:
            task_ids: Optional list of task IDs to include. If None, all non-cancelled tasks.
            schedule_start_date: Optional start date override (YYYY-MM-DD). Tasks will use
                this as their start date instead of their own.
            ownership_resolutions: Dict of {task_id: {"action": "keep"|"reassign",
                "target_member_id": int}} from the conflict resolution popup.
                If None, out-of-scope owners are skipped (not silently reassigned).
        """
        from sqlalchemy import func as sa_func
        from services.persistence.models import Assignment, DayAllocation, Member, Task

        int_project_id = int(project_id) if project_id else None
        int_task_ids = [int(t) for t in task_ids] if task_ids else None
        if member_ids:
            int_member_ids = [int(m) for m in member_ids]
        elif int_project_id:
            # Scope to project members — never auto-assign to members outside the project
            from services.persistence.models import ProjectMember
            pm_rows = session.query(ProjectMember).filter_by(project_id=int_project_id).all()
            if pm_rows:
                int_member_ids = [pm.member_id for pm in pm_rows]
            else:
                # Fallback: all active members if no ProjectMember entries exist
                int_member_ids = [m.id for m in session.query(Member).filter_by(is_active=True).all()]
        else:
            int_member_ids = [m.id for m in session.query(Member).filter_by(is_active=True).all()]

        overscheduled_tasks = []
        log = []  # debug log for the run

        # ── Step 1: Idempotency cleanup FIRST ────────────────────────────
        # Delete engine + unpinned manual allocations so subsequent steps
        # see the true available capacity. Only pinned allocations survive.
        task_ids_in_scope = set()
        task_query_scope = session.query(Task).filter(Task.status.notin_(["cancelled", "completed"]))
        if int_project_id:
            task_query_scope = task_query_scope.filter_by(project_id=int_project_id)
        if int_task_ids:
            task_query_scope = task_query_scope.filter(Task.id.in_(int_task_ids))
        for t in task_query_scope.all():
            task_ids_in_scope.add(t.id)
        if task_ids_in_scope:
            stale = session.query(DayAllocation).filter(
                DayAllocation.task_id.in_(task_ids_in_scope),
            ).all()
            cleared = 0
            int_member_id_set_cleanup = set(int_member_ids)
            for da in stale:
                # Always delete allocations for members NOT in scope
                # For in-scope members, only delete unpinned
                if da.member_id not in int_member_id_set_cleanup:
                    session.delete(da)
                    cleared += 1
                elif not da.pinned:
                    session.delete(da)
                    cleared += 1
            session.flush()
            log.append(f"Cleanup: cleared {cleared} stale allocations ({len(stale) - cleared} pinned kept)")

        # ── Step 1b: Save original dates (for Reset button) ────────────────
        # Save original import dates on first encounter. These are used by
        # the explicit "Reset to Import" endpoint, NOT for automatic resetting.
        # We do NOT reset dates here — the extension only grows windows, so
        # re-running is idempotent without resetting. Resetting caused second-
        # run failures because it compressed windows back to tiny import sizes
        # while Wave 1 allocations had already consumed capacity differently.
        for t in task_query_scope.all():
            overrides = dict(t.field_overrides or {})
            changed = False
            if "_original_start" not in overrides and t.scheduled_start_date:
                overrides["_original_start"] = t.scheduled_start_date
                changed = True
            if "_original_end" not in overrides and t.scheduled_end_date:
                overrides["_original_end"] = t.scheduled_end_date
                changed = True
            if changed:
                t.field_overrides = overrides
            # Only apply schedule_start_date override if explicitly provided
            if schedule_start_date:
                t.scheduled_start_date = schedule_start_date
        session.flush()

        # ── Step 2: Pre-assignment + date extension ──────────────────────
        if int_member_ids:
            task_query = session.query(Task).filter(Task.status.notin_(["cancelled", "completed"]))
            if int_project_id:
                task_query = task_query.filter_by(project_id=int_project_id)
            if int_task_ids:
                task_query = task_query.filter(Task.id.in_(int_task_ids))
            all_tasks = task_query.all()

            parent_ids = {t.parent_id for t in all_tasks if t.parent_id}
            # Also check the full project for parent IDs (summary tasks may not
            # be in the current task_ids selection but still have deps).
            if int_project_id:
                all_project_tasks = session.query(Task).filter(
                    Task.status.notin_(["cancelled", "completed"]),
                    Task.project_id == int_project_id,
                ).all()
                parent_ids |= {t.parent_id for t in all_project_tasks if t.parent_id}

            # ── Step 2a: Detect dependencies involving parent/summary tasks ──
            # Parent/summary tasks are containers for reporting — their dates
            # span all children and must NOT be used as scheduling constraints.
            # Block scheduling if such dependencies exist.
            from services.persistence.models import TaskDependency as _TDCheck
            all_task_map_check = {t.id: t for t in all_tasks}
            if int_project_id:
                for t in all_project_tasks:
                    all_task_map_check[t.id] = t
            _scope_ids = set(all_task_map_check.keys())
            parent_task_deps = []
            for dep in session.query(_TDCheck).all():
                if dep.predecessor_id not in _scope_ids and dep.successor_id not in _scope_ids:
                    continue
                if dep.predecessor_id in parent_ids or dep.successor_id in parent_ids:
                    pred_t = all_task_map_check.get(dep.predecessor_id)
                    succ_t = all_task_map_check.get(dep.successor_id)
                    parent_task_deps.append({
                        "predecessor_id": dep.predecessor_id,
                        "predecessor_name": pred_t.name if pred_t else str(dep.predecessor_id),
                        "successor_id": dep.successor_id,
                        "successor_name": succ_t.name if succ_t else str(dep.successor_id),
                        "dependency_type": dep.dependency_type or "FS",
                        "is_predecessor_parent": dep.predecessor_id in parent_ids,
                        "is_successor_parent": dep.successor_id in parent_ids,
                    })
            if parent_task_deps:
                import json
                raise ValueError(json.dumps({
                    "code": "parent_task_dependencies",
                    "message": (
                        "Dependencies involving parent/summary tasks were detected. "
                        "Parent tasks are containers for reporting — their dates span all children "
                        "and cannot be used as scheduling constraints. Please move these dependencies "
                        "to leaf tasks or remove them before scheduling."
                    ),
                    "parent_task_dependencies": parent_task_deps,
                }))

            leaf_tasks = [t for t in all_tasks if t.id not in parent_ids]

            # Remaining effort (after cleanup, only pinned allocations remain)
            tasks_to_schedule = []
            for t in leaf_tasks:
                total_effort = (t.estimated_hours or 0.0) + (t.buffer_hours or 0.0)
                allocated = session.query(
                    sa_func.coalesce(sa_func.sum(DayAllocation.hours), 0.0)
                ).filter_by(task_id=t.id).scalar() or 0.0
                remaining = max(0.0, total_effort - allocated)

                if total_effort > 0 and allocated > total_effort:
                    overscheduled_tasks.append({
                        "id": t.id, "name": t.name,
                        "effort": total_effort, "allocated": float(allocated),
                    })
                if remaining <= 0:
                    log.append(f"Task '{t.name}': fully allocated ({allocated}h pinned), skip")
                    continue
                tasks_to_schedule.append((t, remaining))
                log.append(f"Task '{t.name}': {remaining}h remaining of {total_effort}h total")

            # Create placeholder assignments for unassigned tasks
            parent_member_map = {}
            for t in all_tasks:
                assigns = session.query(Assignment).filter_by(task_id=t.id).all()
                if assigns:
                    parent_member_map[t.id] = assigns[0].member_id

            # Seed member_effort with cross-project allocations so auto-assignment
            # picks the TRULY least loaded member, not just least in-project effort.
            member_effort: Dict[int, float] = {}
            for mid in int_member_ids:
                xproj_hours = session.query(
                    sa_func.coalesce(sa_func.sum(DayAllocation.hours), 0.0)
                ).filter(
                    DayAllocation.member_id == mid,
                    ~DayAllocation.task_id.in_(task_ids_in_scope) if task_ids_in_scope else sa_func.literal(True),
                ).scalar() or 0.0
                member_effort[mid] = float(xproj_hours)
            for t in leaf_tasks:
                a = session.query(Assignment).filter_by(task_id=t.id).first()
                if a and a.member_id in member_effort:
                    member_effort[a.member_id] += (t.estimated_hours or 0.0) + (t.buffer_hours or 0.0)

            int_member_id_set = set(int_member_ids)
            for t, remaining in tasks_to_schedule:
                has_assign = session.query(Assignment).filter_by(task_id=t.id).first()
                if has_assign is not None:
                    if has_assign.member_id in int_member_id_set:
                        m = session.query(Member).filter_by(id=has_assign.member_id).first()
                        log.append(f"Task '{t.name}': assigned to {m.display_name if m else '?'}")
                        continue
                    # Assignment points to a member NOT in scope.
                    # Check if user provided a resolution from the conflict popup.
                    _resolutions = ownership_resolutions or {}
                    resolution = _resolutions.get(str(t.id)) or _resolutions.get(t.id)
                    if resolution is None:
                        # No resolution — keep the original owner by temporarily
                        # adding them to the member set so the engine can schedule.
                        int_member_id_set.add(has_assign.member_id)
                        m = session.query(Member).filter_by(id=has_assign.member_id).first()
                        log.append(f"Task '{t.name}': keeping owner {m.display_name if m else '?'} (not in scope, no resolution)")
                        continue
                    elif resolution.get("action") == "keep":
                        int_member_id_set.add(has_assign.member_id)
                        m = session.query(Member).filter_by(id=has_assign.member_id).first()
                        log.append(f"Task '{t.name}': keeping owner {m.display_name if m else '?'} (user chose to keep)")
                        continue
                    elif resolution.get("action") == "reassign":
                        new_mid = int(resolution["target_member_id"])
                        old_mid = has_assign.member_id
                        has_assign.member_id = new_mid
                        member_effort[new_mid] += remaining
                        parent_member_map[t.id] = new_mid
                        session.flush()
                        old_m = session.query(Member).filter_by(id=old_mid).first()
                        new_m = session.query(Member).filter_by(id=new_mid).first()
                        log.append(f"Task '{t.name}': reassigned from {old_m.display_name if old_m else '?'} to {new_m.display_name if new_m else '?'} (user approved)")
                        continue
                if not t.scheduled_start_date or not t.scheduled_end_date:
                    log.append(f"Task '{t.name}': no dates, skipping assignment")
                    continue

                # Check if user chose a specific member from the conflict popup
                _resolutions = ownership_resolutions or {}
                resolution = _resolutions.get(str(t.id)) or _resolutions.get(t.id)
                if resolution and resolution.get("action") == "reassign" and resolution.get("target_member_id"):
                    mid = int(resolution["target_member_id"])
                elif t.parent_id and t.parent_id in parent_member_map:
                    mid = parent_member_map[t.parent_id]
                    if mid not in member_effort:
                        mid = min(int_member_ids, key=lambda m: member_effort[m])
                else:
                    mid = min(int_member_ids, key=lambda m: member_effort[m])

                session.add(Assignment(
                    task_id=t.id, member_id=mid, allocated_hours=0.0,
                    start_date=t.scheduled_start_date, end_date=t.scheduled_end_date,
                    field_overrides={"source": "auto"},
                ))
                member_effort[mid] += remaining
                parent_member_map[t.id] = mid
                m = session.query(Member).filter_by(id=mid).first()
                log.append(f"Task '{t.name}': auto-assigned to {m.display_name if m else '?'}")

            # Extend task end dates if remaining effort doesn't fit.
            # Process in dependency order so predecessor extensions cascade correctly.
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            from services.persistence.models import TimeOff, TaskDependency

            # Build dependency graph for topological ordering (all dep types)
            all_task_map = {t.id: t for t in all_tasks}
            remaining_map = {t.id: r for t, r in tasks_to_schedule}
            deps = session.query(TaskDependency).all()
            dep_preds = {}   # successor_id -> [(predecessor_id, dep_type)]
            for dep in deps:
                dep_type = dep.dependency_type or "FS"
                dep_preds.setdefault(dep.successor_id, []).append((dep.predecessor_id, dep_type))
            # Flat predecessor list for topological ordering
            flat_preds = {}  # successor_id -> [predecessor_id]
            for succ_id, entries in dep_preds.items():
                flat_preds[succ_id] = [pred_id for pred_id, _ in entries]

            # projected_start/end track computed dates for each task (cascading through deps)
            projected_end = {}    # task_id -> window end date (for cascade extension)
            projected_start = {}  # task_id -> projected start date string
            actual_effort_end = {}  # task_id -> when effort actually finishes (for pull-forward)
            for t in all_tasks:
                projected_end[t.id] = t.scheduled_end_date
                projected_start[t.id] = t.scheduled_start_date
                actual_effort_end[t.id] = t.scheduled_end_date
            # When running for specific task_ids (wave mode), predecessors from
            # earlier waves are NOT in all_tasks. Initialize their projected dates
            # from the DB so dependency adjustments work correctly.
            if int_task_ids:
                predecessor_ids_all = set()
                for entries in dep_preds.values():
                    for pred_id, _ in entries:
                        predecessor_ids_all.add(pred_id)
                missing_pred_ids = predecessor_ids_all - set(all_task_map.keys())
                if missing_pred_ids:
                    for pred_task in session.query(Task).filter(Task.id.in_(missing_pred_ids)).all():
                        projected_end[pred_task.id] = pred_task.scheduled_end_date
                        projected_start[pred_task.id] = pred_task.scheduled_start_date
                        actual_effort_end[pred_task.id] = pred_task.scheduled_end_date
                        all_task_map[pred_task.id] = pred_task

            # Sort tasks_to_schedule by dependency order (predecessors first)
            # Simple approach: iterate until all are processed
            scheduled_ids = set()
            ordered_schedule = []
            remaining_tasks = list(tasks_to_schedule)
            max_iterations = len(remaining_tasks) + 1
            for _ in range(max_iterations):
                progress = False
                next_remaining = []
                for t, rem in remaining_tasks:
                    preds = flat_preds.get(t.id, [])
                    # Check if all predecessors are processed or not in schedule
                    if all(p in scheduled_ids or p not in remaining_map for p in preds):
                        ordered_schedule.append((t, rem))
                        scheduled_ids.add(t.id)
                        progress = True
                    else:
                        next_remaining.append((t, rem))
                remaining_tasks = next_remaining
                if not remaining_tasks:
                    break
                if not progress:
                    ordered_schedule.extend(remaining_tasks)
                    break

            for t, remaining in ordered_schedule:
                if not t.scheduled_start_date or not t.scheduled_end_date:
                    continue
                assigns = session.query(Assignment).filter_by(task_id=t.id).all()
                if not assigns:
                    continue
                member = session.query(Member).filter_by(id=assigns[0].member_id).first()
                if not member:
                    continue
                daily_cap = member.weekly_capacity_hours / max(len(member.working_days or []), 1)
                wd_set = set(member.working_days or [])
                try:
                    # Use _original_start for unpinned tasks so the extension
                    # matches what the bundle gives the engine (earliest possible start).
                    # When schedule_start_date is provided, use the later of
                    # _original_start and schedule_start_date so the extension
                    # window matches what build() gives the engine.
                    _t_overrides = t.field_overrides or {}
                    _t_has_pinned = session.query(DayAllocation).filter_by(
                        task_id=t.id, pinned=True).first() is not None
                    if _t_has_pinned:
                        s_date = date.fromisoformat(t.scheduled_start_date)
                    else:
                        s_date = date.fromisoformat(
                            _t_overrides.get("_original_start") or t.scheduled_start_date)
                    # schedule_start_date override: the bundle will use this as
                    # start_date, so the extension must also use it to ensure
                    # the end date covers enough capacity from the overridden start.
                    if schedule_start_date:
                        _override_start = date.fromisoformat(schedule_start_date)
                        if _override_start > s_date:
                            s_date = _override_start
                    e_date = date.fromisoformat(t.scheduled_end_date)
                    # Ensure end is at least start (override may push start past original end)
                    if e_date < s_date:
                        e_date = s_date
                except (ValueError, TypeError):
                    continue

                # Account for ALL dependency types using projected dates (cascading)
                # Skip deps where predecessor is a parent/summary task — their
                # inflated date spans would incorrectly extend leaf windows.
                for pred_id, dep_type in dep_preds.get(t.id, []):
                    if pred_id in parent_ids:
                        continue
                    pred_t = all_task_map.get(pred_id)
                    pred_proj_end = projected_end.get(pred_id)
                    pred_proj_start = projected_start.get(pred_id)
                    try:
                        if dep_type == "FS":
                            if pred_proj_end:
                                dep_start = date.fromisoformat(pred_proj_end) + timedelta(days=1)
                                if dep_start > s_date:
                                    s_date = dep_start
                                    log.append(f"Task '{t.name}': FS dep on '{pred_t.name if pred_t else pred_id}' pushes start to {s_date.isoformat()}")
                        elif dep_type == "SS":
                            if pred_proj_start:
                                dep_start = date.fromisoformat(pred_proj_start)
                                if dep_start > s_date:
                                    s_date = dep_start
                                    log.append(f"Task '{t.name}': SS dep on '{pred_t.name if pred_t else pred_id}' pushes start to {s_date.isoformat()}")
                        elif dep_type == "FF":
                            if pred_proj_end:
                                dep_end = date.fromisoformat(pred_proj_end)
                                if dep_end > e_date:
                                    e_date = dep_end
                                    log.append(f"Task '{t.name}': FF dep on '{pred_t.name if pred_t else pred_id}' extends end to {e_date.isoformat()}")
                        elif dep_type == "SF":
                            if pred_proj_start:
                                dep_end = date.fromisoformat(pred_proj_start)
                                if dep_end > e_date:
                                    e_date = dep_end
                                    log.append(f"Task '{t.name}': SF dep on '{pred_t.name if pred_t else pred_id}' extends end to {e_date.isoformat()}")
                    except (ValueError, TypeError):
                        pass

                # Persist dependency-adjusted dates to the task before capacity check.
                # This ensures FF/SF end extensions and SS/FS start pushes are saved
                # even if the capacity check doesn't trigger further extension.
                if s_date.isoformat() != t.scheduled_start_date:
                    t.scheduled_start_date = s_date.isoformat()
                    for a in assigns:
                        a.start_date = s_date.isoformat()
                if e_date.isoformat() != t.scheduled_end_date:
                    old_end = t.scheduled_end_date
                    t.scheduled_end_date = e_date.isoformat()
                    for a in assigns:
                        a.end_date = e_date.isoformat()
                    log.append(f"Task '{t.name}': dep-adjusted end {old_end} -> {e_date.isoformat()}")

                # Load cross-project allocations for this member
                from sqlalchemy import func as sa_hours_func
                member_allocs_by_date = {}
                existing_allocs = session.query(
                    DayAllocation.date,
                    sa_hours_func.sum(DayAllocation.hours),
                ).filter_by(member_id=member.id).group_by(DayAllocation.date).all()
                for row_date, row_hours in existing_allocs:
                    member_allocs_by_date[row_date] = float(row_hours or 0)

                time_off_dates = set()
                for to in session.query(TimeOff).filter_by(member_id=member.id).all():
                    try:
                        to_s = date.fromisoformat(to.start_date)
                        to_e = date.fromisoformat(to.end_date)
                    except (ValueError, TypeError):
                        continue
                    cur = to_s
                    while cur <= to_e:
                        time_off_dates.add(cur.isoformat())
                        cur += timedelta(days=1)

                # Count available capacity in current window (using effective start)
                available_hours = 0.0
                d = s_date
                while d <= e_date:
                    ds = d.isoformat()
                    if day_names[d.weekday()] in wd_set and ds not in time_off_dates:
                        committed = member_allocs_by_date.get(ds, 0.0)
                        avail = max(0.0, daily_cap - committed)
                        available_hours += avail
                    d += timedelta(days=1)

                if available_hours < remaining:
                    # Extend from effective start until enough capacity found
                    d = s_date
                    accumulated = 0.0
                    while accumulated < remaining:
                        ds = d.isoformat()
                        if day_names[d.weekday()] in wd_set and ds not in time_off_dates:
                            committed = member_allocs_by_date.get(ds, 0.0)
                            avail = max(0.0, daily_cap - committed)
                            accumulated += avail
                        if accumulated < remaining:
                            d += timedelta(days=1)
                    old_end = t.scheduled_end_date
                    t.scheduled_end_date = d.isoformat()
                    for a in assigns:
                        a.end_date = d.isoformat()
                    projected_end[t.id] = d.isoformat()
                    actual_effort_end[t.id] = d.isoformat()
                    # Update start if dependency pushed it forward
                    if s_date.isoformat() != t.scheduled_start_date:
                        t.scheduled_start_date = s_date.isoformat()
                        for a in assigns:
                            a.start_date = s_date.isoformat()
                    projected_start[t.id] = s_date.isoformat()
                    log.append(f"Task '{t.name}': extended end {old_end} -> {d.isoformat()} ({remaining}h needs {available_hours}h avail in window starting {s_date.isoformat()})")
                else:
                    # Even without extension, update projected_end to reflect effective window
                    # Find the actual end: walk from s_date accumulating capacity
                    d = s_date
                    accumulated = 0.0
                    while accumulated < remaining:
                        ds = d.isoformat()
                        if day_names[d.weekday()] in wd_set and ds not in time_off_dates:
                            committed = member_allocs_by_date.get(ds, 0.0)
                            avail = max(0.0, daily_cap - committed)
                            accumulated += avail
                        if accumulated < remaining:
                            d += timedelta(days=1)
                    projected_end[t.id] = d.isoformat()
                    actual_effort_end[t.id] = d.isoformat()
                    # Update start if dependency pushed it forward
                    if s_date.isoformat() != t.scheduled_start_date:
                        t.scheduled_start_date = s_date.isoformat()
                        for a in assigns:
                            a.start_date = s_date.isoformat()
                    projected_start[t.id] = s_date.isoformat()

            # ── Second pass: extend ALL tasks per member to fit total effort ───
            # The first pass extends each task independently. Two tasks on the
            # same member in overlapping windows both assume full capacity.
            # We can't predict the engine's processing order, so we extend ALL
            # tasks to a common end date that guarantees enough working days
            # for the member's total effort — regardless of which task runs first.
            from collections import defaultdict as _defaultdict
            member_tasks_agg = _defaultdict(list)  # member_id -> [(task, remaining)]
            for t, remaining in ordered_schedule:
                assigns_list = session.query(Assignment).filter_by(task_id=t.id).all()
                if assigns_list:
                    member_tasks_agg[assigns_list[0].member_id].append((t, remaining))

            for mid, task_list in member_tasks_agg.items():
                if len(task_list) <= 1:
                    continue
                member = session.query(Member).filter_by(id=mid).first()
                if not member:
                    continue
                daily_cap_m = member.weekly_capacity_hours / max(len(member.working_days or []), 1)
                wd_set_m = set(member.working_days or [])
                total_effort = sum(r for _, r in task_list)

                # Find earliest start across all tasks
                all_starts = [date.fromisoformat(t.scheduled_start_date)
                              for t, _ in task_list if t.scheduled_start_date]
                if not all_starts:
                    continue
                earliest = min(all_starts)

                # Load cross-project + time-off deductions for this member
                # so we use ACTUAL available capacity, not raw daily_cap
                from sqlalchemy import func as _sa_func2
                _xproj_by_date = {}
                _xproj_allocs = session.query(
                    DayAllocation.date, _sa_func2.sum(DayAllocation.hours),
                ).filter_by(member_id=mid).filter(
                    ~DayAllocation.task_id.in_(task_ids_in_scope)
                ).group_by(DayAllocation.date).all()
                for _d_str, _hrs in _xproj_allocs:
                    _xproj_by_date[_d_str] = float(_hrs or 0)

                _time_off_set = set()
                for _to in session.query(TimeOff).filter_by(member_id=mid).all():
                    try:
                        _to_s = date.fromisoformat(_to.start_date)
                        _to_e = date.fromisoformat(_to.end_date)
                    except (ValueError, TypeError):
                        continue
                    _cur = _to_s
                    while _cur <= _to_e:
                        _time_off_set.add(_cur.isoformat())
                        _cur += timedelta(days=1)

                # For each task, ensure its window (from ITS start date) has enough
                # room for the TOTAL member effort from that point. This guarantees
                # the engine can place the task even if all other tasks on the same
                # member are processed first and consume capacity.
                # Find the latest start across all tasks — the worst case is when
                # the engine processes the latest-starting task last, after all
                # other tasks have consumed capacity.
                latest_start = max(all_starts)

                for t_ext, rem in task_list:
                    if not t_ext.scheduled_start_date or not t_ext.scheduled_end_date:
                        continue
                    # Extend from the LATEST member start. This ensures even the
                    # latest-starting task has room for the full member total, since
                    # earlier tasks may consume all capacity in earlier days.
                    t_start = latest_start
                    effort_from_here = total_effort
                    accumulated = 0.0
                    d = t_start
                    while accumulated < effort_from_here:
                        ds = d.isoformat()
                        if day_names[d.weekday()] in wd_set_m and ds not in _time_off_set:
                            xproj = _xproj_by_date.get(ds, 0.0)
                            avail = max(0.0, daily_cap_m - xproj)
                            accumulated += avail
                        if accumulated < effort_from_here:
                            d += timedelta(days=1)
                    needed_end = d

                    if t_ext.scheduled_end_date < needed_end.isoformat():
                        old_end = t_ext.scheduled_end_date
                        t_ext.scheduled_end_date = needed_end.isoformat()
                        for a in session.query(Assignment).filter_by(task_id=t_ext.id).all():
                            a.end_date = needed_end.isoformat()
                        projected_end[t_ext.id] = needed_end.isoformat()
                        # actual_effort_end is NOT updated — it stays at the real
                        # projected finish, not the window boundary.
                        log.append(f"Task '{t_ext.name}': sibling competition extended end {old_end} -> {needed_end.isoformat()} (member total {total_effort}h from {t_start.isoformat()})")

            # ── Third pass: cascade sibling extensions through dependencies ────
            # Sibling extensions on predecessors push successor starts later (FS
            # deps). Re-walk successor tasks and extend their windows if the
            # dep-adjusted start + total member effort doesn't fit.
            for t, remaining in ordered_schedule:
                if not t.scheduled_start_date or not t.scheduled_end_date:
                    continue
                # Re-check dependency-adjusted start using updated projected_end
                s_date_adj = date.fromisoformat(t.scheduled_start_date)
                for pred_id, dep_type in dep_preds.get(t.id, []):
                    if pred_id in parent_ids:
                        continue
                    pred_proj_end = projected_end.get(pred_id)
                    if not pred_proj_end:
                        continue
                    try:
                        if dep_type in (None, "FS", ""):
                            dep_start = date.fromisoformat(pred_proj_end) + timedelta(days=1)
                            if dep_start > s_date_adj:
                                s_date_adj = dep_start
                        elif dep_type == "SS":
                            pred_proj_s = projected_start.get(pred_id)
                            if pred_proj_s:
                                dep_start = date.fromisoformat(pred_proj_s)
                                if dep_start > s_date_adj:
                                    s_date_adj = dep_start
                    except (ValueError, TypeError):
                        pass

                if s_date_adj.isoformat() != t.scheduled_start_date:
                    t.scheduled_start_date = s_date_adj.isoformat()
                    for a in session.query(Assignment).filter_by(task_id=t.id).all():
                        a.start_date = s_date_adj.isoformat()
                    projected_start[t.id] = s_date_adj.isoformat()

                    # Re-extend end date if dep-adjusted start pushed window too tight
                    assigns_ext = session.query(Assignment).filter_by(task_id=t.id).all()
                    if assigns_ext:
                        member_ext = session.query(Member).filter_by(id=assigns_ext[0].member_id).first()
                        if member_ext:
                            daily_cap_ext = member_ext.weekly_capacity_hours / max(len(member_ext.working_days or []), 1)
                            wd_set_ext = set(member_ext.working_days or [])
                            avail_ext = 0.0
                            d = s_date_adj
                            e = date.fromisoformat(t.scheduled_end_date)
                            while d <= e:
                                if day_names[d.weekday()] in wd_set_ext:
                                    avail_ext += daily_cap_ext
                                d += timedelta(days=1)
                            if avail_ext < remaining:
                                d = e + timedelta(days=1)
                                while avail_ext < remaining:
                                    if day_names[d.weekday()] in wd_set_ext:
                                        avail_ext += daily_cap_ext
                                    if avail_ext < remaining:
                                        d += timedelta(days=1)
                                old_end = t.scheduled_end_date
                                t.scheduled_end_date = d.isoformat()
                                for a in session.query(Assignment).filter_by(task_id=t.id).all():
                                    a.end_date = d.isoformat()
                                projected_end[t.id] = d.isoformat()
                                log.append(f"Task '{t.name}': dep cascade extended end {old_end} -> {d.isoformat()} (start pushed to {s_date_adj.isoformat()})")

            session.commit()

        # Compute remaining effort overrides (without mutating the DB)
        effort_overrides: Dict[int, float] = {}
        task_query2 = session.query(Task).filter(Task.status.notin_(["cancelled", "completed"]))
        if int_project_id:
            task_query2 = task_query2.filter_by(project_id=int_project_id)
        for t in task_query2.all():
            total = (t.estimated_hours or 0.0) + (t.buffer_hours or 0.0)
            allocated = session.query(
                sa_func.coalesce(sa_func.sum(DayAllocation.hours), 0.0)
            ).filter_by(task_id=t.id).scalar() or 0.0
            remaining = max(0.0, total - float(allocated))
            if remaining < total and remaining > 0:
                effort_overrides[t.id] = remaining
            elif remaining <= 0 and total > 0:
                effort_overrides[t.id] = 0.0

        bundle = self.build(
            session,
            project_id=int_project_id,
            member_ids=int_member_ids,
            effort_overrides=effort_overrides,
            task_ids=int_task_ids,
            schedule_start_date=schedule_start_date,
        )
        return bundle, overscheduled_tasks, log
