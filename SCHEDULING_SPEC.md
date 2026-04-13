# Scheduling Engine — Functional Specification

> Canonical reference for scheduling behavior, contracts, and invariants.
> All prompts and future work on the scheduling system must conform to this spec.

---

## 1. Core Concepts

### 1.1 Entities

| Entity | Description |
|--------|-------------|
| **Task** | A unit of work with effort (hours), start/end dates, and optional parent. Only leaf tasks (no children) are scheduled by the engine. |
| **Member** | A team resource with weekly capacity, working days, and availability. |
| **Assignment** | Coarse link: task + member + date range + total allocated hours. Legacy view. |
| **DayAllocation** | Fine-grained: task + member + specific date + hours. Source of truth for calendar. |
| **TimeOff** | Leave/absence blocking a member's capacity for a date range. |
| **TaskDependency** | Link between tasks: FS, FF, SS, SF types. |
| **PlanningRun** | Record of an engine execution (status, timestamps, counts). |

### 1.2 Hierarchy

- Tasks form a tree via `parent_id` and `hierarchy_depth`.
- **Only leaf tasks** (tasks with no children) carry effort and are scheduled.
- Parent tasks are display containers — their dates are derived from their children's date range.
- Both Tasks tab and Schedule tab must support **collapse/expand** of child tasks under parents.

### 1.3 Working Days & Capacity

- Each member defines their own `working_days` (e.g., `["Sun","Mon","Tue","Wed","Thu"]`).
- `daily_capacity = weekly_capacity_hours / count(working_days)`.
- Non-working days have zero capacity.
- TimeOff records set capacity to zero for specific dates.
- Manual DayAllocations reduce (not eliminate) remaining capacity for that day.

---

## 2. Scheduling Algorithm

### 2.1 Inputs

The engine receives a `NormalizedSourceBundle` containing:
- Tasks (with effort, start_date, due_date)
- Resources (with capacity, working_days)
- Assignments (task-to-resource links)
- Dependencies (FS/FF/SS/SF)
- Resource exceptions (time-off, manual allocations)

### 2.2 Preconditions for Scheduling a Task

A task is schedulable only when ALL of these are true:
1. `effort_hours` is set (not None, > 0)
2. `start_date` and `due_date` are set
3. At least one resource is assigned
4. All predecessors are fully scheduled (status = "scheduled")
5. The dependency-adjusted window (earliest_start to effective_due_date) is valid

If any precondition fails, the task is marked **unschedulable** with a specific issue code.

### 2.3 Dependency Types

| Type | Constraint |
|------|-----------|
| **FS** (Finish-to-Start) | Successor cannot start until predecessor finishes. `earliest_start = max(earliest_start, predecessor_end + 1 day)` |
| **FF** (Finish-to-Finish) | Successor cannot finish before predecessor finishes. Extends `effective_due_date` if needed. |
| **SS** (Start-to-Start) | Successor cannot start before predecessor starts. `earliest_start = max(earliest_start, predecessor_start)` |
| **SF** (Start-to-Finish) | Successor cannot finish before predecessor starts. Extends `effective_due_date` if needed. |

### 2.4 Task Ordering

- Tasks are topologically sorted using Kahn's algorithm.
- **Cycle detection:** If any tasks remain after the sort (cycle exists), they are flagged with a `"dependency_cycle"` issue and appended to the end. The engine does NOT silently ignore cycles.

### 2.5 Effort Distribution (Multi-Resource)

When a task has multiple assigned resources:
1. If any assignment has `allocation_percent`, use percentages as weights.
2. Otherwise, split equally.
3. Last resource gets the remainder (no rounding loss).

### 2.6 Daily Allocation

For each assignment share:
1. Iterate through each day in the scheduling window (earliest_start to effective_due_date).
2. Check remaining capacity for (resource, date).
3. Allocate `min(available_capacity, remaining_effort)`.
4. Round allocated hours UP to nearest 0.5h for display.
5. Deduct the **unrounded** effort from remaining (not the rounded allocation).
6. Cap the final day's allocation so total does not exceed actual effort.

### 2.7 Task Status After Scheduling

| Status | Condition |
|--------|-----------|
| `scheduled` | All effort placed within the window |
| `partially_scheduled` | Some effort placed, but not all |
| `unschedulable` | Zero effort placed |

---

## 3. Data Integrity Invariants

### 3.1 Effort is Immutable During Scheduling

- The engine NEVER mutates `Task.estimated_hours` or `Task.buffer_hours` in the database.
- Remaining effort is computed at bundle-build time and passed as input.
- If the process crashes, task effort values are always intact.

### 3.2 Manual Allocations Are Respected

- `DayAllocation` rows with `source="manual"` are never overwritten by the engine.
- Manual allocations REDUCE (not eliminate) a member's available capacity for that day.
- `available_capacity = max(0, daily_capacity - sum_of_manual_hours_on_that_day)`

### 3.3 DayAllocation Is Source of Truth

- `DayAllocation` (per-day) is the authoritative record for what's scheduled.
- `Assignment` (coarse range) is derived from DayAllocations — its `allocated_hours` equals the exact sum of its DayAllocation hours (no additional rounding).

### 3.4 Task Dates Reflect Actual Allocations

- After any allocation change (engine run, reassign-day, reassign-chunk, create/update/delete assignment):
  - `task.scheduled_start_date` = earliest date with a DayAllocation for that task
  - `task.scheduled_end_date` = latest date with a DayAllocation for that task
- **Effort stays unchanged** — only dates update. Effort is the user's explicit input.

### 3.5 Tasks Without Dates

- Tasks missing `start_date` or `due_date` are flagged with issue code `"missing_dates"`.
- The engine does NOT auto-assign dates.
- The user must manually set dates before the task can be scheduled.

---

## 4. Cross-Project Visibility

- There are NO cross-project task dependencies.
- When scheduling a single project, the engine MUST see ALL DayAllocations for in-scope members across ALL projects.
- This ensures the engine knows the member's TRUE remaining availability per day.
- A member booked 6h/day on Project A should show only 2h available when scheduling Project B (assuming 8h/day capacity).

---

## 5. Scheduling Idempotency

- Running the engine twice on the same input data must produce the same output.
- Before building the bundle, all `source="engine"` DayAllocation rows for in-scope tasks are cleared.
- `source="engine"` Assignment rows are excluded from bundle construction.

---

## 6. UI Behavior

### 6.1 Schedule Trigger

- **Endpoint:** `POST /api/schedule/run`
- **Body:** `{ dry_run: bool, project_id?: int, member_ids?: [int] }`
- `dry_run: true` → returns preview without writing
- `dry_run: false` → writes DayAllocations, updates task dates, returns summary

### 6.2 Task Hierarchy Display

- Tasks are displayed as an indented tree (parent → children) in both Tasks tab and Schedule tab.
- **Collapse/expand:** Each parent task has a chevron toggle. Collapsed parents hide all descendants.
- **Collapse All / Expand All:** Toolbar buttons to toggle all parents at once.
- Collapse state is shared between Tasks tab and Schedule tab within the same project view.

### 6.3 Capacity Display

- Cell footer shows utilization — toggleable between `%` mode and `Hours` mode via toolbar button.
  - `%` mode: `85%`
  - `Hours` mode: `5.5/8h` (allocated / capacity)
- Cell background tone: green (<80%), amber (80-99%), red (>=100%).
- Overloaded cells show red footer text.
- **Tooltip on hover:** Full breakdown by project — `"6h allocated (4h Project A, 2h Project B) — 2h remaining"`

### 6.4 Ghost Tasks / Warnings

- Tasks with `unscheduled_effort_hours > 0` are reported as "ghost tasks" in the engine response.
- Tasks without dates are reported with `"missing_dates"` issue.
- Both are surfaced as warning banners in the UI.

---

## 7. API Contracts

### 7.1 Run Schedule Response

```json
{
  "run_id": "uuid",
  "status": "scheduled | partially_schedulable | unschedulable",
  "dry_run": true,
  "assignments_written": 42,
  "skipped_manual": 3,
  "ghost_tasks": [
    { "task_external_id": "...", "task_name": "...", "unscheduled_hours": 4.0, "status": "partially_scheduled" }
  ],
  "preview_rows": [...],
  "overscheduled_tasks": [...]
}
```

### 7.2 Date Sync After Reassignment

After `POST /api/schedule/reassign-day` or `POST /api/schedule/reassign-chunk`:
- Backend recalculates `task.scheduled_start_date` and `scheduled_end_date` from DayAllocations.
- Response includes updated task dates.

---

## 8. Architecture Boundaries

| Layer | Responsibility |
|-------|---------------|
| **BFF Handler** (`float_runtime.py`) | HTTP transport only — parse request, call services, return response. No domain logic. |
| **Bundle Builder** (`sqlite_bundle_builder.py`) | Read SQLite, compute remaining effort, ensure assignments exist, build NormalizedSourceBundle. |
| **Planning Engine** (`service.py`) | Pure computation — capacity modeling, task scheduling, diagnostics. No DB access. |
| **Allocation Writer** (`allocation_writer.py`) | Write engine output back to SQLite. Respect manual allocations. Sync task dates. |
