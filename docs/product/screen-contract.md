# Screen Contract

## Boundary matrix

### S01 — Portfolio Swimlane Home
Owns:
- portfolio-wide planning visibility
- time-based resource swimlane comparison
- entry into drill-down, diagnosis, review, and warning review
May display:
- capacity-derived metrics
- draft/approved awareness
- warning/trust indicators
- risk/movement indicators
- ghost-load visibility
Must never own:
- setup/configuration
- warning remediation
- recommendation generation
- formal acceptance/activation
- task editing or scheduling logic

### S02 — Planning Setup
Owns:
- compact source readiness and capacity-input readiness
- runnable vs not-runnable setup status
- lightweight setup completion actions in approved scope
May display:
- setup-relevant warning/trust signals
- source freshness/readiness
- capacity-input completeness
Must never own:
- portfolio visibility
- diagnostics
- S04 — Delta Review review/activation behavior
- full S05 — Planning Warnings Workspace behavior
- generic admin-console behavior

### S03 — Resource Detail
Owns:
- single-resource diagnosis
- workload timeline and queue visibility
- distinct workload timeline and assigned work / queue sections
- recommendation consumption for that resource where allowed
- resource-scoped warning/risk visibility
May display:
- overload/free-capacity signals
- ghost-load and placement outputs
- recommendation outputs generated elsewhere
- recommendation effect summaries and recommendation-origin context generated elsewhere
- trust-affected recommendation context without suppressing recommendations by default
- review handoff indicators
Must never own:
- portfolio-wide dashboard behavior
- setup/configuration
- final approval/activation
- warning remediation
- direct plan-application behavior
- recommendation generation logic

### S04 — Delta Review
Owns:
- formal review of draft-vs-approved changes
- reviewable deltas limited to approved MVP delta scope: task dates, milestone dates, project finish, and in-scope assignment changes
- acceptance selection state
- dependency-safe blocked acceptance handling
- connected-set launch into M01 — Connected Change Set Modal when isolated acceptance is unsafe
- explicit activation entry point for accepted changes when valid
May display:
- grouped delta summaries
- risk/movement indicators tied to changes
- recommendation-origin indicators
- downstream recommendation-origin context routed from S03 — Resource Detail where relevant
- warning/trust indicators affecting review confidence
- activation admission/result status and downstream activation workflow status metadata
Must never own:
- portfolio visibility
- resource diagnosis
- setup/configuration
- warning remediation
- recommendation generation
- activation workflow execution
- scheduling execution/editor behavior

### S05 — Planning Warnings Workspace
Owns:
- dedicated warning/trust review
- one-list warning/trust presentation with default grouping by affected workflow
- warning grouping/filtering/review
- trust/interpretation guidance
- routing back to owning workflows
May display:
- source-related warning context
- capacity-related warning context
- origin-scoped filtered entry from S01 — Portfolio Swimlane Home, S02 — Planning Setup, S03 — Resource Detail, or S04 — Delta Review
- resource-, portfolio-, and delta-review affected context
Must never own:
- setup correction
- portfolio dashboard behavior
- resource diagnosis ownership
- acceptance/activation
- recommendation generation/consumption
- generic admin-console behavior

## Navigation contract
- S01 — Portfolio Swimlane Home → S02 — Planning Setup: no-runnable-plan or readiness entry
- S01 — Portfolio Swimlane Home → S03 — Resource Detail: selected resource/lane/problem area
- S01 — Portfolio Swimlane Home → S04 — Delta Review: draft-vs-approved review action
- S01 — Portfolio Swimlane Home → S05 — Planning Warnings Workspace: warning/trust indicator
- S02 — Planning Setup → S01 — Portfolio Swimlane Home: continue to planning when runnable
- S02 — Planning Setup → S05 — Planning Warnings Workspace: setup warning needs deeper review
- S03 — Resource Detail → S01 — Portfolio Swimlane Home: return to portfolio context
- S03 — Resource Detail → S04 — Delta Review: formal review required
- S03 — Resource Detail → S05 — Planning Warnings Workspace: warning/trust issue needs deeper review
- S04 — Delta Review → M01 — Connected Change Set Modal: isolated acceptance is blocked and minimal connected-set handling is required
- S04 — Delta Review → S01 — Portfolio Swimlane Home / S03 — Resource Detail: return to originating context
- S04 — Delta Review → S05 — Planning Warnings Workspace: warning/trust issue affects review confidence
- S05 — Planning Warnings Workspace → S01 — Portfolio Swimlane Home / S02 — Planning Setup / S03 — Resource Detail / S04 — Delta Review: return to owning workflow

## Shared interaction rules
- Preserve across screens only:
  - active plan context
  - origin screen
  - selected entity/scope
  - selected time window where relevant
- Full source-screen filter state is not preserved unless explicitly approved.
- S03 — Resource Detail recommendation consumption may hand off into S04 — Delta Review review context but does not bypass S04 — Delta Review.
- Warnings are advisory by default across S01 — Portfolio Swimlane Home, S02 — Planning Setup, S03 — Resource Detail, and S04 — Delta Review except:
  - true readiness blockers in S02 — Planning Setup
  - explicit dependency-safe or activation blockers in S04 — Delta Review

## Embedded interaction contract
### D01 — Swimlane Task Drill-Down Drawer
May:
- show task-level detail for the selected S01 — Portfolio Swimlane Home segment
- preserve S01 — Portfolio Swimlane Home as the owning screen
May not:
- become a task editor
- replace S03 — Resource Detail
- become an approval surface

### M01 — Connected Change Set Modal
May:
- explain why isolated acceptance is unsafe
- show the minimal dependency-safe connected set required for grouped approval
- allow connected-set acceptance where authorized
- return the user to S04 — Delta Review with updated acceptance-selection context
May not:
- replace S04 — Delta Review
- edit dependencies
- generate changes/recommendations
