"""Maps NormalizedSourceBundle records into the Float SQLite database.

This is called after a successful import sync. It upserts Projects, Tasks,
Dependencies, and Assignments using external_id as the stable key.

Members are NOT auto-created here — use POST /api/float/members/sync-from-asana
to import members from the workspace. Unmatched resources are reported in counts.

It NEVER overwrites field_overrides — manual edits always take priority.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.persistence import get_db_session
from services.persistence.models import Assignment, Project, Task, TaskDependency

# Project colors (cycles)
_PROJECT_COLORS = [
    "#2196F3", "#4CAF50", "#FF9800", "#9C27B0",
    "#F44336", "#00BCD4", "#E91E63", "#FF5722",
]


def _pick_color(items: list, idx: int) -> str:
    return items[idx % len(items)]


class ImportToFloatMapper:
    def sync_from_bundle(self, bundle: Any, completed_ext_ids: set = None,
                         resource_mapping: dict = None) -> Dict[str, Any]:
        """Upsert all entities from a NormalizedSourceBundle into SQLite.

        Returns counts of upserted rows per entity type plus unmatched_resources.
        Members are NEVER auto-created — only matched by external_id.
        completed_ext_ids: set of external_task_ids that should be marked as 'completed'.
        resource_mapping: dict of {resource_external_id: member_id} from the preview
            mapping UI. Overrides external_id matching when provided.
        """
        completed_ext_ids = completed_ext_ids or set()
        counts: Dict[str, Any] = {
            "projects": 0,
            "tasks": 0,
            "dependencies": 0,
            "dependencies_updated": 0,
            "assignments": 0,
            "projects_updated": 0,
            "tasks_updated": 0,
            "unmatched_resources": [],
            "project_ext_id": None,  # first project's external_id (for Asana link)
            "project_id": None,      # DB integer id of first upserted project
            "start_date": None,      # earliest task start date
            "end_date": None,        # latest task end date
        }

        resource_mapping = resource_mapping or {}

        with get_db_session() as session:
            # ── Members — match by external_id or use explicit mapping ──
            from services.persistence.models import Member
            member_ext_to_id: Dict[str, int] = {}
            for resource in bundle.resources:
                ext_id = resource.external_resource_id
                # Explicit mapping from preview UI takes priority
                if ext_id in resource_mapping:
                    mapped_mid = resource_mapping[ext_id]
                    if mapped_mid is not None:
                        member_ext_to_id[ext_id] = int(mapped_mid)
                        # Also update the Member's external_id so future imports
                        # auto-match without needing the mapping again
                        member = session.query(Member).filter_by(id=int(mapped_mid)).first()
                        if member and member.external_id != ext_id:
                            # Store MS Project resource ID as a secondary mapping
                            m_overrides = dict(member.field_overrides or {}) if hasattr(member, 'field_overrides') else {}
                            # Don't overwrite Asana external_id — just record the mapping
                            pass
                    continue
                # Fallback: match by external_id
                existing = session.query(Member).filter_by(external_id=ext_id).first()
                if existing is not None:
                    member_ext_to_id[ext_id] = existing.id
                else:
                    counts["unmatched_resources"].append(ext_id)

            # ── Projects ───────────────────────────────────────────────
            # Build a lookup for project names from bundle mappings
            project_name_map: Dict[str, str] = {}
            for pm in getattr(bundle, "project_mappings", []) or []:
                if pm.external_id and pm.display_name:
                    project_name_map[pm.external_id] = pm.display_name

            # Derive project set from tasks
            project_ext_ids = {t.project_external_id for t in bundle.tasks if t.project_external_id}
            project_ext_to_id: Dict[str, int] = {}
            for idx, p_ext_id in enumerate(sorted(project_ext_ids)):
                proj_name = project_name_map.get(p_ext_id, p_ext_id)
                existing = session.query(Project).filter_by(external_id=p_ext_id).first()
                if existing is None:
                    project = Project(
                        external_id=p_ext_id,
                        name=proj_name,
                        color=_pick_color(_PROJECT_COLORS, idx),
                        status="active",
                    )
                    session.add(project)
                    session.flush()
                    project_ext_to_id[p_ext_id] = project.id
                    counts["projects"] += 1
                else:
                    # Update name if it was a hash placeholder
                    if existing.name == p_ext_id and proj_name != p_ext_id:
                        existing.name = proj_name
                    project_ext_to_id[p_ext_id] = existing.id
                    counts["projects_updated"] += 1
                # Record the first project ext_id and DB id
                if counts["project_ext_id"] is None:
                    counts["project_ext_id"] = p_ext_id
                    counts["project_id"] = project_ext_to_id[p_ext_id]

            # ── Tasks ──────────────────────────────────────────────────
            task_ext_to_id: Dict[str, int] = {}
            for task_rec in bundle.tasks:
                ext_id = task_rec.external_task_id
                p_id = project_ext_to_id.get(task_rec.project_external_id)
                if p_id is None:
                    continue
                existing = session.query(Task).filter_by(external_id=ext_id).first()
                if existing is None:
                    # Save imported dates as originals so the engine can reset to them
                    overrides = {}
                    if task_rec.start_date:
                        overrides["_original_start"] = task_rec.start_date
                    if task_rec.due_date:
                        overrides["_original_end"] = task_rec.due_date
                    task_status = "completed" if ext_id in completed_ext_ids else "active"
                    task = Task(
                        external_id=ext_id,
                        project_id=p_id,
                        name=task_rec.name,
                        status=task_status,
                        scheduled_start_date=task_rec.start_date,
                        scheduled_end_date=task_rec.due_date,
                        estimated_hours=task_rec.effort_hours,
                        field_overrides=overrides,
                    )
                    session.add(task)
                    session.flush()
                    task_ext_to_id[ext_id] = task.id
                    counts["tasks"] += 1
                else:
                    # Update base fields only (never touch manual field_overrides)
                    existing.name = task_rec.name
                    existing.project_id = p_id
                    # Sync completion status from source
                    if ext_id in completed_ext_ids:
                        existing.status = "completed"
                    elif existing.status == "completed" and ext_id not in completed_ext_ids:
                        existing.status = "active"  # un-completed in source
                    overrides = dict(existing.field_overrides or {})
                    if not overrides.get("scheduled_start_date"):
                        existing.scheduled_start_date = task_rec.start_date
                    if not overrides.get("scheduled_end_date"):
                        existing.scheduled_end_date = task_rec.due_date
                    if task_rec.effort_hours is not None:
                        existing.estimated_hours = task_rec.effort_hours
                    # Save/update original dates from import
                    if task_rec.start_date and "_original_start" not in overrides:
                        overrides["_original_start"] = task_rec.start_date
                    if task_rec.due_date and "_original_end" not in overrides:
                        overrides["_original_end"] = task_rec.due_date
                    existing.field_overrides = overrides
                    task_ext_to_id[ext_id] = existing.id
                    counts["tasks_updated"] += 1

            # ── Compute project date range ────────────────────────────
            all_starts = [t.start_date for t in bundle.tasks if t.start_date]
            all_ends = [t.due_date for t in bundle.tasks if t.due_date]
            if all_starts:
                counts["start_date"] = min(all_starts)
            if all_ends:
                counts["end_date"] = max(all_ends)
            # Also update project.start_date / end_date
            if counts["project_id"] is not None:
                proj = session.query(Project).filter_by(id=counts["project_id"]).first()
                if proj:
                    if counts["start_date"] and not proj.start_date:
                        proj.start_date = counts["start_date"]
                    if counts["end_date"] and not proj.end_date:
                        proj.end_date = counts["end_date"]

            # ── Parent-child hierarchy ─────────────────────────────────
            for task_rec in bundle.tasks:
                parent_ext_id = getattr(task_rec, "parent_task_id", None)
                if not parent_ext_id:
                    continue
                child = session.query(Task).filter_by(external_id=task_rec.external_task_id).first()
                parent = session.query(Task).filter_by(external_id=parent_ext_id).first()
                if child and parent:
                    child.parent_id = parent.id
                    child.hierarchy_depth = getattr(task_rec, "hierarchy_depth", 0) or 0

            # ── Split multi-assignee tasks ────────────────────────────
            # If a task has N assignees in the bundle, split it into N
            # separate tasks with equal effort. Each split inherits deps,
            # dates, and parent. The original task keeps assignee[0].
            from collections import defaultdict as _defaultdict
            assigns_by_task_ext = _defaultdict(list)
            for ar in bundle.resource_assignments:
                assigns_by_task_ext[ar.task_external_id].append(ar)

            split_map = {}  # original_ext_id → [all ext_ids including original]
            split_task_to_resource = {}  # ext_id → resource_external_id (for 1:1 assignment)

            for task_ext_id, assign_recs in assigns_by_task_ext.items():
                if len(assign_recs) <= 1:
                    # Single assignee — record for assignment loop
                    if assign_recs:
                        split_task_to_resource[task_ext_id] = assign_recs[0].resource_external_id
                    continue

                original_db_id = task_ext_to_id.get(task_ext_id)
                if original_db_id is None:
                    continue
                original = session.query(Task).filter_by(id=original_db_id).first()
                if original is None:
                    continue

                # Skip parent/summary tasks (no effort to split)
                if original.estimated_hours is None or original.estimated_hours <= 0:
                    continue

                n = len(assign_recs)
                total_effort = original.estimated_hours or 0.0
                total_buffer = original.buffer_hours or 0.0
                base_name = original.name
                split_ext_ids = []

                for i, ar in enumerate(assign_recs):
                    mid = member_ext_to_id.get(ar.resource_external_id)
                    member = session.query(Member).filter_by(id=mid).first() if mid else None
                    label = member.display_name if member else ar.resource_external_id

                    if i == 0:
                        # Keep original task, update effort and name
                        share = round(total_effort / n, 2)
                        buf_share = round(total_buffer / n, 2) if total_buffer else None
                        original.estimated_hours = share
                        original.buffer_hours = buf_share
                        original.name = f"{base_name} [{label}]"
                        split_ext_ids.append(task_ext_id)
                        split_task_to_resource[task_ext_id] = ar.resource_external_id
                    else:
                        # Last assignee gets remainder to avoid rounding loss
                        if i == n - 1:
                            already = round(total_effort / n, 2) * (n - 1)
                            share = round(total_effort - already, 2)
                            buf_already = round(total_buffer / n, 2) * (n - 1) if total_buffer else 0
                            buf_share = round(total_buffer - buf_already, 2) if total_buffer else None
                        else:
                            share = round(total_effort / n, 2)
                            buf_share = round(total_buffer / n, 2) if total_buffer else None

                        split_ext = f"{task_ext_id}__split_{i}"
                        overrides = dict(original.field_overrides or {})
                        overrides["_split_from"] = task_ext_id
                        if original.scheduled_start_date:
                            overrides["_original_start"] = original.scheduled_start_date
                        if original.scheduled_end_date:
                            overrides["_original_end"] = original.scheduled_end_date

                        split_task = Task(
                            external_id=split_ext,
                            project_id=original.project_id,
                            parent_id=original.parent_id,
                            hierarchy_depth=original.hierarchy_depth,
                            name=f"{base_name} [{label}]",
                            status=original.status,
                            scheduled_start_date=original.scheduled_start_date,
                            scheduled_end_date=original.scheduled_end_date,
                            estimated_hours=share,
                            buffer_hours=buf_share,
                            field_overrides=overrides,
                        )
                        session.add(split_task)
                        session.flush()
                        task_ext_to_id[split_ext] = split_task.id
                        split_ext_ids.append(split_ext)
                        split_task_to_resource[split_ext] = ar.resource_external_id
                        counts["tasks"] += 1

                split_map[task_ext_id] = split_ext_ids

            session.flush()

            # ── Task Dependencies (with split expansion) ──────────────
            for dep in bundle.dependencies:
                dep_type = getattr(dep, "dependency_type", None) or "FS"
                pred_ext = dep.predecessor_external_task_id
                succ_ext = dep.successor_external_task_id

                # Expand splits: if pred or succ was split, create deps for all
                pred_ext_ids = split_map.get(pred_ext, [pred_ext])
                succ_ext_ids = split_map.get(succ_ext, [succ_ext])

                for p_ext in pred_ext_ids:
                    for s_ext in succ_ext_ids:
                        pred_id = task_ext_to_id.get(p_ext)
                        succ_id = task_ext_to_id.get(s_ext)
                        if pred_id is None or succ_id is None:
                            continue
                        existing_dep = session.query(TaskDependency).filter_by(
                            predecessor_id=pred_id, successor_id=succ_id
                        ).first()
                        if existing_dep is None:
                            session.add(TaskDependency(
                                predecessor_id=pred_id,
                                successor_id=succ_id,
                                dependency_type=dep_type,
                            ))
                            counts["dependencies"] += 1
                        else:
                            counts["dependencies_updated"] += 1
                            # Update dep type if changed
                            new_dep_type = getattr(dep, "dependency_type", None)
                            if new_dep_type and existing_dep.dependency_type != new_dep_type:
                                existing_dep.dependency_type = new_dep_type

            session.flush()

            # ── Assignments (1:1 after splitting) ─────────────────────
            # For split tasks, each split has exactly one assignee via
            # split_task_to_resource. For non-split tasks, the original
            # bundle assignment records are used.
            # Build the set of (task_ext, resource_ext) pairs to create.
            assignment_pairs = []  # [(task_ext_id, resource_ext_id)]
            for task_ext_id, resource_ext_id in split_task_to_resource.items():
                assignment_pairs.append((task_ext_id, resource_ext_id))
            # Also include non-split single-assignee tasks from the bundle
            for ar in bundle.resource_assignments:
                if ar.task_external_id not in split_task_to_resource:
                    assignment_pairs.append((ar.task_external_id, ar.resource_external_id))

            for task_ext_id, resource_ext_id in assignment_pairs:
                task_id = task_ext_to_id.get(task_ext_id)
                member_id = member_ext_to_id.get(resource_ext_id)
                if task_id is None or member_id is None:
                    continue

                task = session.query(Task).filter_by(id=task_id).first()
                if task is None:
                    continue
                start = task.scheduled_start_date
                end = task.scheduled_end_date
                if not start or not end:
                    continue

                # Store assignee in task field_overrides so reset can restore
                t_overrides = dict(task.field_overrides or {})
                t_overrides["_import_assignee_member_id"] = member_id
                t_overrides["_import_assignee_external_id"] = resource_ext_id
                task.field_overrides = t_overrides

                existing_assign = session.query(Assignment).filter_by(
                    task_id=task_id, member_id=member_id
                ).first()
                if existing_assign is None:
                    overrides: Dict[str, Any] = {"source": "import", "allocation_percent": 100}
                    assignment = Assignment(
                        task_id=task_id,
                        member_id=member_id,
                        allocated_hours=0.0,
                        start_date=start,
                        end_date=end,
                        field_overrides=overrides,
                    )
                    session.add(assignment)
                    counts["assignments"] += 1

            # ── Completed task allocations (pinned, as-is) ────────────────
            # For completed tasks imported from project files (not Asana sync),
            # create pinned DayAllocation rows so they appear in the schedule
            # exactly as they happened — effort spread across working days.
            from datetime import date as date_cls, timedelta as td
            from services.persistence.models import DayAllocation
            day_names_list = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

            for ext_id in completed_ext_ids:
                task_id = task_ext_to_id.get(ext_id)
                if task_id is None:
                    continue
                task = session.query(Task).filter_by(id=task_id).first()
                if task is None or not task.estimated_hours or not task.scheduled_start_date or not task.scheduled_end_date:
                    continue

                # Find assignment for this task
                assign = session.query(Assignment).filter_by(task_id=task_id).first()
                if assign is None:
                    continue

                member = session.query(Member).filter_by(id=assign.member_id).first()
                if member is None:
                    continue

                wd_set = set(member.working_days or ["Sun", "Mon", "Tue", "Wed", "Thu"])
                try:
                    s = date_cls.fromisoformat(task.scheduled_start_date)
                    e = date_cls.fromisoformat(task.scheduled_end_date)
                except (ValueError, TypeError):
                    continue

                # Count working days in range
                working_days = []
                cur = s
                while cur <= e:
                    if day_names_list[cur.weekday()] in wd_set:
                        working_days.append(cur.isoformat())
                    cur += td(days=1)

                if not working_days:
                    continue

                hours_per_day = round(task.estimated_hours / len(working_days), 2)

                # Delete any existing allocations for this task (re-import safe)
                session.query(DayAllocation).filter_by(task_id=task_id).delete()
                session.flush()

                for day_str in working_days:
                    session.add(DayAllocation(
                        task_id=task_id,
                        member_id=assign.member_id,
                        date=day_str,
                        hours=hours_per_day,
                        source="import",
                        pinned=False,
                    ))

                # Update assignment with actual hours
                assign.allocated_hours = task.estimated_hours

            # Collect discovered member IDs for wizard pre-population
            counts["discovered_member_ids"] = list(member_ext_to_id.values())

            session.commit()

        return counts
