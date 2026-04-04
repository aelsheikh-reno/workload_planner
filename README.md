# Capacity-Aware Execution Planner — Repo Doc Pack

This repository doc pack is the canonical implementation baseline for the MVP.

## What this pack contains
- product scope and epic map
- screen inventory and cross-screen contract
- locked MVP decisions
- frozen architecture and traceability rules
- API boundary map
- data model decomposition
- testing strategy
- Codex implementation plan and first implementation slice

## Canonical usage
Use these docs in this order:
1. `AGENTS.md`
2. `docs/product/locked-decisions.md`
3. `docs/product/epic-map.md`
4. `docs/product/screen-inventory.md`
5. `docs/product/screen-contract.md`
6. `docs/architecture/architecture-freeze.md`
7. `docs/architecture/traceability-matrix.md`
8. `docs/architecture/api-boundaries.md`
9. `docs/architecture/data-model-decomposition.md`
10. `docs/testing/testing-strategy.md`
11. `docs/planning/codex-build-plan.md`
12. `docs/planning/first-slice.md`

## Canonical models
### Product truth
- EPIC-01 — Plan Intake and Normalization
- EPIC-02 — Capacity and Availability Modeling
- EPIC-03 — Scheduling and Allocation Engine
- EPIC-04 — Planning Visibility and Diagnostics
- EPIC-05 — Planning Risk, Warnings, and Trust Controls
- EPIC-06 — Rebalancing Recommendations
- EPIC-07 — Draft Review, Approval, and Plan Activation

### Approved MVP screens
- S01 — Portfolio Swimlane Home
- S02 — Planning Setup
- S03 — Resource Detail
- S04 — Delta Review
- S05 — Planning Warnings Workspace
- D01 — Swimlane Task Drill-Down Drawer
- M01 — Connected Change Set Modal

### Frozen service/domain model
- API Gateway / BFF
- Workflow Orchestrator Service
- Integration Service
- Planning Engine Service
- Review & Approval Service
- Decision Support Service

## Governance rule
Screens are not epics.
Services are not epics.
When both product epics and services appear in an artifact, include traceability.
