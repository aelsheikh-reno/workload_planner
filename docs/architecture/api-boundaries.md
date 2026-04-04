# API Boundaries

## Principles
- Frontend interacts through API Gateway / BFF only.
- BFF owns transport-level command/query endpoints and screen read-model composition only.
- Domain command ownership remains with downstream owning services.
- Sync for user-facing reads and lightweight command admission.
- Async for:
  - source import/sync
  - planning run
  - recommendation precompute/refresh where heavy
  - downstream recomputation after activation
  - bounded write-back/status sync

## Command/query ownership

### Integration Service
Commands:
- start import/sync
- validate/normalize source inputs
- initiate bounded external write-back
Queries:
- source readiness
- latest import/sync status
- write-back result/status

### Planning Engine Service
Commands:
- execute planning run
- recompute planning outputs
Queries:
- latest draft planning outputs
- capacity outputs
- scheduling/allocation outputs
- planning diagnostics and variance/criticality outputs

### Review & Approval Service
Commands:
- generate/refresh reviewable deltas
- record acceptance selection
- resolve connected set
- activate approved changes
Queries:
- reviewable deltas
- acceptance state
- connected set
- approved operating plan state
- activation status/history

### Decision Support Service
Commands:
- refresh warning/trust interpretation
- generate recommendations
- refresh recommendations
- precompute recommendations
Queries:
- S05 — Planning Warnings Workspace data
- warning/trust state for screens
- recommendations for S03 — Resource Detail
- recommendation freshness/status

### Workflow Orchestrator Service
Commands:
- start import/sync workflow
- start planning run workflow
- start recommendation precompute workflow
- start recomputation workflow
- start bounded write-back workflow
Queries:
- workflow/job status
- workflow history/log

## Major user-facing command flows
- S02 — Planning Setup → start import/sync → BFF → Workflow Orchestrator → Integration
- S02 — Planning Setup → start planning run → BFF → Workflow Orchestrator → Planning Engine
- S03 — Resource Detail → get/refresh recommendations → BFF → Decision Support
- S04 — Delta Review → get deltas → BFF → Review & Approval
- S04 — Delta Review → record acceptance → BFF → Review & Approval
- M01 — Connected Change Set Modal → resolve connected set → BFF → Review & Approval
- S04 — Delta Review → activate approved changes → BFF → Review & Approval, then async downstream via Workflow Orchestrator
- S05 — Planning Warnings Workspace → get S05 — Planning Warnings Workspace data → BFF → Decision Support

## Async workflow boundaries
Must be async:
- import/sync
- planning run
- recommendation precompute when heavy
- downstream recomputation after activation
- bounded external write-back/status sync

May remain sync:
- S05 — Planning Warnings Workspace retrieval
- S04 — Delta Review retrieval
- connected-set retrieval
- acceptance selection
- recommendation retrieval when already precomputed
- S02 — Planning Setup readiness retrieval
- swimlane and screen view retrieval
