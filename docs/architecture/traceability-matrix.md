# Traceability Matrix

## Product epic ↔ service mapping

| Epic | Primary services | Supporting services |
|---|---|---|
| EPIC-01 Plan Intake and Normalization | Integration Service | Workflow Orchestrator Service, API Gateway / BFF |
| EPIC-02 Capacity and Availability Modeling | Planning Engine Service | Integration Service, API Gateway / BFF |
| EPIC-03 Scheduling and Allocation Engine | Planning Engine Service | Workflow Orchestrator Service, API Gateway / BFF |
| EPIC-04 Planning Visibility and Diagnostics | API Gateway / BFF, Planning Engine Service | Review & Approval Service, Decision Support Service |
| EPIC-05 Planning Risk, Warnings, and Trust Controls | Decision Support Service | Integration Service, Planning Engine Service, Review & Approval Service, API Gateway / BFF |
| EPIC-06 Rebalancing Recommendations | Decision Support Service | Planning Engine Service, API Gateway / BFF |
| EPIC-07 Draft Review, Approval, and Plan Activation | Review & Approval Service, Workflow Orchestrator Service | Integration Service, API Gateway / BFF |

## Screen ↔ service mapping

| Screen | Primary services | Notes |
|---|---|---|
| S01 — Portfolio Swimlane Home | API Gateway / BFF, Planning Engine Service | May display EPIC-05/EPIC-07 indicators |
| S02 — Planning Setup | API Gateway / BFF, Integration Service, Planning Engine Service, Decision Support Service, Workflow Orchestrator Service | Readiness, advisory setup visibility, and run initiation |
| S03 — Resource Detail | API Gateway / BFF, Planning Engine Service, Decision Support Service | Resource diagnosis and recommendation consumption |
| S04 — Delta Review | API Gateway / BFF, Review & Approval Service | Review, acceptance, activation, plus review-confidence warning/trust context from Decision Support Service |
| S05 — Planning Warnings Workspace | API Gateway / BFF, Decision Support Service | Dedicated warning/trust review with upstream issue facts from Review & Approval, Planning Engine, and Integration Service |
| D01 — Swimlane Task Drill-Down Drawer | API Gateway / BFF, Planning Engine Service | Task drill-down from S01 — Portfolio Swimlane Home |
| M01 — Connected Change Set Modal | API Gateway / BFF, Review & Approval Service | Connected-set handling from S04 — Delta Review |

## Service ↔ epic/screen mapping

### API Gateway / BFF
- Product epics: EPIC-01, EPIC-02, EPIC-03, EPIC-04, EPIC-05, EPIC-06, EPIC-07
- Screens: S01 — Portfolio Swimlane Home, S02 — Planning Setup, S03 — Resource Detail, S04 — Delta Review, S05 — Planning Warnings Workspace, D01 — Swimlane Task Drill-Down Drawer, M01 — Connected Change Set Modal

### Workflow Orchestrator Service
- Product epics: EPIC-01, EPIC-03, EPIC-07
- Screens: S02 — Planning Setup, S04 — Delta Review

### Integration Service
- Product epics: EPIC-01, EPIC-02, EPIC-07
- Screens: S02 — Planning Setup

### Planning Engine Service
- Product epics: EPIC-02, EPIC-03, EPIC-04
- Screens: S01 — Portfolio Swimlane Home, S02 — Planning Setup, S03 — Resource Detail, D01 — Swimlane Task Drill-Down Drawer

### Review & Approval Service
- Product epics: EPIC-05, EPIC-07
- Screens: S04 — Delta Review, S05 — Planning Warnings Workspace, M01 — Connected Change Set Modal

### Decision Support Service
- Product epics: EPIC-05, EPIC-06
- Screens: S02 — Planning Setup, S03 — Resource Detail, S04 — Delta Review, S05 — Planning Warnings Workspace

## Drift-prevention rules
- Backlog, screens, acceptance criteria, and testing use the 7-epic product model.
- Architecture, API, data ownership, and implementation planning use the frozen service/domain model.
- When both appear, traceability must be shown.
- Screens are not epics.
- Services are not epics.
- No artifact may introduce alternative labels without mapping.
