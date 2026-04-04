# Codex Build Plan

## Build strategy
Recommended order:
1. freeze contracts and shared state model
2. build intake + readiness + capacity truth
3. build deterministic scheduling and draft outputs
4. build diagnostics and warnings/trust
5. build S04 — Delta Review and dependency-safe approval
6. build activation and bounded downstream side effects

Why:
- normalized inputs → capacity truth → deterministic draft → reviewable delta → approval/activation is the stable dependency chain
- warnings/recommendations depend on stable outputs from earlier layers
- bounded external side effects are safest last

## Implementation phases

### Phase 1 — Canonical plan foundation
Goal:
- define canonical normalized entities, draft vs approved plan state model, planning run contract, activation lifecycle skeleton
Services:
- Planning Engine
- Workflow Orchestrator
- API Gateway / BFF
Epics:
- EPIC-01
- EPIC-02
- EPIC-07 foundation
Screens:
- S02 — Planning Setup skeleton only

### Phase 2 — Intake, readiness, and capacity truth
Goal:
- source readiness, capacity-input readiness, runnable/not-runnable status
Services:
- Integration
- Workflow Orchestrator
- Planning Engine
- API Gateway / BFF
Epics:
- EPIC-01
- EPIC-02
- EPIC-05 readiness blockers
Screens:
- S02 — Planning Setup

### Phase 3 — Deterministic scheduling and portfolio visibility
Goal:
- daily scheduling, chunking, ghost outputs, portfolio swimlane payload
Services:
- Planning Engine
- Workflow Orchestrator
- API Gateway / BFF
Epics:
- EPIC-03
- EPIC-04
Screens:
- S01 — Portfolio Swimlane Home
- D01 — Swimlane Task Drill-Down Drawer
- partial S03 — Resource Detail

### Phase 4 — Diagnostics, warnings, and recommendation scaffolding
Goal:
- resource diagnostics, S05 — Planning Warnings Workspace behavior, deterministic recommendation contract
Services:
- Decision Support
- Planning Engine
- API Gateway / BFF
Epics:
- EPIC-04
- EPIC-05
- EPIC-06 scaffold
Screens:
- S03 — Resource Detail
- S05 — Planning Warnings Workspace

### Phase 5 — Delta review and dependency-safe approval
Goal:
- S04 — Delta Review, acceptance, connected-set handling
Services:
- Review & Approval
- Planning Engine
- Workflow Orchestrator
- API Gateway / BFF
Epics:
- EPIC-07
Screens:
- S04 — Delta Review
- M01 — Connected Change Set Modal

### Phase 6 — Activation and bounded downstream side effects
Goal:
- explicit activation, async recomputation, bounded downstream sync/write-back
Services:
- Review & Approval
- Workflow Orchestrator
- Integration
- API Gateway / BFF
Epics:
- EPIC-07
Screens:
- S04 — Delta Review complete
- final status behavior on S01 — Portfolio Swimlane Home
- final status behavior on S03 — Resource Detail
- final status behavior on S05 — Planning Warnings Workspace

## Codex task-shaping rules
- one bounded task at a time
- always specify owning service/module
- always specify affected epic(s) and screen(s)
- always specify what must not be touched
- always require tests
- always require contract/doc updates when interfaces change
- avoid cross-service refactors unless the task is explicitly a contract task
- prefer this order:
  - contract/model
  - service logic
  - service tests
  - BFF mapping
  - screen wiring
  - E2E verification
