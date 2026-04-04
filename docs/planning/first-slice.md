# First Slice

## Slice
S02 — Planning Setup thin vertical slice

## Services involved
- API Gateway / BFF
- Workflow Orchestrator Service
- Integration Service
- Planning Engine Service

## Product epics
- EPIC-01 — Plan Intake and Normalization
- EPIC-02 — Capacity and Availability Modeling
- EPIC-05 — Planning Risk, Warnings, and Trust Controls

## User-visible outcome
User can:
1. open S02 — Planning Setup
2. see source readiness
3. see capacity-input readiness
4. see overall runnable vs not-runnable state
5. trigger a planning run command
6. see tracked planning-run status
7. be blocked only by true no-runnable-plan blockers

## What is stubbed initially
- live Asana adapter behavior
- full scheduler output
- S01 — Portfolio Swimlane Home swimlane rendering
- recommendations
- review/approval
- bounded downstream sync/write-back
- rich explanation text

## Acceptance criteria
- S02 — Planning Setup renders source readiness, capacity-input readiness, and overall readiness correctly
- advisory vs blocking setup conditions are distinguished correctly
- planning run can be initiated through BFF and tracked through workflow state
- no-runnable-plan blockers prevent planning entry
- non-blocking warnings do not prevent planning entry once runnable
- service and BFF contracts are fixture-backed and deterministic

## Required tests
- source readiness classification tests
- capacity-input readiness classification tests
- runnable/not-runnable aggregation tests
- blocker vs advisory tests
- workflow status progression tests
- BFF contract tests for S02 — Planning Setup
- S02 — Planning Setup screen/workflow tests for ready, partial, blocked, loading, and restricted states

## Follow-on slices unlocked
- S01 — Portfolio Swimlane Home first read-only version
- deeper EPIC-01/02 hardening
- deterministic planning run output exposure
