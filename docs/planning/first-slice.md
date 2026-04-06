# First Slice

## Slice
S02 — Planning Setup thin vertical slice

## Services involved
- API Gateway / BFF
- Workflow Orchestrator Service
- Integration Service
- Planning Engine Service
- Decision Support Service

## Product epics
- EPIC-01 — Plan Intake and Normalization
- EPIC-02 — Capacity and Availability Modeling
- EPIC-04 — Planning Visibility and Diagnostics
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
- S01 — Portfolio Swimlane Home swimlane rendering
- recommendations
- review/approval
- bounded downstream sync/write-back
- rich explanation text

## Current EPIC-01 baseline note
- The current implementation baseline is fixture-driven source intake and normalization inside the Integration Service.
- S02 — Planning Setup now exposes source readiness from the Integration Service baseline.
- The planning-run workflow/job lifecycle baseline now exists in the Workflow Orchestrator Service for S02 — Planning Setup status exposure.
- The EPIC-02 Planning Engine baseline now provides deterministic daily capacity outputs plus a capacity-input readiness contract from normalized source inputs.
- The EPIC-03 Planning Engine baseline now provides deterministic draft scheduling and allocation outputs plus the planning-run execution record needed for later S01 — Portfolio Swimlane Home and D01 — Swimlane Task Drill-Down Drawer composition.
- BFF composition now combines source readiness, capacity-input readiness, and setup-relevant warning/trust signals into an S02-only runnable/not-runnable view model.
- True no-runnable-plan blockers on S02 come only from source readiness and capacity-input readiness; Decision Support warning/trust signals remain advisory in this slice.
- S01 — Portfolio Swimlane Home swimlane composition and D01 — Swimlane Task Drill-Down Drawer shaping now exist as the first BFF read-model baseline over Planning Engine daily, draft, and diagnostics outputs.
- Live external adapter behavior remains an explicit downstream stub outside this slice.

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
- daily capacity output contract tests
- runnable/not-runnable aggregation tests
- blocker vs advisory tests
- workflow status progression tests
- BFF contract tests for S02 — Planning Setup
- Current baseline covers S02 — Planning Setup ready, partial, blocked, refresh, and restricted contract states.

## Follow-on slices unlocked
- S01 — Portfolio Swimlane Home first read-only version
- deeper EPIC-01/02 hardening
- deterministic planning run output exposure
- D01 — Swimlane Task Drill-Down Drawer read model shaping
