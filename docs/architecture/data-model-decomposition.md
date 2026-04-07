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
- normalized task/subtask records
- normalized dependency records
- normalized resource-assignment records
- normalized resource capacity profiles
- normalized calendar/availability inputs
- normalized resource exception inputs
- normalized effort/date field normalization
- source sync/readiness state
- activation-linked write-back request/result state
- integration audit records
- integration issue facts/signals

### Planning Engine Service
Owns:
- planning runs
- capacity outputs
- daily capacity output records
- capacity-input readiness state
- capacity-input issue facts
- resource capacity summaries
- draft plan snapshots
- draft schedule records
- draft task timing outputs
- draft allocation outputs
- draft scheduling issue facts/signals
- scheduling/allocation outputs
- comparison-ready variance facts
- comparison-ready criticality facts
- diagnostics comparison-context metadata
- variance/criticality facts
- planning diagnostics facts
- planning issue facts/signals

### Review & Approval Service
Owns:
- review contexts
- delta review sets/items backing S04 — Delta Review
- delta attribute-change records comparing current draft versus current approved operating plan
- acceptance state
- connected change sets backing M01 — Connected Change Set Modal
- connected-set resolution records for blocked isolated-acceptance evaluation
- activation command admission/result records
- activation records/business result
- approved plan snapshots/current pointer
- approval audit records
- approval issue facts/signals, including dependency-safe blockers, connected-set-required facts, activation blockers, and activation outcome facts

### Decision Support Service
Owns:
- warnings
- interpreted warning records
- warning groups/workspace entries
- trust interpretation records
- trust explanations
- warning/trust lifecycle state
- recommendations
- recommendation freshness/generation state
- recommendation ranking state
- recommendation origin context

### Workflow Orchestrator Service
Owns:
- workflow instances
- planning-run workflow instances
- activation workflow instances
- workflow step instances
- activation workflow step instances
- planning-run transition records
- activation workflow transition records
- planning-run trigger metadata
- activation workflow trigger metadata
- retry state for workflow/job execution
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
  - write-back request Q triggered by activation Z through workflow W step `activation_side_effect_sequencing`
- external project/task/resource IDs remain mapped only through Integration-owned source mappings

## State model decomposition
- Source artifacts → Integration Service
- Normalized planning records → Integration Service
- Capacity setup/normalized planning inputs → Integration Service
- Capacity-input readiness and daily capacity truth → Planning Engine Service
- Draft planning outputs, draft schedules, and draft allocations → Planning Engine Service
- Variance facts, criticality facts, and planning issue facts → Planning Engine Service
- Planning-run execution/business entity → Planning Engine Service
- Reviewable deltas → Review & Approval Service
- Acceptance state → Review & Approval Service
- Approved operating plan → Review & Approval Service
- Issue facts/signals → emitting service
- Warnings/trust state → Decision Support Service
- Recommendations → Decision Support Service
- Workflow/job state, transitions, and retry history → Workflow Orchestrator Service
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
- planning-run execution state as business execution reference → Planning Engine
- deltas/acceptance/approved plan → Review & Approval
- warnings/trust/recommendations → Decision Support
- approval/activation issue facts remain upstream inputs for Decision Support interpretation rather than interpreted warning state themselves
- workflow/job state → Workflow Orchestrator
- write-back request/result → Integration
