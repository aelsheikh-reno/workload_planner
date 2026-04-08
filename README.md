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

## Local MVP Run
The repo now includes a seeded local runtime so the current MVP flow can be used in-browser without bypassing the real BFF transport.

Quick start:
1. From the repo root, run `./scripts/run_local_mvp.sh`
2. Open the printed frontend URL, usually `http://127.0.0.1:5173`
3. The seeded runtime starts with:
   - a normalized source snapshot
   - a completed planning run for `context::frontend-shell`
   - a current approved operating plan snapshot
   - a saved `S04` review context that exposes `M01`
   - seeded `S05` warning/trust workspace data

Useful local notes:
- The BFF server defaults to a seeded `local-demo` runtime when started with `python3 -m services.api_gateway_bff.server`
- `./scripts/run_local_mvp.sh` will use the requested frontend and BFF ports when available and otherwise move each service to the next open local port
- The frontend continues to proxy `/api` and `/health` to the launched BFF target
- The browser-shell Reset button clears frontend-held context only
- Stopping and restarting the BFF resets the seeded in-memory backend state
- `S02` import/sync remains admission-and-handoff only in the current MVP transport; the seeded snapshot exists so the local browser flow is still runnable end to end
