# Product Overview

## Product
Capacity-Aware Execution Planner

## Primary users
- Delivery Manager
- Resource / Operations Manager
- Project Manager

## MVP purpose
Turn imported plan data and capacity truth into:
- a realistic draft schedule
- portfolio and resource diagnostics
- risk/warning/trust signals
- deterministic recommendation options
- controlled review/approval/activation into the operating plan

## Core workflows
1. source readiness and S02 — Planning Setup
2. planning run and draft generation
3. portfolio visibility in S01 — Portfolio Swimlane Home and resource diagnosis in S03 — Resource Detail
4. warning/trust review in S05 — Planning Warnings Workspace
5. recommendation handling in S03 — Resource Detail
6. draft-vs-approved review in S04 — Delta Review
7. dependency-safe acceptance in M01 — Connected Change Set Modal when required
8. explicit activation in S04 — Delta Review
9. bounded downstream write-back/status sync where approved

## Scope boundaries
In scope:
- approved 7 epics
- approved MVP screen set
- frozen service/domain model
- explicit activation after acceptance

Out of scope:
- source authoring
- broad admin console
- hidden confirmation state separate from review/activation
- broad downstream sync platform
