"""Writes planning engine allocation outputs back to SQLite.

Two writes happen per engine run:
1. DayAllocation rows (one per task/member/date) — the source of truth for the
   new calendar UI. Manual reassignments (source="manual") are never overwritten.
2. Assignment rows (coarse date-range aggregates) — kept for the legacy schedule view.

Ghost tasks: tasks where scheduled_effort_hours < effort_hours after scheduling.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, List, Set, Tuple

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from services.integration_service.contracts import NormalizedSourceBundle
    from services.planning_engine_service.contracts import DraftScheduleResult


def _round_up_half(hours: float) -> float:
    """Round hours up to the nearest 0.5 (e.g. 6.3 → 6.5, 6.0 → 6.0)."""
    return math.ceil(hours * 2) / 2


class AllocationOutputWriter:
    """Translates DraftScheduleResult into DayAllocation + Assignment rows in SQLite."""

    def write(
        self,
        draft_schedule: "DraftScheduleResult",
        bundle: "NormalizedSourceBundle",
        session: "Session",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        from services.persistence.models import Assignment, DayAllocation, Member, Task

        # ── Build lookup maps ────────────────────────────────────────────────
        task_ext_to_id: Dict[str, int] = {
            t.external_id: t.id for t in session.query(Task).all()
        }
        member_ext_to_id: Dict[str, int] = {
            m.external_id: m.id
            for m in session.query(Member).filter_by(is_active=True).all()
        }

        # ── Build per-day rows from engine output ────────────────────────────
        # Each TaskAllocationOutput is already one day — collect (task_id, member_id, date, hours)
        day_rows: List[Dict[str, Any]] = []
        engine_day_keys: Set[Tuple[int, int, str]] = set()  # (task_id, member_id, date)

        for alloc in draft_schedule.allocation_outputs:
            task_id = task_ext_to_id.get(alloc.task_external_id)
            member_id = member_ext_to_id.get(alloc.resource_external_id)
            if task_id is None or member_id is None:
                continue
            key = (task_id, member_id, alloc.date)
            engine_day_keys.add(key)
            day_rows.append({
                "task_id": task_id,
                "member_id": member_id,
                "date": alloc.date,
                "hours": alloc.allocated_hours,
            })

        # ── Ghost tasks (effort not fully placed) ────────────────────────────
        ghost_tasks = [
            {
                "task_external_id": ts.task_external_id,
                "task_name": ts.task_name,
                "unscheduled_hours": _round_up_half(ts.unscheduled_effort_hours),
                "status": ts.status,
            }
            for ts in draft_schedule.task_schedules
            if ts.unscheduled_effort_hours > 0
        ]

        # ── Preview (dry_run) ────────────────────────────────────────────────
        preview_rows = day_rows if dry_run else None

        written = 0
        skipped_manual = 0

        if not dry_run:
            # ── Collect PINNED manual DayAllocation keys (never overwrite) ──
            # Only pinned=True manual allocations are protected from engine overwrite.
            # Unpinned manual allocations are treated as replaceable.
            manual_keys: Set[Tuple[int, int, str]] = {
                (da.task_id, da.member_id, da.date)
                for da in session.query(DayAllocation).filter_by(source="manual", pinned=True).all()
            }

            # Also honour old-style manual Assignment rows as pinned
            manual_assignment_pairs: Set[Tuple[int, int]] = {
                (a.task_id, a.member_id)
                for a in session.query(Assignment).all()
                if a.field_overrides.get("manual") is True
            }
            for (task_id, member_id, date) in list(engine_day_keys):
                if (task_id, member_id) in manual_assignment_pairs:
                    manual_keys.add((task_id, member_id, date))

            # ── Delete stale engine/import DayAllocation rows not in new output ─
            # Scoped to only tasks in this run (don't touch other projects)
            task_ids_in_scope = {key[0] for key in engine_day_keys}
            if task_ids_in_scope:
                stale = session.query(DayAllocation).filter(
                    DayAllocation.source.in_(["engine", "import"]),
                    DayAllocation.task_id.in_(task_ids_in_scope),
                ).all()
            else:
                stale = []
            for da in stale:
                if (da.task_id, da.member_id, da.date) not in engine_day_keys:
                    session.delete(da)
            session.flush()

            # ── Upsert new engine DayAllocation rows (skip manual) ────────────
            for row in day_rows:
                key = (row["task_id"], row["member_id"], row["date"])
                if key in manual_keys:
                    skipped_manual += 1
                    continue
                existing = session.query(DayAllocation).filter_by(
                    task_id=row["task_id"], member_id=row["member_id"], date=row["date"]
                ).first()
                if existing is not None:
                    existing.hours = row["hours"]
                    existing.source = "engine"
                else:
                    session.add(DayAllocation(
                        task_id=row["task_id"],
                        member_id=row["member_id"],
                        date=row["date"],
                        hours=row["hours"],
                        source="engine",
                    ))
                written += 1

            # ── Also update coarse Assignment rows (legacy calendar view) ─────
            grouped: Dict[Tuple[int, int], Dict] = defaultdict(
                lambda: {"min_date": None, "max_date": None, "total_hours": 0.0}
            )
            for row in day_rows:
                if (row["task_id"], row["member_id"], row["date"]) in manual_keys:
                    continue
                g = grouped[(row["task_id"], row["member_id"])]
                g["total_hours"] += row["hours"]
                if g["min_date"] is None or row["date"] < g["min_date"]:
                    g["min_date"] = row["date"]
                if g["max_date"] is None or row["date"] > g["max_date"]:
                    g["max_date"] = row["date"]

            engine_pairs: Set[Tuple[int, int]] = set(grouped.keys())
            # Only clean assignments for tasks that were part of THIS wave's
            # scheduling scope. Include tasks with allocations AND tasks that
            # the engine attempted but couldn't place (unschedulable). Never
            # touch context-only predecessors from other waves.
            cleanup_task_ids: Set[int] = set(task_ids_in_scope)
            for ts in draft_schedule.task_schedules:
                # Include tasks the engine attempted (have unscheduled effort or
                # allocations). Skip context-only predecessors (0 effort, 0 unscheduled).
                if getattr(ts, 'unscheduled_effort_hours', 0) > 0 or \
                   getattr(ts, 'scheduled_effort_hours', 0) > 0:
                    tid = task_ext_to_id.get(ts.task_external_id)
                    if tid is not None:
                        cleanup_task_ids.add(tid)
            for a in session.query(Assignment).filter(
                Assignment.task_id.in_(cleanup_task_ids)
            ).all():
                if a.field_overrides.get("source") == "engine":
                    if (a.task_id, a.member_id) not in engine_pairs:
                        session.delete(a)
            session.flush()

            for (task_id, member_id), g in grouped.items():
                # Use exact sum of DayAllocation hours (already rounded individually)
                rounded = round(g["total_hours"], 2)
                existing = session.query(Assignment).filter_by(
                    task_id=task_id, member_id=member_id
                ).first()
                if existing is not None:
                    if existing.field_overrides.get("manual") is True:
                        continue
                    existing.allocated_hours = rounded
                    existing.start_date = g["min_date"]
                    existing.end_date = g["max_date"]
                    existing.field_overrides = {**existing.field_overrides, "source": "engine"}
                else:
                    session.add(Assignment(
                        task_id=task_id,
                        member_id=member_id,
                        allocated_hours=rounded,
                        start_date=g["min_date"],
                        end_date=g["max_date"],
                        field_overrides={"source": "engine"},
                    ))

            session.commit()

        return {
            "written": written,
            "skipped_manual": skipped_manual,
            "ghost_tasks": ghost_tasks,
            "proposed_reassignments": [],
            "preview_rows": preview_rows,
        }
