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

Thin end-to-end golden-path coverage should verify at minimum:
- one setup-to-activation happy path with visible async activation and bounded write-back success
- one advisory-warning path that remains runnable
- one dependency-safe approval-blocking path that requires connected-set handling
- one post-activation write-back failure path that preserves approved operating plan truth

## Service-by-service focus

### API Gateway / BFF
- screen payload composition
- permission-aware shaping
- command routing
- S02 blocker versus advisory composition
- S01 daily-to-weekly roll-up derivation
- S01 ghost/indicator projection without planning-logic drift
- S03 single-resource summary, timeline, and queue composition
- S03 recommendation-context and warning-context visibility without ownership drift
- S03 trust-affected recommendation flagging without suppressing visible candidates by default
- S04 grouped delta review, acceptance-state, and blocked-isolated-acceptance composition
- S04 activation-state visibility and explicit activation command routing without taking ownership
- M01 connected-set modal composition and return-navigation context
- S04/M01 acceptance command routing into Review & Approval without taking ownership
- D01 selected-context drill-down shaping
- S05 one-list warning workspace composition
- S05 affected-workflow grouping, filtering, and scoped-entry preservation
- S05 blocking/advisory/trust-limited presentation without warning-ownership drift
- refresh/restricted screen-state shaping where surfaced
- no silent loss of warnings/recommendations/deltas/blockers

### Workflow Orchestrator Service
- workflow lifecycle progression
- async state transitions
- retry/idempotency
- visible status/result
- planning-run trigger admission
- planning-run handoff contract stability
- activation workflow trigger admission
- activation workflow step ordering and visible status progression
- activation downstream-step failure and retry handling
- activation workflow status contract stability
- non-runnable snapshot rejection

### Integration Service
- source readiness
- normalization correctness
- blocker vs advisory setup classification
- source-of-truth separation
- source/setup issue fact emission
- normalized output contract stability

### Planning Engine Service
- daily capacity calculations
- calendar and availability rule application
- exception override handling
- capacity-input readiness classification
- deterministic scheduling/allocation
- dependency-safe placement
- partially schedulable and unschedulable draft handling
- planning-run execution contract stability
- variance fact generation
- criticality fact generation
- planning issue-fact boundary correctness
- ghost allocation
- stable output ordering

### Review & Approval Service
- delta generation
- delta-scope attribute guardrails
- acceptance semantics
- explicit acceptance selection/deselection mutation through command contracts
- dependency-safe blocking
- blocked isolated acceptance emits current approval blocker facts even when acceptance selection itself is not mutated
- connected-set handling
- connected-set acceptance clears unresolved blocker facts deterministically
- deterministic connected-set resolution and minimal-set membership
- activation admission/control
- approved operating plan update from the selected approved set only
- repeated activation idempotency and initial downstream-handoff contract behavior
- approval/activation issue-fact emission
- deterministic blocker/outcome fact IDs and ordering
- boundary assertions proving warning/trust state is not created here

### Decision Support Service
- warning/trust interpretation
- cross-service issue-fact interpretation
- blocker vs advisory warning classification
- trust-limited interpretation classification
- recommendation-context retrieval and freshness-state stability
- deterministic recommendation generation from Planning Engine outputs
- stable recommendation candidate IDs and ordering where published
- stable issue-fact provenance in interpreted outputs
- deterministic recommendation ranking
- locked recommendation tie-break enforcement
- recommendation-origin context for downstream review usage
- explanation payloads
- no unsafe recommendation presented as safe

## High-risk scenarios
- intake readiness misclassification
- normalization drift
- capacity miscalculation
- non-deterministic scheduling/allocation
- daily-to-weekly roll-up drift
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
- malformed source import
- missing dependency target at normalization layer
- planning-run trigger baseline
- planning-run failure/retry case
- capacity FTE baseline
- capacity part-time baseline
- capacity exception baseline
- capacity missing-availability baseline
- draft schedule happy path
- draft schedule capacity-constrained case
- draft schedule partial/unschedulable case
- diagnostics no-variance case
- diagnostics slippage case
- diagnostics dependency-pressure case
- diagnostics planning-issue case
- recommendation multi-candidate case
- overloaded portfolio
- ghost-allocation case
- warning-heavy case
- approval-blocked case
- reviewable-delta no-delta case
- reviewable-delta simple comparison case
- reviewable-delta dependency-linked connected-set case
- reviewable-delta blocked isolated-acceptance case
- reviewable-delta valid acceptance selection case
- activation explicit-command/idempotency case
- activation/write-back case where approved
- write-back success case
- write-back partial-result case
- write-back failed-but-approved-truth-preserved case
- write-back retry/idempotent case
