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

Current baseline note:
- The current repo baseline now covers deterministic draft scheduling and allocation outputs inside Planning Engine plus the Workflow Orchestrator handoff adapter into Planning Engine execution.
- The current repo baseline now covers S01 — Portfolio Swimlane Home and D01 — Swimlane Task Drill-Down Drawer BFF composition over Planning Engine daily/draft/diagnostic outputs, including weekly roll-up derived from daily swimlane segments only.
- The current repo baseline now also exposes a minimal real API Gateway / BFF transport surface for frontend consumption of S01, S02, S03, S04, M01, and S05 payloads plus the current planning-run, acceptance-selection, recommendation-refresh, and activation command/status seams without moving ownership out of downstream services.

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

Current baseline note:
- The current repo baseline now covers Planning Engine-owned variance facts, criticality facts, and planning issue facts as comparison-ready inputs derived from draft scheduling outputs.
- S02 — Planning Setup now composes setup-relevant warning/trust signals from Decision Support outputs without taking ownership of the warning/trust lifecycle.
- The current repo baseline now covers Decision Support-owned warning/trust interpretation over Integration, Planning Engine, and Review & Approval issue facts with deterministic screen-scoped warning/trust state for S02 — Planning Setup, S04 — Delta Review, and S05 — Planning Warnings Workspace.
- S03 — Resource Detail now composes a focused single-resource summary, workload timeline, assigned work / queue, warning/trust context, and recommendation context from Planning Engine and Decision Support outputs in the API Gateway / BFF.
- S05 — Planning Warnings Workspace now composes a one-list warning workspace over Decision Support outputs with affected-workflow grouping, scoped-entry defaults, trust guidance, and return-navigation context in the API Gateway / BFF.
- Decision Support now generates, ranks, persists, and exposes deterministic recommendation candidates for S03 — Resource Detail using the locked MVP tie-break rules and stable candidate IDs.
- recommendation-origin context is now available for later S04 — Delta Review handoff without moving recommendation ownership into Review & Approval or the BFF.

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
Implementation note:
- The current repo baseline now covers Review & Approval-owned reviewable delta generation between current draft and current approved operating plan, limited delta scope for task dates/milestone dates/project finish/in-scope assignments, deterministic connected-set resolution for unsafe isolated acceptance, explicit acceptance-selection mutation through Review & Approval command contracts, and continued issue-fact emission for downstream interpretation without taking warning/trust lifecycle ownership.
- The current repo baseline now covers deterministic approval-blocker issue-fact evaluation in Review & Approval for unresolved blocked isolated-acceptance attempts, connected-set-required conditions, safe no-blocker cases, and explicit activation-blocking conditions already represented in the current contracts.
- The current repo baseline now covers API Gateway / BFF composition for S04 — Delta Review and M01 — Connected Change Set Modal, including grouped/item-level review shaping, blocked isolated-acceptance presentation, explicit acceptance command routing into Review & Approval, and already-available warning/trust and recommendation-origin context display without moving ownership out of downstream services.

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
Implementation note:
- Activation-blocker facts and activation outcome facts are emitted by Review & Approval for later Decision Support consumption; interpreted warnings remain out of scope for this phase.
- S04 — Delta Review remains the user-facing activation entry point after acceptance; Review & Approval owns activation business truth and Workflow Orchestrator owns downstream async workflow state.
- The current repo baseline now covers the explicit Review & Approval activation command/result contract, valid-approved-set admission checks, idempotent re-activation handling for the same already-applied selected set, approved operating plan snapshot updates from the selected accepted deltas, Workflow Orchestrator-owned activation workflow execution/status with deterministic downstream recomputation-first and bounded side-effect sequencing hooks, and Integration-owned bounded external write-back execution/result tracking from orchestrated post-activation requests only.

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
