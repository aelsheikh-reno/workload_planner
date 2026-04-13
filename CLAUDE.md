# Scheduling Engine — Development Rules & Invariants

> This document is read automatically by every Claude session. It documents HOW to safely
> modify the scheduling code — the hard rules that prevent regressions. For WHAT the engine
> does, see `SCHEDULING_SPEC.md`.

---

## 1. Architecture

The scheduling pipeline has 4 layers. Data flows one direction: **DB → Bundle → Engine → DB**.

| Layer | File | Responsibility |
|-------|------|---------------|
| **Bundle Builder** | `services/schedule_service/sqlite_bundle_builder.py` | Read SQLite, compute remaining effort, ensure assignments exist, extend date windows, build `NormalizedSourceBundle` |
| **Planning Engine** | `services/planning_engine_service/service.py` | Pure computation — capacity modeling, topological sort, daily allocation. No DB access. |
| **Allocation Writer** | `services/schedule_service/allocation_writer.py` | Write engine output back to SQLite. Respect pinned/manual allocations. |
| **BFF** | `services/api_gateway_bff/float_runtime.py` | HTTP transport — parse request, call services, return response. No domain logic. |

**Never skip a layer.** The BFF must not compute scheduling logic. The engine must not access the DB.

---

## 2. Critical Invariants — MUST NOT Violate

### 2.1 Single Source of Truth for Dates
- Task dates live in `scheduled_start_date` / `scheduled_end_date` DB columns ONLY
- `field_overrides` is for metadata (`_original_start`, `_original_end`, `source`, `asana_gid`) — **NEVER** for values the engine reads during scheduling
- **Why**: We added `field_overrides.get("scheduled_end_date")` as a date override. It silently capped the scheduling window, making the engine ignore buffer hours. Took a full debugging session to find.

### 2.2 Parent Tasks = Containers (effort=0)
- Tasks with children get `effort_hours=0` in the bundle (not `None`)
- The engine marks them `SCHEDULED` instantly so dependencies through parents don't block leaf tasks
- If a parent gets `effort_hours=None`, it's marked `UNSCHEDULABLE` → blocks ALL downstream successors
- **Detection**: In `sqlite_bundle_builder.py build()`, `_parent_ids` set identifies parents

### 2.3 Effort = estimated_hours + buffer_hours
- Every place that computes effort MUST include both fields: `(t.estimated_hours or 0.0) + (t.buffer_hours or 0.0)`
- Search for `estimated_hours` without `buffer_hours` nearby → that's a bug
- The engine sees only `effort_hours` — it never distinguishes estimated from buffer
- **Pitfall**: `(est or 0.0) + (buf or 0.0) or None` — the trailing `or None` converts `0.0` to `None` because `0.0` is falsy in Python

### 2.4 Pinned = User Intent, Unpinned = Engine Optimizes
- Pinned `DayAllocation` rows (`pinned=True`) survive cleanup and are never overwritten
- Unpinned tasks use `_original_start` from `field_overrides` so the engine can re-optimize when capacity changes
- Pinned tasks keep their current `scheduled_start_date`
- **Both the bundle builder and the extension pass must use this same logic** — if they disagree on starting dates, the engine gets a mismatched window

### 2.5 No Silent Reassignment
- The scheduler NEVER silently reassigns a task's owner to a different member
- Out-of-scope owners trigger the preflight conflict popup (`analyze_ownership_conflicts`)
- User must explicitly approve any ownership change via `ownership_resolutions`
- Default behavior for unresolved out-of-scope owners: **keep** (add owner to member set)

### 2.6 Allocation Writer Scoping
- The allocation writer MUST only clean assignments for tasks in the current scheduling scope
- `cleanup_task_ids` = tasks with `unscheduled_effort_hours > 0` or `scheduled_effort_hours > 0`
- Context-only predecessors (effort=0) from other waves are EXCLUDED from cleanup
- **Why**: Wave 2's writer was deleting Wave 1's engine assignments, breaking subsequent runs

---

## 3. Wave Scheduling Rules

The frontend computes dependency waves and calls `POST /api/schedule/run` separately per wave.

- Wave 1: tasks with no unresolved predecessors
- Wave 2+: tasks whose predecessors were scheduled in earlier waves
- Each wave's `prepare_and_build` includes transitive predecessors as **context-only** (effort=0)
- Context-only tasks are for dependency resolution ONLY — their allocations are NOT touched
- `projected_end` = window boundary (for cascade extension); `actual_effort_end` = when effort actually finishes (for pull-forward)
- Sibling pull-forward uses `actual_effort_end`, NOT `projected_end` (inflated by sibling extension)

When running for specific `task_ids` (wave mode):
- `projected_end/projected_start` must be initialized for predecessor tasks from their DB dates
- Missing predecessors (from earlier waves, not in `all_tasks`) must be loaded separately

---

## 4. Date Extension Rules

- Extensions only **GROW** windows, never shrink
- No date reset between runs — removed because it caused second-run failures (capacity landscape changes between runs)
- `_original_start` / `_original_end` saved on first encounter for the explicit "Reset to Import" button
- Extension pass uses `_original_start` for unpinned tasks (matching what the bundle gives the engine)
- **Sibling competition**: for each member, compute `needed_end` from `latest_start` among member's tasks using total member effort / actual available capacity (including cross-project deductions and time-off)
- **Dependency cascade pass** (third pass): after sibling extension, re-check successors whose dep-derived start changed and re-extend their windows

---

## 5. Capacity Rules

- Cross-project `DayAllocation` rows reduce member capacity via `NormalizedResourceExceptionRecord`
- When multiple exceptions exist for same `(resource_id, date)`, keep the **MINIMUM** `available_capacity_hours` — time-off (0h) must win over cross-project deduction
- `member_effort` for auto-assignment **includes** cross-project DayAllocation hours (not just in-project)
- Auto-assignment scopes to **project members** (via `ProjectMember` table) when `member_ids` not provided — never assigns to global members outside the project

---

## 6. Rounding Rule

- Allocations rounded UP to nearest 0.5h: `math.ceil(raw_hours * 2) / 2`
- **Cumulative cap**: `allocated_hours = min(allocated_hours, share_hours - cumulative_allocated)`
- This ensures the sum of all `allocated_hours` across days exactly matches `share_hours`
- Without the cap, rounding steals capacity from sibling tasks on the same member

---

## 7. Testing & Verification

### 7a. Unit Tests
```bash
pytest tests/planning_engine_service/ tests/schedule_service/ -v
```
All tests must pass after EVERY change. Current count: 102.

### 7b. Integration Verification Scenarios

Run against real DB after any change to the scheduling pipeline. These caught real regressions:

| ID | Scenario | What to verify |
|----|----------|---------------|
| V1 | Buffer inclusion | `estimated=16 + buffer=20` → `effort_hours=36` in bundle, allocations sum to 36h |
| V2 | Parent passthrough | Parent tasks have `effort_hours=0`, successors NOT blocked |
| V3 | Member scoping | Only project members in bundle — no global members |
| V4 | Rounding cap | 4.3h task → allocations sum to exactly 4.3h, not 4.5h |
| V5 | Partial predecessor | `partially_scheduled` predecessor does NOT block successor |
| V6 | Idempotency | Run 3x consecutively → identical results |
| V7 | Wave assignment persistence | Wave 2 writer does NOT delete Wave 1 assignments |
| V8 | Freed capacity | Remove blocker, re-run → tasks pack tighter |
| V9 | Preflight conflicts | `preflight: true` with excluded owner → `ownership_conflicts` returned |
| V10 | Conflict resolution | `ownership_resolutions: {action: "keep"}` → owner preserved |
| V11 | Cross-project in auto-assign | Heavy cross-project member NOT picked as "least loaded" |
| V12 | Time-off vs cross-project | Same (member, date) with time-off + cross-project → capacity = 0h |

### 7c. Test Rules
- Every bug fix MUST include a unit test that fails before the fix and passes after
- Every new feature MUST include happy path + edge case tests
- If a V-scenario catches a regression the unit tests missed → add a new unit test for it
- When behavior changes by design, update test expectations — don't delete tests

---

## 8. Common Pitfalls

| Pitfall | What happened | Prevention |
|---------|--------------|------------|
| Dict comprehension for exceptions | Overwrites duplicates — time-off lost | Use loop with `min()` |
| `0.0 or None` | Python evaluates to `None` (0.0 is falsy) | Explicit `if x is None` check |
| Reading dates from `field_overrides` | Stale values bypass extensions | Read from DB column only |
| Writer scans ALL assignments | Deletes other waves' assignments | Scope to `cleanup_task_ids` |
| Date reset to originals | Second run fails — capacity changed | Never reset, only grow |
| Sibling extension from `earliest_start` | Misses later-starting tasks | Use `latest_start` per member |
| `projected_end` inflated by sibling ext | Breaks pull-forward for successors | Separate `actual_effort_end` |
| `member_effort` without cross-project | Wrong "least loaded" member picked | Seed with cross-project hours |
| Auto-assign to all active members | Members outside project get tasks | Scope via `ProjectMember` table |
