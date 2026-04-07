# API Boundaries

## Principles
- Frontend interacts through API Gateway / BFF only.
- BFF owns transport-level command/query endpoints and screen read-model composition only.
- Domain command ownership remains with downstream owning services.
- Sync for user-facing reads and lightweight command admission.
- Async for:
  - source import/sync
  - planning run
  - recommendation precompute/refresh where heavy
  - downstream recomputation after activation
  - bounded write-back/status sync

## Command/query ownership

### Integration Service
Commands:
- start import/sync
- validate/normalize source inputs
- initiate bounded external write-back
Queries:
- source readiness
- latest import/sync status
- latest normalized source snapshot
- source artifact metadata and payload reference
- source mappings for projects/tasks/resources
- source/setup issue facts
- write-back result/status

### Planning Engine Service
Commands:
- execute planning run
- recompute planning outputs
- compute daily capacity baseline
- compute planning diagnostics facts
Queries:
- latest draft planning outputs
- capacity outputs
- scheduling/allocation outputs
- planning diagnostics and variance/criticality outputs

### Review & Approval Service
Commands:
- generate/refresh reviewable deltas
- record acceptance selection
- resolve connected set
- activate approved changes
Queries:
- reviewable deltas
- acceptance state
- connected set
- approved operating plan state
- activation status/history
- review/activation issue facts

## Review & Approval delta contract
The Review & Approval Service owns the reviewable delta artifact layer for S04 — Delta Review and M01 — Connected Change Set Modal. The baseline contract covers:
- deterministic review-context generation between the current draft schedule and the current approved operating plan
- reviewable delta items limited to approved MVP delta scope only
- draft-to-approved comparison references for the current review context
- optional recommendation-origin references when upstream contracts already provide them
- minimal connected change set resolution for dependency-safe grouped approval when isolated acceptance is unsafe
- explicit acceptance-selection mutation through a separate Review & Approval command contract

Review context contract:
- review_context_id
- planning_run_id/source_snapshot_id/approved_plan_id
- draft_schedule_id
- comparison_context as `draft_vs_current_approved_plan`
- delta_set_id
- delta_items
- connected_change_sets

Reviewable delta item contract:
- delta_id
- entity_type/entity_id/entity_external_id/entity_name
- task_id/task_external_id/task_name when the delta is task-scoped
- project_id/project_external_id
- delta_scope_attributes limited to approved attributes only
- attribute_changes with before/after values
- dependency_delta_ids
- connected_set_id when dependency-safe grouped approval is required
- selected_for_acceptance for Review & Approval-owned review-selection state
- recommendation_origin_refs when upstream context is already available, using canonical task IDs or project-scoped task identity when canonical task IDs are absent

Connected change set contract:
- connected_set_id
- review_context_id
- member_delta_ids
- member_entity_external_ids
- minimal_for_dependency_safety

Connected set resolution contract:
- resolution_id
- review_context_id
- requested_delta_id
- isolated_acceptance_safe
- blocking_reason_code/blocking_reason_message when isolated acceptance is unsafe
- connected_change_set when a minimal dependency-safe grouped approval set is required

Acceptance selection result contract:
- command_id
- review_context_id
- selection_scope as `delta_item` or `connected_change_set`
- requested_delta_id
- connected_set_id when connected-set handling is required
- action as `select` or `deselect`
- status as `applied` or `blocked`
- blocked_reason_code/blocked_reason_message when isolated task-level acceptance is unsafe
- review_context with updated Review & Approval-owned acceptance-selection state
- connected_set_resolution when blocked or when connected-set selection is routed explicitly

Activation state contract:
- activation_id
- status as `not_requested`, `blocked`, or `activated`
- review_context_id
- approved_plan_id_before/approved_plan_id_after
- requested_by/requested_at
- selected_delta_ids
- business_rule_blockers when activation is not admissible
- outcome when activation completes

Activation command result contract:
- command_id
- review_context_id
- activation_state
- resulting_approved_plan_snapshot when activation completes
- reused_existing for idempotent re-activation of the same already-applied approved set
- downstream_handoff with Workflow Orchestrator ownership metadata, the initial `not_started` execution state only, the activated `source_snapshot_id`, and deterministic write-back targets for later post-activation orchestration

Contract rules:
- delta scope is limited to task dates, milestone dates, project finish, and in-scope assignment changes only
- Review & Approval owns reviewable deltas as business artifacts; Planning Engine comparison-ready facts do not replace them
- connected change set resolution returns the smallest dependency-safe related set needed to avoid leaving the approved plan in an inconsistent dependency state
- delta generation and connected-set resolution do not mutate acceptance state or activation state by themselves
- acceptance-selection mutation happens only through the explicit Review & Approval acceptance-selection command contract; activation remains a separate later command
- activation is admitted only for a current review context that has a valid selected approved set and a current approved operating plan pointer
- successful activation updates the current approved operating plan snapshot from the selected accepted deltas only; draft state and acceptance-selection state remain separate artifacts
- repeated activation of the same already-applied selected set may return the existing activation business result instead of mutating approved-plan truth again
- downstream async recomputation or workflow execution is not created here; the command result exposes initial handoff metadata only and Workflow Orchestrator remains the owner of execution state and later status progression
- IDs, ordering, and connected-set membership must remain deterministic for identical draft and approved inputs

### Decision Support Service
Commands:
- refresh warning/trust interpretation
- generate recommendations
- refresh recommendations
- precompute recommendations
Queries:
- S05 — Planning Warnings Workspace data
- warning/trust state for screens
- recommendations for S03 — Resource Detail
- recommendation freshness/status

### Workflow Orchestrator Service
Commands:
- start import/sync workflow
- start planning run workflow
- start activation workflow
- start recommendation precompute workflow
- start recomputation workflow
- start bounded write-back workflow
Queries:
- workflow/job status
- planning-run trigger admission result
- planning-run status for S02 — Planning Setup composition
- activation workflow status for S04 — Delta Review composition
- workflow history/log

## Planning-run workflow baseline
The Workflow Orchestrator provides the planning-run lifecycle baseline for S02 — Planning Setup. The baseline contract covers:
- planning-run trigger admission using a planning context key plus normalized source snapshot reference
- workflow/job state for queued, dispatched, running, retry-pending, failed, and succeeded execution states
- a stable handoff request to Planning Engine containing only correlation IDs and trigger metadata
- a stable status view keyed by planning context plus source snapshot for downstream composition without moving planning calculations into the Orchestrator

Planning Engine handoff contract:
- workflow_instance_id
- planning_context_key
- source_snapshot_id
- source_artifact_id
- requested_by
- requested_at
- attempt_number

Planning Engine execution receipt baseline:
- planning_run_id owned by Planning Engine as the draft execution reference
- accepted_at for the admitted execution attempt
- handoff acceptance does not create reviewable deltas or approved-plan state

Planning-run status contract:
- workflow_instance_id
- planning_context_key
- source_snapshot_id
- source_artifact_id
- planning_run_id as a reference to Planning Engine-owned planning-run execution
- status/current step
- current_attempt/max_attempts
- requested_by/requested_at
- last_transition_at
- completed_at
- last_error_code/last_error_message when relevant
- downstream composition should resolve status using planning_context_key plus source_snapshot_id together when a specific planning context is in scope

Lifecycle rules:
- Workflow Orchestrator owns workflow/job execution state only
- Planning Engine remains the owner of planning-run execution and draft planning outputs
- Integration Service remains the owner of normalized source readiness/input
- repeated start requests for the same active planning context reuse the active workflow instead of creating a duplicate execution
- no extra confirmation state is introduced between request admission and async execution

## Activation workflow baseline
The Workflow Orchestrator provides the activation workflow baseline for post-activation async execution visibility. The baseline contract covers:
- activation workflow admission from a valid Review & Approval activation command/result handoff
- workflow/job state for queued, dispatched, running, retry-pending, failed, and succeeded execution states
- ordered downstream hook sequencing for:
  - activation-triggered downstream recomputation
  - bounded downstream side-effect sequencing
- a stable status view keyed by activation ID or review context ID for downstream composition without moving activation business truth into the Orchestrator

Activation workflow trigger contract:
- activation_command_id
- activation_id
- review_context_id
- approved_plan_id
- source_snapshot_id when the downstream workflow carries bounded write-back provenance
- write_back_targets when bounded post-activation write-back is required, with:
  - target_id/delta_id
  - entity_type/entity_external_id/entity_name
  - project_external_id when task-scoped
  - write_back_action
  - write_back_fields
- requested_by
- requested_at
- idempotency_key
- max_attempts

Activation downstream-step handoff contract:
- workflow_instance_id
- activation_command_id
- activation_id
- review_context_id
- approved_plan_id
- source_snapshot_id when bounded post-activation write-back is in scope for the workflow
- write_back_targets when the side-effect step carries deterministic bounded write-back scope into Integration
- step_name
- requested_by
- requested_at
- attempt_number

Activation workflow status contract:
- workflow_instance_id
- activation_command_id
- activation_id
- review_context_id
- approved_plan_id
- status/current step
- current_attempt/max_attempts
- requested_by/requested_at
- last_transition_at
- completed_at
- last_error_code/last_error_message when relevant
- step_states with step_name, status, attempt_number, and downstream handoff ID

Lifecycle rules:
- Workflow Orchestrator owns activation workflow/job execution state only
- Review & Approval remains the owner of activation business result, approved operating plan mutation, and activation blocker logic
- activation workflow admission is valid only after explicit activation succeeds and produces a downstream handoff requirement
- downstream hooks are sequenced deterministically as recomputation first, then bounded side-effect sequencing
- the bounded side-effect step may carry Integration-owned write-back scope/provenance from Review & Approval, but Workflow Orchestrator still owns only async sequencing and visible workflow state
- repeated workflow start requests for the same activation ID reuse the existing workflow rather than creating a duplicate execution
- retry remains an explicit workflow-execution concern and does not reopen activation business admission
- bounded external write-back execution remains Integration-owned; Workflow Orchestrator only sequences the side-effect hook and surfaces async workflow state

## S02 — Planning Setup composed read contract
The API Gateway / BFF owns the S02 — Planning Setup view-model composition baseline. The composed contract covers:
- source readiness projection from Integration Service
- capacity-input readiness projection from Planning Engine Service
- setup-relevant warning/trust state projection from Decision Support Service when available
- overall runnable versus not-runnable evaluation for S02 only
- explicit separation between true no-runnable-plan blockers and advisory warning/trust signals
- lightweight screen state such as refresh and access restriction without moving domain ownership into the BFF

## Integration bounded external write-back baseline
The Integration Service owns the bounded post-activation external write-back baseline. The contract covers:
- explicit execution only from an orchestrated post-activation request
- deterministic target scope limited to already-approved MVP write-back fields/actions
- persisted write-back request/result state keyed by request ID with activation-linked provenance
- success, partial, failed, and idempotent result handling without redefining approved-plan truth

Bounded external write-back request contract:
- request_id
- activation_command_id/activation_id/review_context_id/approved_plan_id
- source_snapshot_id
- orchestrator_workflow_instance_id
- orchestrator_step_name as `activation_side_effect_sequencing`
- requested_by/requested_at
- attempt_number
- targets with:
  - target_id/delta_id
  - entity_type/entity_external_id/entity_name
  - project_external_id when task-scoped
  - write_back_action as `update_task_fields` or `update_project_fields`
  - write_back_fields limited to `task_start_date`, `task_due_date`, `milestone_date`, `project_finish_date`, and `assigned_resource_external_ids`
- idempotency_key when the orchestrated caller wants deterministic reuse for the same request

Bounded external write-back result/status contract:
- request_id
- activation_command_id/activation_id/review_context_id/approved_plan_id
- source_snapshot_id/source_system
- orchestrator_workflow_instance_id/orchestrator_step_name
- attempt_number
- status as `succeeded`, `partial`, or `failed`
- total_target_count/succeeded_target_count/failed_target_count
- requested_by/requested_at/completed_at
- reused_existing for idempotent replay of the same request
- item_results with:
  - target_id/delta_id
  - entity_type/entity_external_id
  - status as `succeeded` or `failed`
  - applied_fields
  - error_code/error_message when a bounded external target rejects the request

Contract rules:
- Integration Service is the only service allowed to write to external systems
- write-back may run only after explicit activation and only from an orchestrated post-activation request
- write-back scope remains bounded to the approved MVP delta attributes only
- write-back result/status is Integration-owned and must remain separate from activation business truth and approved operating plan truth
- failed or partial downstream write-back never rolls back the approved operating plan snapshot
- repeated execution of the same request may reuse the existing Integration-owned result; retry stays an explicit orchestrated concern and does not reopen activation business admission

S02 composed view-model contract:
- screen/query context metadata
- view state with screen state plus refresh/restricted flags
- source readiness
- capacity-input readiness
- overall readiness with `canContinueToPlanning`
- latest import metadata
- planning-run status
- source setup issues
- capacity-input issues
- setup warning/trust state
- aggregated no-runnable-plan blockers
- aggregated advisory signals
- stubbed dependency indicators when a supporting read seam is not wired

Composition rules:
- BFF does not create source/setup issue facts, capacity-input issues, or warning/trust interpretations
- true S02 blockers come only from Integration-owned source readiness or Planning Engine-owned capacity-input readiness
- warning/trust signals remain advisory on S02 by default and do not block planning entry on their own
- S02 remains status-first and does not become a generic admin/setup console
- when setup is runnable, planning entry remains allowed even if advisory warning/trust signals are present

## Integration normalized source contract
The Integration Service provides a bounded internal normalized-output bundle for downstream consumers. The bundle contains:
- source artifact metadata with a deterministic payload digest and retained imported payload
- source snapshot metadata for the normalized import baseline
- project, task, and resource mappings from external IDs to canonical internal IDs
- task mappings are project-scoped so repeated external task IDs do not collapse across projects
- normalized task/subtask records with hierarchy, effort, and date fields
- normalized dependency records
- normalized resource-assignment records
- normalized resource capacity inputs covering resource profiles, baseline calendars, working days, availability ratios, and resource-specific exceptions when the source provides them
- source/setup issue facts with blocking vs advisory severity
- source readiness derived only from source/setup conditions owned by the Integration Service

Contract rules:
- same logical input payload must produce the same payload digest, internal IDs, normalized ordering, and readiness result
- malformed or incomplete source input emits source/setup issue facts instead of warning/trust interpretations
- normalized output is planning-ready input owned by the Integration Service, not a draft planning output
- missing resource capacity-profile detail is preserved as normalized optional input and is classified later by Planning Engine as capacity-input readiness, not as an Integration-owned warning/trust lifecycle
- source sync and normalization never replace approved operating plan truth

Source artifact semantics:
- imported source artifacts remain a retained historical comparison baseline
- each normalized source snapshot is anchored to one artifact digest
- mappings remain Integration-owned cross-service references for downstream consumers
- downstream services may read this bundle, but may not mutate Integration-owned artifacts, mappings, or issue facts

## Planning Engine daily capacity baseline contract
The Planning Engine provides the EPIC-02 baseline capacity-output contract for downstream scheduling and later BFF composition. The baseline contract covers:
- a deterministic `capacity_snapshot_id` anchored to one normalized source snapshot and its modeled outputs
- capacity-input readiness with blocking vs advisory counts owned by Planning Engine rather than Workflow Orchestrator or BFF
- resource-scoped daily capacity outputs only
- resource summaries for modeled windows, assigned effort input, and total productive capacity
- capacity-input issues for missing calendars, availability ratios, working days, or resource capacity profiles

Daily capacity output contract:
- source_snapshot_id
- resource_id/resource_external_id/resource_display_name
- date
- working_day
- calendar_capacity_hours
- availability_ratio
- productive_capacity_hours
- active_assignment_count
- exception_reason when an exception overrides baseline capacity

Resource summary contract:
- resource_id/resource_external_id/resource_display_name
- assignment_input_count
- assigned_effort_hours
- window_start_date/window_end_date
- total_productive_capacity_hours
- days_modeled

Contract rules:
- Planning Engine outputs daily authoritative capacity truth only; weekly roll-up remains a BFF derivation for S01 — Portfolio Swimlane Home
- exceptions override baseline calendar-plus-availability capacity for the targeted resource/date only
- assignment input counts are descriptive source-input context and do not introduce scheduling placement logic
- this baseline does not generate schedule placement, draft deltas, warnings/trust interpretations, or approval state

## Planning Engine draft scheduling baseline contract
The Planning Engine provides the EPIC-03 baseline draft scheduling contract for downstream S01 — Portfolio Swimlane Home and D01 — Swimlane Task Drill-Down Drawer composition later in the stack. The baseline contract covers:
- deterministic draft scheduling driven by normalized work inputs plus authoritative daily capacity outputs
- dependency-respecting placement only
- task-level draft timing outputs
- allocation outputs by task, resource, and day
- partial and unschedulable draft outcomes as Planning Engine-owned draft signals only
- a planning-run execution record keyed by the Workflow Orchestrator handoff metadata

Draft schedule result contract:
- draft_schedule_id
- planning_run_id
- source_snapshot_id/source_artifact_id
- capacity_snapshot_id
- schedule_state as `scheduled`, `partially_schedulable`, or `unschedulable`
- task_schedules
- allocation_outputs
- schedule_issues

Draft task schedule contract:
- task_id/task_external_id/task_name
- project_id/project_external_id
- parent_task_id
- requested_start_date/requested_due_date
- scheduled_start_date/scheduled_end_date
- required_effort_hours/scheduled_effort_hours/unscheduled_effort_hours
- assigned_resource_ids
- predecessor_task_ids
- status as `scheduled`, `partially_scheduled`, or `unschedulable`

Allocation output contract:
- task_id/task_external_id
- resource_id/resource_external_id
- date
- allocated_hours

Planning-run execution record contract:
- planning_run_id
- workflow_instance_id
- planning_context_key
- source_snapshot_id/source_artifact_id
- attempt_number
- accepted_at
- capacity_snapshot_id
- draft_schedule_id
- draft_schedule_state

Contract rules:
- Planning Engine owns draft scheduling outputs only; no reviewable deltas or approval-state artifacts are created here
- dependency placement never allows a successor to begin before all predecessors are fully scheduled
- constrained capacity is resolved deterministically using stable task ordering and the authoritative daily capacity baseline
- partially schedulable and unschedulable outcomes remain draft planning outputs and issue facts only; warning/trust interpretation remains outside this service
- weekly roll-up remains BFF-owned derivation from daily authoritative outputs only
- S01 — Portfolio Swimlane Home and D01 — Swimlane Task Drill-Down Drawer payload shaping remain BFF-owned read composition only

## Planning Engine diagnostics fact baseline contract
The Planning Engine provides the EPIC-04 and EPIC-05 input-layer diagnostics contract for downstream consumers. The baseline contract covers:
- comparison-ready variance facts derived from draft scheduling outputs versus imported baseline dates
- criticality facts derived from dependency structure and draft timing pressure
- planning issue facts derived from draft schedule status, variance, and criticality conditions
- explicit comparison-context signaling when approved-plan comparison is not yet available in the current baseline

Planning diagnostics result contract:
- diagnostics_id
- planning_run_id
- draft_schedule_id
- source_snapshot_id/source_artifact_id
- capacity_snapshot_id
- comparison_context
- approved_comparison_available
- variance_facts
- criticality_facts
- planning_issue_facts

Current comparison-context rule:
- the current baseline emits `comparison_context = source_baseline_only`
- `approved_comparison_available = false` until an approved-plan comparison source is integrated later
- downstream consumers may treat these facts as comparison-ready inputs without inferring approved-plan drift from Planning Engine alone

Variance fact contract:
- task_id/task_external_id/task_name
- baseline_start_date/baseline_due_date
- scheduled_start_date/scheduled_end_date
- start_variance_days
- finish_variance_days
- slippage_detected
- unscheduled_effort_hours

Criticality fact contract:
- task_id/task_external_id/task_name
- direct_predecessor_count/direct_successor_count
- dependency_chain_depth
- downstream_dependency_count
- slack_days
- zero_slack
- blocked_by_unscheduled_predecessor
- critical

Planning issue fact contract:
- severity
- code
- message
- entity_type
- entity_id/entity_external_id

Contract rules:
- Planning Engine emits raw variance, criticality, and planning issue facts only; it does not interpret them into warnings or trust state
- source/setup issue facts remain Integration-owned and approval/activation issue facts remain Review & Approval-owned
- reviewable deltas are not created here even when facts are comparison-ready
- fact generation must be deterministic for identical normalized inputs and draft scheduling outputs

## Review & Approval issue-fact emission contract
The Review & Approval Service owns issue-fact emission for review, approval, connected-set, and activation conditions that belong to S04 — Delta Review and later Decision Support interpretation inputs. The emitted contract covers:
- review-context issue facts for acceptance validation and connected-set handling
- dependency-safe approval blocker facts
- connected-set-required facts
- activation-blocker facts
- activation outcome facts/signals
- current blocker evaluation over both persisted acceptance-selection state and explicit blocked isolated-acceptance attempts captured by Review & Approval, without treating read-only connected-set lookup as a blocker event

Review & Approval issue-fact contract:
- emitted_by_service
- context_scope
- fact_type
- review_context_id/planning_run_id/source_snapshot_id/approved_plan_id
- activation_id when the fact comes from activation evaluation
- severity
- code
- message
- entity_type/entity_id/entity_external_id
- related_delta_ids
- related_connected_set_id

Contract rules:
- Review & Approval emits issue facts/signals only; it does not create interpreted warning state, trust state, or warning grouping
- reviewable deltas, acceptance state, approved operating plan state, and activation business state remain distinct owned artifacts and are not replaced by emitted facts
- Decision Support may later consume these facts for S05 — Planning Warnings Workspace interpretation without moving warning lifecycle ownership into Review & Approval
- blocked isolated-acceptance attempts must remain traceable through deterministic issue-fact emission without mutating accepted selection state automatically
- safe acceptance cases must emit no false dependency-safe or connected-set-required blocker facts
- fact IDs and output ordering must remain deterministic for identical review context and activation inputs

## Decision Support warning/trust interpretation contract
The Decision Support Service owns the warning/trust interpretation lifecycle over authoritative issue facts from Integration Service, Planning Engine Service, and Review & Approval Service. The baseline contract covers:
- screen-scoped interpreted warning/trust state for S02 — Planning Setup, S03 — Resource Detail, S04 — Delta Review, and S05 — Planning Warnings Workspace
- setup blocker and setup warning interpretation from Integration-owned source/setup issue facts
- advisory warning and trust-limited interpretation from Planning Engine-owned planning issue facts
- dependency-safe review blocker and activation blocker interpretation from Review & Approval-owned issue facts
- stable provenance from interpreted signals back to raw issue facts

Decision Support warning/trust state contract:
- interpretation_id
- screen_id/planning_context_key/source_snapshot_id
- lifecycle_state
- active/advisory/blocking counts
- warning/trust counts
- trust-limited count
- total input fact count
- interpreted signal count
- signals

Interpreted signal contract:
- signal_id
- signal_type as `warning` or `trust`
- severity
- advisory/blocking
- interpretation_category
- lifecycle_state
- code/message
- source_issue_service
- source_fact_id/source_fact_type/source_fact_severity
- entity_type/entity_id/entity_external_id

Interpretation rules:
- Decision Support is the only owner of warning/trust interpretation lifecycle; emitting services continue to own raw issue facts
- warnings are advisory by default except true setup blockers, dependency-safe review blockers, and explicit activation blockers
- Planning Engine issue facts remain advisory warning or trust-limited interpretation inputs only
- activation outcome facts may be consumed for provenance but do not create active warning/trust signals by default
- S02 composition may continue to use Integration and Planning Engine readiness as the runnable gate even when setup-related warning/trust state is available separately

## Decision Support recommendation context contract
The Decision Support Service owns deterministic recommendation generation, ranking, persistence, and freshness state for S03 — Resource Detail. The baseline contract now covers:
- resource-scoped recommendation context keyed by resource, planning context, and source snapshot
- deterministic candidate generation from Planning Engine draft scheduling and diagnostic outputs without mutating draft or approved plan state
- stable recommendation candidate IDs and final ranking state
- approved MVP action families only: `rechunk`, `move_defer`, `reassignment`, and `date_extension`
- freshness and availability state including explicit `no_actionable_recommendations` handling
- recommendation-origin context for later S04 — Delta Review handoff without turning S04 — Delta Review into a recommendation-owning screen

Recommendation context contract:
- context_id
- resource_id/resource_external_id
- planning_context_key/source_snapshot_id
- state
- freshness_status
- actionable recommendation count
- total recommendation count
- recommendations

Recommendation candidate contract:
- recommendation_id
- title/summary/rationale/effect_summary
- action_family
- priority_rank
- ranking_score
- ranking_policy
- disruption_score
- handoff_overhead_score
- requires_review
- affected_task_ids/affected_task_external_ids
- origin_context
- trigger_issue_fact_ids

Contract rules:
- Decision Support remains the owner of recommendation generation, ranking, and freshness semantics; the BFF consumes this context only
- deterministic ranking uses the locked tie-break order after equal ranking score:
  - lower disruption / blast radius
  - lower handoff overhead
  - action family order: `rechunk` → `move_defer` → `reassignment` → `date_extension`
  - stable internal candidate ID
- unsafe or disallowed candidates are excluded rather than surfaced as safe recommendations
- S03 may display recommendation candidates even when trust-limited warning context is present, but trust-affected candidates must be flagged rather than suppressed by default
- S04 may consume recommendation-origin context later for downstream review context, but recommendation ownership remains in Decision Support and S04 does not become a recommendation screen
- this slice does not introduce direct plan application, recommendation remediation workflows, or alternative recommendation ownership outside Decision Support

## S01 and D01 composed read contract
The API Gateway / BFF owns the first stable S01 — Portfolio Swimlane Home and D01 — Swimlane Task Drill-Down Drawer view-model composition baseline. The composed contract covers:
- S01 portfolio swimlane read composition from Planning Engine daily capacity, draft scheduling, and diagnostics outputs
- weekly roll-up derived in the BFF from composed daily swimlane segments only
- ghost/not-fully-placed visibility projected from Planning Engine draft task status and unscheduled effort without inventing new scheduling placements
- overload/free-capacity indicators projected from daily authoritative capacity versus daily draft allocation
- D01 drill-down projection for a selected swimlane resource/date/week/task context

S01 composed view-model contract:
- screen/query context metadata
- view state including `ready`, `indicator_present`, `no_data`, and `unavailable`
- portfolio summary for planning run, draft schedule, capacity snapshot, and diagnostics context
- daily swimlanes by resource lane
- lane-level weekly roll-ups derived from daily segments only
- indicator summary for movement, risk, ghost visibility, overload, and free-capacity presence
- unavailable-state banner contract that routes back to S02 — Planning Setup when no runnable plan exists in current Planning Engine reads

Daily swimlane segment contract:
- date/week_start_date
- productive_capacity_hours
- allocated_hours
- utilization_ratio
- overload_hours/free_capacity_hours
- active_assignment_count
- task_refs with ghost, movement, and risk indicator flags

D01 composed view-model contract:
- drawer/query context metadata
- view state including `ready`, `indicator_present`, `empty`, `no_data`, and `unavailable`
- selected segment context
- task detail records with requested/scheduled timing, context allocations, ghost visibility, summarized movement and risk indicators derived from variance/criticality/planning issue facts, and planning issue facts
- segment summary for selected task count, allocated hours, ghost visibility, and indicator presence

Composition rules:
- weekly roll-up is derived in the BFF from daily swimlane segments only; the Planning Engine remains the owner of daily authoritative planning outputs
- BFF does not compute scheduling, capacity, criticality, or warning/trust interpretation logic
- S01 remains visibility/navigation only and does not become a scheduling, recommendation, or approval surface
- D01 remains an embedded drill-down surface only and does not become an editor or approval surface
- ghost visibility is a screen-facing projection of Planning Engine-owned partially placed or unschedulable draft work, not a new business artifact

## S03 composed read contract
The API Gateway / BFF owns the first stable S03 — Resource Detail view-model composition baseline. The composed contract covers:
- single-resource summary projection from Planning Engine daily capacity, draft scheduling, and diagnostics outputs
- a workload timeline/time-bucket diagnostic view from Planning Engine daily authoritative outputs only
- a distinct assigned work / queue view for the selected resource
- resource-scoped warning/trust context from Decision Support interpreted signals
- recommendation context from Decision Support recommendation outputs without moving recommendation ownership into the BFF
- navigation context back to S01 — Portfolio Swimlane Home and onward to S04 — Delta Review or S05 — Planning Warnings Workspace where relevant

S03 composed view-model contract:
- screen/query context metadata
- view state including `ready`, `overload_focused`, `underutilized`, `warning_heavy`, `no_actionable_recommendation`, `loading`, `access_restricted`, `no_data`, and `unavailable`
- resource summary for utilization, ghost load, indicator counts, and warning/trust counts
- workload timeline projection with daily capacity, allocation, utilization, ghost visibility, and task refs
- assigned work / queue projection with task timing, allocation, ghost visibility, and planning indicators
- recommendation context including availability/freshness state, recommendation candidates, effect summaries, recommendation-origin context, trust-affected flags, and review-handoff metadata
- warning/trust context including advisory/trust-limited counts and resource-relevant interpreted signals
- navigation context for return, review handoff, and warning review

Composition rules:
- BFF does not compute capacity, scheduling, diagnostics, warning interpretation, or recommendation ranking logic
- S03 remains a focused single-resource diagnostic workspace and does not become a setup, approval, or direct plan-application surface
- workload timeline and assigned work / queue remain distinct screen sections rather than a merged surface
- Planning Engine remains the owner of planning outputs and Decision Support remains the owner of warning/trust interpretation and recommendation outputs
- trust-limited warning context may flag recommendation visibility, but recommendation candidates remain visible by default unless an authoritative downstream contract says otherwise

## S04 and M01 composed contract
The API Gateway / BFF owns the first stable S04 — Delta Review and M01 — Connected Change Set Modal composition baseline. The composed contract covers:
- draft-vs-approved review context projection from Review & Approval reviewable deltas
- grouped and item-level delta review shaping for S04 only
- acceptance-state display and explicit selection/deselection command routing through Review & Approval only
- activation-state display and explicit activation command routing through Review & Approval only
- explicit activation entry-point shaping after acceptance without moving activation business truth or downstream workflow ownership into the BFF
- blocked isolated-acceptance projection with M01 launch context when connected-set handling is required
- already-available warning/trust context from Decision Support and recommendation-origin context from Review & Approval-owned delta items
- lightweight access-restricted and no-data state shaping without moving acceptance or delta ownership into the BFF

S04 composed view-model contract:
- screen/query context metadata including origin screen, origin scope, and focused delta when present
- view state including `ready`, `no_deltas`, `blocked_isolated_acceptance`, `warning_heavy`, `loading`, `no_data`, and `access_restricted`
- review context status including review context IDs and review stage summary
- delta summary counts for total, selected, blocked, grouped, and recommendation-linked deltas
- grouped delta review records with item-level attribute changes, dependency indicators, selected state, connected-set entry points, recommendation-origin context, and advisory warning/trust context
- acceptance state summary for selected counts, blocked counts, and screen-facing review-stage status
- activation summary for activation status, approved-plan before/after references, business-rule blockers, outcome state, and downstream workflow status metadata when Orchestrator state is available
- blocked-acceptance projection for a focused blocked delta with M01 launch metadata
- warning/trust context limited to already-available interpreted Decision Support state
- navigation context back to the origin workflow and onward to S05 — Planning Warnings Workspace when review confidence needs deeper warning review

M01 composed view-model contract:
- modal/query context metadata for review context, requested delta, and planning context
- view state including `ready`, `no_modal_required`, and `access_restricted`
- requested delta summary
- blocking reason for unsafe isolated acceptance
- connected-set payload with minimal dependency-safe membership, member items, and selected-member counts
- connected-set select/deselect action availability
- navigation context back into S04 — Delta Review

Composition rules:
- BFF does not create reviewable deltas, acceptance state, connected-change-set membership, activation business state, or downstream activation workflow state
- S04 remains the formal review workspace and may expose the explicit activation entry point after acceptance, but Review & Approval owns activation business command/state and Workflow Orchestrator owns downstream async workflow state
- S04 may display activation admission/result metadata, route an explicit activation command, and project downstream activation workflow state from Workflow Orchestrator, but it does not own approved-plan mutation rules or downstream execution lifecycle
- task-level acceptance remains primary; group-level handling is exposed only as a convenience wrapper through M01 when dependency-safe grouped acceptance is required
- warnings on S04 remain advisory by default unless Review & Approval exposes an explicit separate blocker such as dependency-safe or activation blocking
- M01 remains review/approval-only connected-set handling and does not become a general editor, recommendation surface, or warning workspace

## S05 composed read contract
The API Gateway / BFF owns the first stable S05 — Planning Warnings Workspace view-model composition baseline. The composed contract covers:
- warning/trust workspace payload projection from Decision Support Service interpreted warning/trust state
- one-list presentation that keeps blocking warnings, advisory warnings, and trust-limited interpretations in a single workspace with labels, counts, and filters
- default grouping by affected workflow with scoped-entry defaults when S05 is opened from S01 — Portfolio Swimlane Home, S02 — Planning Setup, S03 — Resource Detail, or S04 — Delta Review
- affected-scope navigation context and return-navigation context back to the owning workflow
- lightweight loading and access-restricted state shaping without moving warning/trust interpretation into the BFF

S05 composed view-model contract:
- screen/query context metadata including origin screen and origin scope
- view state including `ready`, `no_warnings`, `warning_heavy`, `trust_limited`, `loading`, and `access_restricted`
- workspace summary counts for blocking, advisory, trust-limited, total, and grouped warning state
- filter state with default grouping, available filter options, active filters, and scoped-entry defaults
- group summaries by affected workflow
- warning items with blocking/advisory/trust-limited classification, affected workflow and scope, trust guidance, and navigation target metadata
- trust guidance summary
- return-navigation and empty-state metadata

Composition rules:
- Decision Support Service remains the only owner of warning/trust interpretation lifecycle and classification
- BFF may derive affected-workflow grouping, scoped filtering, and navigation context from authoritative interpreted signals only
- S05 stays a dedicated review-and-navigation workspace and does not become remediation, scheduling, approval, or recommendation logic
- origin screen and scope act as initial filters only; S05 does not create separate top-level workflow workspaces
- blocking versus advisory visibility is a screen-facing presentation rule only and does not move blocker ownership out of emitting services or Decision Support interpretation state

## Major user-facing command flows
- S01 — Portfolio Swimlane Home → get S01 — Portfolio Swimlane Home data → BFF → Planning Engine
- D01 — Swimlane Task Drill-Down Drawer → get D01 — Swimlane Task Drill-Down Drawer data → BFF → Planning Engine
- S02 — Planning Setup → start import/sync → BFF → Workflow Orchestrator → Integration
- S02 — Planning Setup → start planning run → BFF → Workflow Orchestrator → Planning Engine
- S02 — Planning Setup → get planning-run status → BFF → Workflow Orchestrator
- S02 — Planning Setup → get setup warning/trust state → BFF → Decision Support
- S03 — Resource Detail → get S03 — Resource Detail data → BFF → Planning Engine, Decision Support
- S03 — Resource Detail → get/refresh recommendations → BFF → Decision Support
- S04 — Delta Review → get review warning/trust state → BFF → Decision Support
- S04 — Delta Review → get deltas → BFF → Review & Approval
- S04 — Delta Review → record acceptance → BFF → Review & Approval
- M01 — Connected Change Set Modal → resolve connected set → BFF → Review & Approval
- S04 — Delta Review → activate approved changes → BFF → Review & Approval, then async downstream via Workflow Orchestrator
- S05 — Planning Warnings Workspace → get S05 — Planning Warnings Workspace data → BFF → Decision Support

## Async workflow boundaries
Must be async:
- import/sync
- planning run
- recommendation precompute when heavy
- downstream recomputation after activation
- bounded external write-back/status sync

May remain sync:
- S01 — Portfolio Swimlane Home retrieval
- D01 — Swimlane Task Drill-Down Drawer retrieval
- S05 — Planning Warnings Workspace retrieval
- S04 — Delta Review retrieval
- S04 — Delta Review warning/trust state retrieval
- connected-set retrieval
- acceptance selection
- recommendation retrieval when already precomputed
- S02 — Planning Setup readiness retrieval
- S02 — Planning Setup planning-run status retrieval
- S02 — Planning Setup warning/trust state retrieval
- swimlane and screen view retrieval
