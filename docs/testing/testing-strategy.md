# Testing Strategy

## Testing principles
- Test business outcomes against approved manager workflows.
- Use the approved operating plan as operational truth, imported baseline as historical comparison reference, and latest synced source/task data as input to draft generation.
- Deterministic logic must produce stable outputs for identical inputs.
- UI tests verify representation, permissions, transitions, and edge states; they do not re-prove engine algorithms.
- Async tests verify state progression, idempotency, retries, and visible completion/failure state.
- End-to-end coverage stays thin and smoke-oriented.
- Use fixed canonical fixtures as the regression basis.

## Test layers
- Product acceptance / business workflow tests
- Screen / workflow tests
- Service-level tests
- Domain logic / unit tests
- Async workflow / integration tests
- Contract tests
- Thin end-to-end tests

## Service-by-service focus

### API Gateway / BFF
- screen payload composition
- permission-aware shaping
- command routing
- no silent loss of warnings/recommendations/deltas/blockers

### Workflow Orchestrator Service
- workflow lifecycle progression
- async state transitions
- retry/idempotency
- visible status/result

### Integration Service
- source readiness
- normalization correctness
- blocker vs advisory setup classification
- source-of-truth separation

### Planning Engine Service
- capacity calculations
- deterministic scheduling/allocation
- dependency-safe placement
- ghost allocation
- stable output ordering

### Review & Approval Service
- delta generation
- acceptance semantics
- dependency-safe blocking
- connected-set handling
- activation admission/control

### Decision Support Service
- warning/trust interpretation
- deterministic recommendation ranking
- explanation payloads
- no unsafe recommendation presented as safe

## High-risk scenarios
- intake readiness misclassification
- normalization drift
- capacity miscalculation
- non-deterministic scheduling/allocation
- ghost allocation regression
- diagnostics projection mismatch
- warnings/trust underexposed or misclassified
- recommendation ranking instability
- unsafe recommendation presentation
- dependency-safe approval failure
- activation truth corruption
- activation async state visibility failure
- bounded downstream write-back/status sync drift where in scope

## Fixture strategy
Use canonical fixtures for:
- clean runnable plan
- readiness-blocked plan
- overloaded portfolio
- ghost-allocation case
- warning-heavy case
- approval-blocked case
- activation/write-back case where approved
