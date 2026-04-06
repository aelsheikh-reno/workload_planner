# AGENTS.md

## Project intent
Build the **Capacity-Aware Execution Planner MVP** as a production-grade system that:
- imports source plans
- computes a capacity-aware draft schedule
- produces deterministic recommendation options
- routes accepted changes through review/approval
- activates only explicitly approved outcomes

## Source-of-truth order
1. `docs/product/locked-decisions.md`
2. `docs/product/epic-map.md`
3. `docs/product/screen-inventory.md`
4. `docs/product/screen-contract.md`
5. `docs/architecture/architecture-freeze.md`
6. `docs/architecture/traceability-matrix.md`
7. `docs/architecture/api-boundaries.md`
8. `docs/architecture/data-model-decomposition.md`
9. `docs/testing/testing-strategy.md`
10. `docs/planning/codex-build-plan.md`
11. `docs/planning/first-slice.md`

If a requested change conflicts with these docs, stop and update the docs first.

## Non-negotiable model rules
- Honor the approved **7-epic product model** only.
- Honor the frozen **service/domain ownership model** only.
- Screens are not epics.
- Services are not epics.
- Epics define product capability slices.
- Screens define user interaction surfaces.
- Services define technical ownership boundaries.

## Service ownership rules
- **API Gateway / BFF** owns frontend-facing transport contracts and screen read-model composition only.
- **Workflow Orchestrator Service** owns workflow lifecycle and cross-service async sequencing only.
- **Integration Service** owns source ingestion, normalization, source mappings, source artifacts, and bounded external write-back only.
- **Planning Engine Service** owns capacity, scheduling, draft planning outputs, and planning-derived facts only.
- **Review & Approval Service** owns reviewable deltas, acceptance state, approved operating plan state, connected-set handling, and activation business state only.
- **Decision Support Service** owns warning/trust interpretation lifecycle and recommendation lifecycle only.

## Scope-control rules
- Do not invent features outside approved docs.
- Do not backfill missing requirements from memory.
- Do not add hidden workflow steps, extra screens, or extra services.
- Do not convert advisory behavior into blocking behavior, or the reverse, without a doc update.
- Do not merge acceptance and activation into one action.
- Do not add draft-time write-back to source systems.
- Do not let source sync overwrite approved operating plan truth.

## Testing expectations
- Every requirement must be testable.
- Deterministic recommendation ranking must be reproducible.
- Blocking and advisory warnings must be independently testable.
- Activation must be tested separately from acceptance.
- State, permission, and edge-case behavior must be tested for every screen surface and embedded interaction.
- Service contracts must be tested independently from end-to-end UI flows.

## Code-change discipline
- Make the smallest change that satisfies the targeted slice.
- Preserve service boundaries and explicit contracts.
- Update docs, tests, and contracts in the same change when behavior changes.
- Add or update traceability when a screen, epic, or service mapping changes.
- Prefer container-friendly, decoupled modules and explicit interfaces.
- Reject changes that require undocumented scope expansion.

## Codex task discipline
- One bounded task at a time.
- Always specify:
  - owning service/module
  - affected epic(s)
  - affected screen(s)
  - what must not be touched
  - required tests
- Do not do cross-service refactors unless the task is explicitly a contract task.

## Required implementation workflow
For every implementation task, Codex must:

1. Read AGENTS.md and the relevant docs before coding.
2. Produce a short execution plan before changing files.
3. Identify:
   - owning service/module
   - affected epic(s)
   - affected screen(s)
   - docs/contracts/tests touched
4. Implement only the bounded task requested.
5. Run required tests/checks.
6. Spawn a reviewer subagent before finishing.

## Reviewer subagent requirements
The reviewer subagent must audit:
- service-boundary compliance
- scope drift
- contract/doc alignment
- test adequacy
- unintended file changes
- naming/model drift against canonical docs

The reviewer must report:
- pass/fail
- issues found
- required fixes before merge
- whether the task is truly done against acceptance criteria

## Done criteria
A task is not done until:
- implementation is complete
- required tests pass
- docs/contracts are updated if needed
- reviewer subagent signs off or lists explicit blocking issues