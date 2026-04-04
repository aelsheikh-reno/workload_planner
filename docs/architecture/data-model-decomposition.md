# Data Model Decomposition

## Data modeling principles
- One authoritative owning service per entity family.
- Other services may reference or cache, but do not become owners.
- Cross-service references are by canonical IDs.
- External source IDs remain owned by Integration Service mappings.
- Draft planning outputs and approved operating plan remain separate entity families.
- Issue facts/signals are distinct from interpreted warnings/trust state.
- Review & Approval owns activation business truth; Workflow Orchestrator owns activation workflow status only.
- External write-back result never redefines internal approval truth.

## Service-owned entity families

### Integration Service
Owns:
- source artifacts
- source snapshots
- external source mappings
- normalized planning records
- source sync/readiness state
- write-back request/result state
- integration audit records
- integration issue facts/signals

### Planning Engine Service
Owns:
- planning runs
- capacity outputs
- draft plan snapshots
- scheduling/allocation outputs
- variance/criticality facts
- planning diagnostics facts
- planning issue facts/signals

### Review & Approval Service
Owns:
- review contexts
- delta review sets/items backing S04 — Delta Review
- acceptance state
- connected change sets backing M01 — Connected Change Set Modal
- activation records/business result
- approved plan snapshots/current pointer
- approval audit records
- approval issue facts/signals

### Decision Support Service
Owns:
- warnings
- warning groups/workspace entries
- trust explanations
- recommendations
- recommendation freshness/generation state

### Workflow Orchestrator Service
Owns:
- workflow instances
- workflow step instances
- retry/failure records
- job execution status/history

## Cross-service reference model
Use canonical IDs for:
- resource, task, project
- planning run
- draft plan
- approved plan
- delta/review context
- acceptance selection where needed
- recommendation
- warning
- issue fact/signal
- activation
- write-back request/result
- workflow/job

Reference discipline:
- cross-service references are by ID only
- record provenance conceptually:
  - derived from draft plan X
  - warning derived from issue fact Y
  - write-back triggered by activation Z

## State model decomposition
- Source artifacts → Integration Service
- Normalized planning records → Integration Service
- Capacity setup/normalized planning inputs → Integration Service
- Draft planning outputs → Planning Engine Service
- Reviewable deltas → Review & Approval Service
- Acceptance state → Review & Approval Service
- Approved operating plan → Review & Approval Service
- Issue facts/signals → emitting service
- Warnings/trust state → Decision Support Service
- Recommendations → Decision Support Service
- Workflow/job state → Workflow Orchestrator Service
- Activation state/result → Review & Approval Service
- External write-back request/result → Integration Service
- Audit records → local to owning service

## Derived/read-model guidance
May duplicate:
- non-authoritative summaries
- screen-facing projections
- workflow correlation fields
Must remain authoritative:
- normalized planning records → Integration
- draft planning outputs → Planning Engine
- deltas/acceptance/approved plan → Review & Approval
- warnings/trust/recommendations → Decision Support
- workflow/job state → Workflow Orchestrator
- write-back request/result → Integration
