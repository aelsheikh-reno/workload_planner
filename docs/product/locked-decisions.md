# Locked Decisions

## Canonical product and screen model
- Use the approved 7-epic model only.
- Approved MVP screens:
  - S01 — Portfolio Swimlane Home
  - S02 — Planning Setup
  - S03 — Resource Detail
  - S04 — Delta Review
  - S05 — Planning Warnings Workspace
  - D01 — Swimlane Task Drill-Down Drawer
  - M01 — Connected Change Set Modal

## Warning/trust ownership
- EPIC-05 owns warnings, trust controls, and interpretation logic.
- Warnings/trust may appear across screens and workflows, but ownership remains with EPIC-05.

## Downstream sync/write-back scope
- Limited downstream write-back/status sync remains in MVP only where already approved.
- It is explicit, orchestrated, and not a broad sync platform.
- It is post-activation only.

## Recommendation ranking determinism
- Recommendation ranking must be deterministic for identical inputs.
- Tie-break order:
  1. lower disruption / blast radius
  2. lower handoff overhead
  3. action family order: rechunk → move/defer → reassignment → date extension
  4. stable internal candidate ID

## Activation model
- Activation is an explicit user action.
- Activation command is initiated synchronously.
- Downstream recomputation and side effects are async with visible status/result.
- Accepted changes do not become active automatically.

## Permissions
- Delivery Manager: review, accept, connected-set handling, activate
- Resource / Operations Manager: review visibility only, no activation
- Project Manager: read-only / limited review visibility, no acceptance or activation

## Blocking vs advisory warnings
Blocking:
- true no-runnable-plan readiness blockers on S02 — Planning Setup
- explicit dependency-safe approval blockers on S04 — Delta Review
- explicit activation blockers
Advisory by default:
- warning-heavy states
- trust-limited states
- fallback/inferred-data warnings
- weak planning-confidence warnings

## Source-of-truth conflict rule
- Imported baseline = historical comparison reference
- Approved operating plan = current internal operational truth
- Latest synced source/task data = latest source input for new draft generation
- Reviewable deltas are generated between current draft and current approved operating plan
- Source sync never directly replaces approved operating plan truth

## Screen-phase locked decisions
### S01 — Portfolio Swimlane Home
- review-aware only; not review-owning
- no-runnable-plan banner must link to S02 — Planning Setup
- Project Manager may open S03 — Resource Detail only within authorized scope
- ghost load is scheduler-owned ghost allocations for work not fully placed into normal draft allocations under current constraints

### S02 — Planning Setup
- status-first, not admin-first
- source readiness supports lightweight actions only
- capacity-input readiness may support compact edit surfaces where approved
- continue to planning is allowed when setup is runnable even if non-blocking warnings exist

### S03 — Resource Detail
- recommendation consumption means inspect/select recommendation candidate and hand off into S04 — Delta Review where required
- S03 — Resource Detail does not directly apply plan changes
- S03 — Resource Detail keeps both workload timeline and assigned work/queue visibility
- trust-affected recommendations remain visible but flagged when relevant

### S04 — Delta Review
- activation is explicit after acceptance
- item-level acceptance is primary
- group-level acceptance is only a convenience wrapper and must not weaken dependency-safe rules

### S05 — Planning Warnings Workspace
- review-and-navigation only in MVP
- no acknowledge/read workflow state in MVP
- defaults to originating scope/context filter
- default grouping is by affected workflow
