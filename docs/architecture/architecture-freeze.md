# Architecture Freeze

## Architecture goals
- modularity with explicit ownership boundaries
- low coupling
- independent service evolution
- containerized deployment
- deterministic planning core
- safe stepwise implementation

## Frozen MVP service set

### API Gateway / BFF
Owns:
- frontend-facing API surface
- auth enforcement
- response composition/adaptation
Does not own:
- orchestration
- planning logic
- warning/trust lifecycle
- recommendation lifecycle
- approval rules

### Workflow Orchestrator Service
Owns:
- workflow sequencing
- async job coordination
- retries/timeouts/failure handling
- workflow status/state
Does not own:
- planning calculations
- warning/trust interpretation
- recommendation logic
- approval business rules

### Integration Service
Owns:
- MS Project import
- Asana inbound sync
- bounded outbound write-back
- source artifact retention
- source mappings
- source normalization
- integration validation/audit
- integration issue facts/signals
Does not own:
- planning calculations
- review/approval state
- warning/trust interpretation lifecycle
- recommendation lifecycle

### Planning Engine Service
Owns:
- capacity computation
- scheduling computation
- variance/criticality computation
- draft planning outputs only
- planning-derived issue facts/signals
Does not own:
- external integrations
- reviewable deltas
- acceptance state
- approved operating plan state
- warning/trust interpretation lifecycle
- recommendation lifecycle

### Review & Approval Service
Owns:
- reviewable deltas
- acceptance state
- approved operating plan state
- dependency-safe approval validation
- minimal connected approval set resolution
- activation business state/result
- approval audit records
Does not own:
- planning calculations
- draft planning outputs
- external write-back
- warning/trust interpretation lifecycle
- recommendation lifecycle

### Decision Support Service
Owns:
- warning/trust interpretation lifecycle
- warning catalog/state
- trust/explanation model
- recommendation generation/scoring
- recommendation persistence
- recommendation freshness/precompute/refresh
Does not own:
- raw issue fact generation
- planning calculations
- approval state mutation
- external write-back
- workflow sequencing

## Boundary rules
- BFF may aggregate/adapt frontend contracts but owns no business logic.
- Workflow Orchestrator coordinates workflows but owns no business truth outside workflow state.
- Integration Service is the only external-system writer.
- Planning Engine owns draft planning outputs only.
- Review & Approval owns reviewable deltas, acceptance state, and approved operating plan state only.
- Decision Support is the only warning/trust interpreter and recommendation owner.
- Other services may emit issue facts/signals only.

## Deployment shape
Containers:
- frontend
- api-gateway
- workflow-orchestrator
- integration-service
- planning-engine-service
- review-approval-service
- decision-support-service
- database
- queue-broker
- object-storage

Storage:
- one relational DB cluster with separate schema per service
- object/file storage for source artifacts
- queue/broker for async workflows
