"""Review & Approval delta generation and issue-fact emission baseline."""

from dataclasses import replace
import hashlib
from typing import Dict, Iterable, List, Optional, Set, Tuple

from services.planning_engine_service import PlanningRunExecutionResult

from .contracts import (
    ACCEPTANCE_SELECTION_ACTION_DESELECT,
    ACCEPTANCE_SELECTION_ACTION_SELECT,
    ACCEPTANCE_SELECTION_SCOPE_CONNECTED_CHANGE_SET,
    ACCEPTANCE_SELECTION_SCOPE_DELTA_ITEM,
    ACCEPTANCE_SELECTION_STATUS_APPLIED,
    ACCEPTANCE_SELECTION_STATUS_BLOCKED,
    ACTIVATION_STATUS_ACTIVATED,
    ACTIVATION_STATUS_BLOCKED,
    ACTIVATION_WORKFLOW_STATE_NOT_STARTED,
    DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS,
    DELTA_SCOPE_ATTRIBUTE_MILESTONE_DATE,
    DELTA_SCOPE_ATTRIBUTE_PROJECT_FINISH_DATE,
    DELTA_SCOPE_ATTRIBUTE_TASK_DUE_DATE,
    DELTA_SCOPE_ATTRIBUTE_TASK_START_DATE,
    ISSUE_FACT_SCOPE_ACTIVATION,
    ISSUE_FACT_SCOPE_REVIEW_CONTEXT,
    ISSUE_FACT_SEVERITY_BLOCKING,
    ISSUE_FACT_SEVERITY_INFO,
    ISSUE_FACT_TYPE_ACTIVATION_BLOCKER,
    ISSUE_FACT_TYPE_ACTIVATION_OUTCOME,
    ISSUE_FACT_TYPE_CONNECTED_SET_REQUIRED,
    ISSUE_FACT_TYPE_DEPENDENCY_SAFE_BLOCKER,
    REVIEW_COMPARISON_CONTEXT_DRAFT_VS_APPROVED,
    REVIEW_DELTA_ENTITY_TYPE_MILESTONE,
    REVIEW_DELTA_ENTITY_TYPE_PROJECT,
    REVIEW_DELTA_ENTITY_TYPE_TASK,
    AcceptanceSelectionResult,
    ActivationBusinessRuleBlocker,
    ActivationCommandResult,
    ActivationDownstreamHandoff,
    ActivationOutcome,
    ActivationState,
    ActivationWriteBackTarget,
    ApprovedOperatingPlanSnapshot,
    ApprovedPlanProjectRecord,
    ApprovedPlanTaskRecord,
    ConnectedChangeSet,
    ConnectedChangeSetResolution,
    RecommendationOriginReference,
    ReviewApprovalIssueFact,
    ReviewApprovalIssueFactEmission,
    ReviewContextState,
    ReviewableDeltaAttributeChange,
    ReviewableDeltaItem,
)
from .repository import InMemoryReviewApprovalRepository


SERVICE_NAME = "Review & Approval Service"
WORKFLOW_ORCHESTRATOR_SERVICE_NAME = "Workflow Orchestrator Service"
WRITE_BACK_ACTION_UPDATE_TASK_FIELDS = "update_task_fields"
WRITE_BACK_ACTION_UPDATE_PROJECT_FIELDS = "update_project_fields"
WRITE_BACK_FIELD_ORDER = (
    DELTA_SCOPE_ATTRIBUTE_TASK_START_DATE,
    DELTA_SCOPE_ATTRIBUTE_TASK_DUE_DATE,
    DELTA_SCOPE_ATTRIBUTE_MILESTONE_DATE,
    DELTA_SCOPE_ATTRIBUTE_PROJECT_FINISH_DATE,
    DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS,
)
ApprovedTaskKey = Tuple[str, str, str]
RecommendationRefKey = Tuple[Optional[str], str]


class ReviewApprovalService:
    """Owns reviewable deltas, connected-set handling, and related issue facts."""

    def __init__(
        self,
        repository: Optional[InMemoryReviewApprovalRepository] = None,
    ) -> None:
        self._repository = repository or InMemoryReviewApprovalRepository()

    def generate_reviewable_delta_set(
        self,
        execution_result: PlanningRunExecutionResult,
        approved_plan_snapshot: ApprovedOperatingPlanSnapshot,
        recommendation_origin_refs: Optional[List[RecommendationOriginReference]] = None,
    ) -> ReviewContextState:
        review_context = _build_review_context_state(
            execution_result=execution_result,
            approved_plan_snapshot=approved_plan_snapshot,
            recommendation_origin_refs=recommendation_origin_refs or [],
        )
        self._repository.save_review_context(review_context)
        self._repository.save_approved_plan_snapshot(approved_plan_snapshot)
        if self._repository.get_approved_plan_snapshot(current=True) is None:
            self._repository.save_approved_plan_snapshot(
                approved_plan_snapshot,
                set_current=True,
            )
        return review_context

    def get_review_context(
        self, review_context_id: Optional[str] = None
    ) -> Optional[ReviewContextState]:
        return self._repository.get_review_context(review_context_id=review_context_id)

    def get_approved_operating_plan_snapshot(
        self,
        approved_plan_id: Optional[str] = None,
        *,
        current: bool = False,
    ) -> Optional[ApprovedOperatingPlanSnapshot]:
        return self._repository.get_approved_plan_snapshot(
            approved_plan_id=approved_plan_id,
            current=current,
        )

    def resolve_connected_change_set(
        self,
        requested_delta_id: str,
        review_context_id: Optional[str] = None,
    ) -> ConnectedChangeSetResolution:
        review_context = self._repository.get_review_context(review_context_id=review_context_id)
        if review_context is None:
            raise ValueError("A saved review context is required before resolving a connected set.")

        resolution = _build_connected_set_resolution(
            review_context=review_context,
            requested_delta_id=requested_delta_id,
        )
        self._repository.save_connected_set_resolution(resolution)
        return resolution

    def get_connected_set_resolution(
        self,
        review_context_id: Optional[str] = None,
        requested_delta_id: Optional[str] = None,
    ) -> Optional[ConnectedChangeSetResolution]:
        return self._repository.get_connected_set_resolution(
            review_context_id=review_context_id,
            requested_delta_id=requested_delta_id,
        )

    def record_delta_acceptance_selection(
        self,
        review_context_id: str,
        delta_id: str,
        selected: bool,
    ) -> AcceptanceSelectionResult:
        review_context = self._repository.get_review_context(review_context_id=review_context_id)
        if review_context is None:
            raise ValueError("A saved review context is required before recording acceptance.")

        requested_delta = _get_review_delta(review_context=review_context, delta_id=delta_id)
        action = (
            ACCEPTANCE_SELECTION_ACTION_SELECT
            if selected
            else ACCEPTANCE_SELECTION_ACTION_DESELECT
        )
        if requested_delta.connected_set_id is not None:
            resolution = _build_connected_set_resolution(
                review_context=review_context,
                requested_delta_id=delta_id,
            )
            self._repository.save_connected_set_resolution(resolution)
            self._repository.save_blocked_acceptance_attempt(resolution)
            self.emit_issue_facts(
                review_context=review_context,
                blocked_acceptance_resolutions=self._repository.list_blocked_acceptance_attempts(
                    review_context_id=review_context.review_context_id
                ),
            )
            return _build_acceptance_selection_result(
                review_context=review_context,
                requested_delta_id=delta_id,
                selection_scope=ACCEPTANCE_SELECTION_SCOPE_DELTA_ITEM,
                connected_set_id=requested_delta.connected_set_id,
                action=action,
                status=ACCEPTANCE_SELECTION_STATUS_BLOCKED,
                connected_set_resolution=resolution,
            )

        updated_review_context = _apply_acceptance_selection(
            review_context=review_context,
            selected_delta_ids={delta_id},
            selected=selected,
        )
        self._repository.save_review_context(updated_review_context)
        self._repository.clear_blocked_acceptance_attempts(
            review_context_id=updated_review_context.review_context_id,
            requested_delta_ids=[delta_id],
        )
        self.emit_issue_facts(
            review_context=updated_review_context,
            blocked_acceptance_resolutions=self._repository.list_blocked_acceptance_attempts(
                review_context_id=updated_review_context.review_context_id
            ),
        )
        return _build_acceptance_selection_result(
            review_context=updated_review_context,
            requested_delta_id=delta_id,
            selection_scope=ACCEPTANCE_SELECTION_SCOPE_DELTA_ITEM,
            connected_set_id=None,
            action=action,
            status=ACCEPTANCE_SELECTION_STATUS_APPLIED,
            connected_set_resolution=None,
        )

    def record_connected_set_acceptance_selection(
        self,
        review_context_id: str,
        requested_delta_id: str,
        selected: bool,
    ) -> AcceptanceSelectionResult:
        review_context = self._repository.get_review_context(review_context_id=review_context_id)
        if review_context is None:
            raise ValueError("A saved review context is required before recording acceptance.")

        resolution = _build_connected_set_resolution(
            review_context=review_context,
            requested_delta_id=requested_delta_id,
        )
        self._repository.save_connected_set_resolution(resolution)
        if resolution.connected_change_set is None:
            raise ValueError("Requested delta does not require connected-set handling.")

        updated_review_context = _apply_acceptance_selection(
            review_context=review_context,
            selected_delta_ids=set(resolution.connected_change_set.member_delta_ids),
            selected=selected,
        )
        self._repository.save_review_context(updated_review_context)
        self._repository.clear_blocked_acceptance_attempts(
            review_context_id=updated_review_context.review_context_id,
            requested_delta_ids=list(resolution.connected_change_set.member_delta_ids),
        )
        self.emit_issue_facts(
            review_context=updated_review_context,
            blocked_acceptance_resolutions=self._repository.list_blocked_acceptance_attempts(
                review_context_id=updated_review_context.review_context_id
            ),
        )
        return _build_acceptance_selection_result(
            review_context=updated_review_context,
            requested_delta_id=requested_delta_id,
            selection_scope=ACCEPTANCE_SELECTION_SCOPE_CONNECTED_CHANGE_SET,
            connected_set_id=resolution.connected_change_set.connected_set_id,
            action=(
                ACCEPTANCE_SELECTION_ACTION_SELECT
                if selected
                else ACCEPTANCE_SELECTION_ACTION_DESELECT
            ),
            status=ACCEPTANCE_SELECTION_STATUS_APPLIED,
            connected_set_resolution=resolution,
        )

    def get_current_review_issue_fact_emission(
        self,
        review_context_id: str,
    ) -> ReviewApprovalIssueFactEmission:
        review_context = self._repository.get_review_context(review_context_id=review_context_id)
        if review_context is None:
            raise ValueError("A saved review context is required before reading review issue facts.")
        return self.emit_issue_facts(
            review_context=review_context,
            blocked_acceptance_resolutions=self._repository.list_blocked_acceptance_attempts(
                review_context_id=review_context_id
            ),
        )

    def emit_issue_facts(
        self,
        review_context: ReviewContextState,
        activation_state: Optional[ActivationState] = None,
        blocked_acceptance_resolutions: Optional[List[ConnectedChangeSetResolution]] = None,
    ) -> ReviewApprovalIssueFactEmission:
        issue_facts = _build_issue_facts(
            review_context=review_context,
            activation_state=activation_state,
            blocked_acceptance_resolutions=blocked_acceptance_resolutions or [],
        )
        issue_fact_fingerprint = ",".join(fact.fact_id for fact in issue_facts) or "no-facts"
        emission = ReviewApprovalIssueFactEmission(
            emission_id=_stable_id(
                "review-approval-issue-emission",
                review_context.review_context_id,
                activation_state.activation_id if activation_state is not None else "none",
                issue_fact_fingerprint,
            ),
            review_context_id=review_context.review_context_id,
            planning_run_id=review_context.planning_run_id,
            source_snapshot_id=review_context.source_snapshot_id,
            approved_plan_id=review_context.approved_plan_id,
            activation_id=None if activation_state is None else activation_state.activation_id,
            blocking_fact_count=len(
                [
                    fact
                    for fact in issue_facts
                    if fact.severity == ISSUE_FACT_SEVERITY_BLOCKING
                ]
            ),
            informational_fact_count=len(
                [
                    fact
                    for fact in issue_facts
                    if fact.severity == ISSUE_FACT_SEVERITY_INFO
                ]
            ),
            total_fact_count=len(issue_facts),
            issue_facts=issue_facts,
        )
        self._repository.save_issue_fact_emission(emission)
        return emission

    def get_issue_fact_emission(
        self,
        review_context_id: Optional[str] = None,
        activation_id: Optional[str] = None,
    ) -> Optional[ReviewApprovalIssueFactEmission]:
        return self._repository.get_issue_fact_emission(
            review_context_id=review_context_id,
            activation_id=activation_id,
        )

    def get_activation_state(
        self,
        review_context_id: Optional[str] = None,
        activation_id: Optional[str] = None,
    ) -> Optional[ActivationState]:
        return self._repository.get_activation_state(
            review_context_id=review_context_id,
            activation_id=activation_id,
        )

    def activate_approved_changes(
        self,
        review_context_id: str,
        requested_by: str,
        requested_at: str,
    ) -> ActivationCommandResult:
        review_context = self._repository.get_review_context(review_context_id=review_context_id)
        if review_context is None:
            raise ValueError("A saved review context is required before activation.")

        selected_delta_ids = sorted(
            [
                delta.delta_id
                for delta in review_context.delta_items
                if delta.selected_for_acceptance
            ]
        )
        existing_activation_state = self._repository.get_activation_state(
            review_context_id=review_context.review_context_id
        )
        if (
            existing_activation_state is not None
            and existing_activation_state.status == ACTIVATION_STATUS_ACTIVATED
            and existing_activation_state.selected_delta_ids == selected_delta_ids
        ):
            return _build_activation_command_result(
                review_context=review_context,
                activation_state=existing_activation_state,
                resulting_approved_plan_snapshot=self._repository.get_approved_plan_snapshot(
                    approved_plan_id=existing_activation_state.approved_plan_id_after
                ),
                reused_existing=True,
            )

        current_approved_plan = self._repository.get_approved_plan_snapshot(current=True)
        blocked_acceptance_resolutions = self._repository.list_blocked_acceptance_attempts(
            review_context_id=review_context.review_context_id
        )
        blockers = _build_activation_business_rule_blockers(
            review_context=review_context,
            current_approved_plan=current_approved_plan,
            blocked_acceptance_resolutions=blocked_acceptance_resolutions,
        )
        if blockers:
            activation_state = ActivationState(
                activation_id=_stable_id(
                    "activation",
                    review_context.review_context_id,
                    current_approved_plan.approved_plan_id
                    if current_approved_plan is not None
                    else "no-current-approved-plan",
                    ",".join(selected_delta_ids) or "no-selected-deltas",
                    ",".join(blocker.code for blocker in blockers),
                ),
                status=ACTIVATION_STATUS_BLOCKED,
                business_rule_blockers=blockers,
                outcome=None,
                review_context_id=review_context.review_context_id,
                approved_plan_id_before=(
                    None if current_approved_plan is None else current_approved_plan.approved_plan_id
                ),
                approved_plan_id_after=None,
                requested_by=requested_by,
                requested_at=requested_at,
                selected_delta_ids=selected_delta_ids,
            )
            self._repository.save_activation_state(activation_state)
            self.emit_issue_facts(
                review_context=review_context,
                activation_state=activation_state,
                blocked_acceptance_resolutions=blocked_acceptance_resolutions,
            )
            return _build_activation_command_result(
                review_context=review_context,
                activation_state=activation_state,
                resulting_approved_plan_snapshot=None,
                reused_existing=False,
            )

        assert current_approved_plan is not None
        resulting_approved_plan_snapshot = _build_activated_approved_plan_snapshot(
            review_context=review_context,
            current_approved_plan=current_approved_plan,
            selected_delta_ids=selected_delta_ids,
        )
        self._repository.save_approved_plan_snapshot(
            resulting_approved_plan_snapshot,
            set_current=True,
        )
        activation_state = ActivationState(
            activation_id=_stable_id(
                "activation",
                review_context.review_context_id,
                current_approved_plan.approved_plan_id,
                ",".join(selected_delta_ids),
            ),
            status=ACTIVATION_STATUS_ACTIVATED,
            business_rule_blockers=[],
            outcome=ActivationOutcome(
                code="activation_completed",
                message="Accepted changes were activated into the approved operating plan.",
                activated_delta_ids=selected_delta_ids,
                resulting_approved_plan_id=resulting_approved_plan_snapshot.approved_plan_id,
            ),
            review_context_id=review_context.review_context_id,
            approved_plan_id_before=current_approved_plan.approved_plan_id,
            approved_plan_id_after=resulting_approved_plan_snapshot.approved_plan_id,
            requested_by=requested_by,
            requested_at=requested_at,
            selected_delta_ids=selected_delta_ids,
        )
        self._repository.save_activation_state(activation_state)
        self.emit_issue_facts(
            review_context=review_context,
            activation_state=activation_state,
            blocked_acceptance_resolutions=blocked_acceptance_resolutions,
        )
        return _build_activation_command_result(
            review_context=review_context,
            activation_state=activation_state,
            resulting_approved_plan_snapshot=resulting_approved_plan_snapshot,
            reused_existing=False,
        )


def _build_review_context_state(
    execution_result: PlanningRunExecutionResult,
    approved_plan_snapshot: ApprovedOperatingPlanSnapshot,
    recommendation_origin_refs: List[RecommendationOriginReference],
) -> ReviewContextState:
    execution_record = execution_result.execution_record
    draft_schedule_result = execution_result.draft_schedule_result
    review_context_id = _stable_id(
        "review-context",
        execution_record.planning_run_id,
        draft_schedule_result.draft_schedule_id,
        execution_record.source_snapshot_id,
        approved_plan_snapshot.approved_plan_id,
    )
    resource_external_ids_by_id = {
        summary.resource_id: summary.resource_external_id
        for summary in execution_result.capacity_result.resource_summaries
    }
    recommendation_refs_by_task_external_id = _index_recommendation_origin_refs(
        recommendation_origin_refs
    )
    approved_tasks_by_key = _index_approved_tasks(approved_plan_snapshot)
    task_schedules = sorted(
        draft_schedule_result.task_schedules,
        key=lambda item: (item.project_external_id, item.task_external_id, item.task_id),
    )
    task_external_id_counts = _count_task_external_ids(task_schedules)

    delta_entries: List[Dict[str, object]] = []
    task_delta_id_by_task_id: Dict[str, str] = {}
    for task_schedule in task_schedules:
        approved_task = _find_approved_task(
            approved_tasks_by_key=approved_tasks_by_key,
            task_id=task_schedule.task_id,
            project_external_id=task_schedule.project_external_id,
            task_external_id=task_schedule.task_external_id,
        )
        if approved_task is None:
            continue

        attribute_changes = _build_task_attribute_changes(
            task_schedule=task_schedule,
            approved_task=approved_task,
            resource_external_ids_by_id=resource_external_ids_by_id,
        )
        if not attribute_changes:
            continue

        entity_type = (
            REVIEW_DELTA_ENTITY_TYPE_MILESTONE
            if approved_task.item_type == REVIEW_DELTA_ENTITY_TYPE_MILESTONE
            else REVIEW_DELTA_ENTITY_TYPE_TASK
        )
        delta_id = _stable_id(
            "review-delta",
            review_context_id,
            entity_type,
            task_schedule.task_id,
            _attribute_change_fingerprint(attribute_changes),
        )
        delta_entries.append(
            {
                "delta_id": delta_id,
                "entity_type": entity_type,
                "entity_id": task_schedule.task_id,
                "entity_external_id": task_schedule.task_external_id,
                "entity_name": task_schedule.task_name,
                "task_id": task_schedule.task_id,
                "task_external_id": task_schedule.task_external_id,
                "task_name": task_schedule.task_name,
                "project_id": task_schedule.project_id,
                "project_external_id": task_schedule.project_external_id,
                "dependency_task_ids": sorted(task_schedule.predecessor_task_ids),
                "dependency_delta_ids": [],
                "connected_set_id": None,
                "selected_for_acceptance": False,
                "delta_scope_attributes": [
                    attribute_change.attribute_name
                    for attribute_change in attribute_changes
                ],
                "attribute_changes": attribute_changes,
                "recommendation_origin_refs": list(
                    _get_recommendation_origin_refs(
                        recommendation_refs_by_key=recommendation_refs_by_task_external_id,
                        project_external_id=task_schedule.project_external_id,
                        task_external_id=task_schedule.task_external_id,
                        task_external_id_counts=task_external_id_counts,
                    )
                ),
            }
        )
        task_delta_id_by_task_id[task_schedule.task_id] = delta_id

    project_finish_dates = _build_project_finish_dates(task_schedules)
    for approved_project in sorted(
        approved_plan_snapshot.projects,
        key=lambda item: (item.project_external_id, item.project_id or ""),
    ):
        draft_project_id, draft_finish_date = _find_draft_project_match(
            project_finish_dates=project_finish_dates,
            project_id=approved_project.project_id,
            project_external_id=approved_project.project_external_id,
        )
        if approved_project.finish_date == draft_finish_date:
            continue

        attribute_changes = [
            ReviewableDeltaAttributeChange(
                attribute_name=DELTA_SCOPE_ATTRIBUTE_PROJECT_FINISH_DATE,
                before_value=approved_project.finish_date,
                after_value=draft_finish_date,
            )
        ]
        delta_entries.append(
            {
                "delta_id": _stable_id(
                    "review-delta",
                    review_context_id,
                    REVIEW_DELTA_ENTITY_TYPE_PROJECT,
                    (
                        approved_project.project_id
                        or draft_project_id
                        or approved_project.project_external_id
                    ),
                    _attribute_change_fingerprint(attribute_changes),
                ),
                "entity_type": REVIEW_DELTA_ENTITY_TYPE_PROJECT,
                "entity_id": (
                    approved_project.project_id
                    or draft_project_id
                    or approved_project.project_external_id
                ),
                "entity_external_id": approved_project.project_external_id,
                "entity_name": approved_project.project_name,
                "task_id": None,
                "task_external_id": None,
                "task_name": None,
                "project_id": approved_project.project_id or draft_project_id,
                "project_external_id": approved_project.project_external_id,
                "dependency_task_ids": [],
                "dependency_delta_ids": [],
                "connected_set_id": None,
                "selected_for_acceptance": False,
                "delta_scope_attributes": [DELTA_SCOPE_ATTRIBUTE_PROJECT_FINISH_DATE],
                "attribute_changes": attribute_changes,
                "recommendation_origin_refs": [],
            }
        )

    _attach_dependency_delta_ids(
        delta_entries=delta_entries,
        task_delta_id_by_task_id=task_delta_id_by_task_id,
        task_schedules=task_schedules,
    )
    connected_change_sets = _build_connected_change_sets(
        review_context_id=review_context_id,
        delta_entries=delta_entries,
    )

    delta_items = [
        ReviewableDeltaItem(
            delta_id=entry["delta_id"],
            entity_type=entry["entity_type"],
            entity_id=entry["entity_id"],
            entity_external_id=entry["entity_external_id"],
            entity_name=entry["entity_name"],
            dependency_delta_ids=entry["dependency_delta_ids"],
            connected_set_id=entry["connected_set_id"],
            selected_for_acceptance=entry["selected_for_acceptance"],
            task_id=entry["task_id"],
            task_external_id=entry["task_external_id"],
            task_name=entry["task_name"],
            project_id=entry["project_id"],
            project_external_id=entry["project_external_id"],
            delta_scope_attributes=entry["delta_scope_attributes"],
            attribute_changes=entry["attribute_changes"],
            recommendation_origin_refs=entry["recommendation_origin_refs"],
        )
        for entry in sorted(
            delta_entries,
            key=lambda item: (
                item["entity_type"],
                item["project_external_id"] or "",
                item["entity_external_id"],
                item["delta_id"],
            ),
        )
    ]
    delta_set_id = _stable_id(
        "review-delta-set",
        review_context_id,
        ",".join(delta_item.delta_id for delta_item in delta_items) or "no-deltas",
    )
    return ReviewContextState(
        review_context_id=review_context_id,
        planning_run_id=execution_record.planning_run_id,
        source_snapshot_id=execution_record.source_snapshot_id,
        approved_plan_id=approved_plan_snapshot.approved_plan_id,
        draft_schedule_id=draft_schedule_result.draft_schedule_id,
        comparison_context=REVIEW_COMPARISON_CONTEXT_DRAFT_VS_APPROVED,
        delta_set_id=delta_set_id,
        delta_items=delta_items,
        connected_change_sets=connected_change_sets,
    )


def _build_task_attribute_changes(
    task_schedule,
    approved_task,
    resource_external_ids_by_id: Dict[str, str],
) -> List[ReviewableDeltaAttributeChange]:
    attribute_changes: List[ReviewableDeltaAttributeChange] = []
    if approved_task.item_type == REVIEW_DELTA_ENTITY_TYPE_MILESTONE:
        if approved_task.approved_due_date != task_schedule.scheduled_end_date:
            attribute_changes.append(
                ReviewableDeltaAttributeChange(
                    attribute_name=DELTA_SCOPE_ATTRIBUTE_MILESTONE_DATE,
                    before_value=approved_task.approved_due_date,
                    after_value=task_schedule.scheduled_end_date,
                )
            )
    else:
        if approved_task.approved_start_date != task_schedule.scheduled_start_date:
            attribute_changes.append(
                ReviewableDeltaAttributeChange(
                    attribute_name=DELTA_SCOPE_ATTRIBUTE_TASK_START_DATE,
                    before_value=approved_task.approved_start_date,
                    after_value=task_schedule.scheduled_start_date,
                )
            )
        if approved_task.approved_due_date != task_schedule.scheduled_end_date:
            attribute_changes.append(
                ReviewableDeltaAttributeChange(
                    attribute_name=DELTA_SCOPE_ATTRIBUTE_TASK_DUE_DATE,
                    before_value=approved_task.approved_due_date,
                    after_value=task_schedule.scheduled_end_date,
                )
            )

    draft_resource_external_ids = sorted(
        [
            resource_external_ids_by_id.get(resource_id, resource_id)
            for resource_id in task_schedule.assigned_resource_ids
        ]
    )
    approved_resource_external_ids = sorted(
        approved_task.assigned_resource_external_ids
    )
    if approved_resource_external_ids != draft_resource_external_ids:
        attribute_changes.append(
            ReviewableDeltaAttributeChange(
                attribute_name=DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS,
                before_value=approved_resource_external_ids,
                after_value=draft_resource_external_ids,
            )
        )

    return attribute_changes


def _count_task_external_ids(task_schedules) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for task_schedule in task_schedules:
        counts[task_schedule.task_external_id] = (
            counts.get(task_schedule.task_external_id, 0) + 1
        )
    return counts


def _get_recommendation_origin_refs(
    recommendation_refs_by_key: Dict[RecommendationRefKey, List[RecommendationOriginReference]],
    project_external_id: str,
    task_external_id: str,
    task_external_id_counts: Dict[str, int],
) -> List[RecommendationOriginReference]:
    project_scoped_refs = recommendation_refs_by_key.get(
        (project_external_id, task_external_id),
        [],
    )
    if project_scoped_refs:
        return project_scoped_refs
    if task_external_id_counts.get(task_external_id, 0) == 1:
        return recommendation_refs_by_key.get((None, task_external_id), [])
    return []


def _index_recommendation_origin_refs(
    recommendation_origin_refs: List[RecommendationOriginReference],
) -> Dict[RecommendationRefKey, List[RecommendationOriginReference]]:
    indexed_refs: Dict[RecommendationRefKey, List[RecommendationOriginReference]] = {}
    for recommendation_origin_ref in sorted(
        recommendation_origin_refs,
        key=lambda item: (
            item.project_external_id or "",
            item.task_external_id,
            item.recommendation_id,
        ),
    ):
        indexed_refs.setdefault(
            (
                recommendation_origin_ref.project_external_id,
                recommendation_origin_ref.task_external_id,
            ),
            [],
        ).append(recommendation_origin_ref)
    return indexed_refs


def _index_approved_tasks(
    approved_plan_snapshot: ApprovedOperatingPlanSnapshot,
) -> Dict[ApprovedTaskKey, object]:
    indexed_tasks: Dict[ApprovedTaskKey, object] = {}
    for task in approved_plan_snapshot.tasks:
        if task.task_id is not None:
            indexed_tasks[("task_id", task.task_id, "")] = task
        indexed_tasks[
            (
                "project_scoped_external_task_id",
                task.project_external_id,
                task.task_external_id,
            )
        ] = task
    return indexed_tasks


def _find_approved_task(
    approved_tasks_by_key: Dict[ApprovedTaskKey, object],
    task_id: str,
    project_external_id: str,
    task_external_id: str,
):
    return approved_tasks_by_key.get(("task_id", task_id, "")) or approved_tasks_by_key.get(
        (
            "project_scoped_external_task_id",
            project_external_id,
            task_external_id,
        )
    )


def _build_project_finish_dates(task_schedules) -> Dict[Tuple[str, str], Optional[str]]:
    finish_dates: Dict[Tuple[str, str], Optional[str]] = {}
    for task_schedule in task_schedules:
        key = (task_schedule.project_id, task_schedule.project_external_id)
        candidate_finish_date = task_schedule.scheduled_end_date
        existing_finish_date = finish_dates.get(key)
        if candidate_finish_date is None:
            if existing_finish_date is None:
                finish_dates[key] = None
            continue
        if existing_finish_date is None or candidate_finish_date > existing_finish_date:
            finish_dates[key] = candidate_finish_date
    return finish_dates


def _find_draft_project_match(
    project_finish_dates: Dict[Tuple[str, str], Optional[str]],
    project_id: Optional[str],
    project_external_id: str,
) -> Tuple[Optional[str], Optional[str]]:
    if (project_id, project_external_id) in project_finish_dates:
        return project_id, project_finish_dates[(project_id, project_external_id)]
    for (draft_project_id, draft_project_external_id), finish_date in project_finish_dates.items():
        if project_id is not None and draft_project_id == project_id:
            return draft_project_id, finish_date
        if draft_project_external_id == project_external_id:
            return draft_project_id, finish_date
    return None, None


def _attach_dependency_delta_ids(
    delta_entries: List[Dict[str, object]],
    task_delta_id_by_task_id: Dict[str, str],
    task_schedules,
) -> None:
    successor_task_ids: Dict[str, Set[str]] = {}
    for task_schedule in task_schedules:
        for predecessor_task_id in task_schedule.predecessor_task_ids:
            successor_task_ids.setdefault(predecessor_task_id, set()).add(
                task_schedule.task_id
            )

    for entry in delta_entries:
        task_id = entry.get("task_id")
        if task_id is None:
            continue
        dependency_task_ids = set(entry.pop("dependency_task_ids", []))
        dependency_task_ids.update(successor_task_ids.get(task_id, set()))
        dependency_delta_ids = sorted(
            {
                task_delta_id_by_task_id[dependency_task_id]
                for dependency_task_id in dependency_task_ids
                if dependency_task_id in task_delta_id_by_task_id
            }
        )
        entry["dependency_delta_ids"] = dependency_delta_ids


def _build_connected_change_sets(
    review_context_id: str,
    delta_entries: List[Dict[str, object]],
) -> List[ConnectedChangeSet]:
    adjacency: Dict[str, Set[str]] = {}
    entity_external_id_by_delta_id: Dict[str, str] = {}
    for entry in delta_entries:
        delta_id = entry["delta_id"]
        entity_external_id_by_delta_id[delta_id] = entry["entity_external_id"]
        adjacency.setdefault(delta_id, set())
        for dependency_delta_id in entry["dependency_delta_ids"]:
            adjacency[delta_id].add(dependency_delta_id)
            adjacency.setdefault(dependency_delta_id, set()).add(delta_id)

    connected_set_id_by_delta_id: Dict[str, str] = {}
    connected_change_sets: List[ConnectedChangeSet] = []
    visited_delta_ids: Set[str] = set()
    for delta_id in sorted(adjacency):
        if delta_id in visited_delta_ids:
            continue
        component_delta_ids = _walk_delta_component(adjacency, delta_id)
        visited_delta_ids.update(component_delta_ids)
        if len(component_delta_ids) <= 1:
            continue
        connected_set_id = _stable_id(
            "connected-change-set",
            review_context_id,
            ",".join(component_delta_ids),
        )
        for member_delta_id in component_delta_ids:
            connected_set_id_by_delta_id[member_delta_id] = connected_set_id
        connected_change_sets.append(
            ConnectedChangeSet(
                connected_set_id=connected_set_id,
                review_context_id=review_context_id,
                member_delta_ids=component_delta_ids,
                member_entity_external_ids=sorted(
                    [
                        entity_external_id_by_delta_id[member_delta_id]
                        for member_delta_id in component_delta_ids
                    ]
                ),
                minimal_for_dependency_safety=True,
            )
        )

    for entry in delta_entries:
        entry["connected_set_id"] = connected_set_id_by_delta_id.get(entry["delta_id"])

    return sorted(
        connected_change_sets,
        key=lambda item: (
            item.connected_set_id,
            item.member_delta_ids,
        ),
    )


def _walk_delta_component(
    adjacency: Dict[str, Set[str]],
    start_delta_id: str,
) -> List[str]:
    component_delta_ids: Set[str] = set()
    pending_delta_ids = [start_delta_id]
    while pending_delta_ids:
        delta_id = pending_delta_ids.pop()
        if delta_id in component_delta_ids:
            continue
        component_delta_ids.add(delta_id)
        pending_delta_ids.extend(sorted(adjacency.get(delta_id, set()) - component_delta_ids))
    return sorted(component_delta_ids)


def _build_connected_set_resolution(
    review_context: ReviewContextState,
    requested_delta_id: str,
) -> ConnectedChangeSetResolution:
    requested_delta = _get_review_delta(review_context=review_context, delta_id=requested_delta_id)

    connected_set_by_id = {
        connected_set.connected_set_id: connected_set
        for connected_set in review_context.connected_change_sets
    }
    connected_change_set = (
        None
        if requested_delta.connected_set_id is None
        else connected_set_by_id.get(requested_delta.connected_set_id)
    )
    isolated_acceptance_safe = connected_change_set is None
    return ConnectedChangeSetResolution(
        resolution_id=_stable_id(
            "connected-set-resolution",
            review_context.review_context_id,
            requested_delta_id,
            "safe" if isolated_acceptance_safe else connected_change_set.connected_set_id,
        ),
        review_context_id=review_context.review_context_id,
        requested_delta_id=requested_delta_id,
        isolated_acceptance_safe=isolated_acceptance_safe,
        blocking_reason_code=(
            None if isolated_acceptance_safe else "connected_set_required"
        ),
        blocking_reason_message=(
            None
            if isolated_acceptance_safe
            else (
                "Isolated acceptance is unsafe because related dependency-linked"
                " deltas must be reviewed together."
            )
        ),
        connected_change_set=connected_change_set,
    )


def _get_review_delta(
    review_context: ReviewContextState,
    delta_id: str,
) -> ReviewableDeltaItem:
    for delta in review_context.delta_items:
        if delta.delta_id == delta_id:
            return delta
    raise ValueError("Requested delta_id is not present in the review context.")


def _apply_acceptance_selection(
    review_context: ReviewContextState,
    selected_delta_ids: Set[str],
    selected: bool,
) -> ReviewContextState:
    updated_delta_items = [
        replace(
            delta,
            selected_for_acceptance=(
                selected if delta.delta_id in selected_delta_ids else delta.selected_for_acceptance
            ),
        )
        for delta in review_context.delta_items
    ]
    return replace(review_context, delta_items=updated_delta_items)


def _build_acceptance_selection_result(
    review_context: ReviewContextState,
    requested_delta_id: str,
    selection_scope: str,
    connected_set_id: Optional[str],
    action: str,
    status: str,
    connected_set_resolution: Optional[ConnectedChangeSetResolution],
) -> AcceptanceSelectionResult:
    blocked_reason_code = None
    blocked_reason_message = None
    if status == ACCEPTANCE_SELECTION_STATUS_BLOCKED and connected_set_resolution is not None:
        blocked_reason_code = connected_set_resolution.blocking_reason_code
        blocked_reason_message = connected_set_resolution.blocking_reason_message
    return AcceptanceSelectionResult(
        command_id=_stable_id(
            "acceptance-selection",
            review_context.review_context_id,
            selection_scope,
            requested_delta_id,
            connected_set_id or "none",
            action,
            status,
        ),
        review_context_id=review_context.review_context_id,
        selection_scope=selection_scope,
        requested_delta_id=requested_delta_id,
        connected_set_id=connected_set_id,
        action=action,
        status=status,
        blocked_reason_code=blocked_reason_code,
        blocked_reason_message=blocked_reason_message,
        review_context=review_context,
        connected_set_resolution=connected_set_resolution,
    )


def _build_activation_command_result(
    review_context: ReviewContextState,
    activation_state: ActivationState,
    resulting_approved_plan_snapshot: Optional[ApprovedOperatingPlanSnapshot],
    reused_existing: bool,
) -> ActivationCommandResult:
    return ActivationCommandResult(
        command_id=_stable_id(
            "activation-command",
            review_context.review_context_id,
            activation_state.activation_id,
            "reused" if reused_existing else "new",
        ),
        review_context_id=review_context.review_context_id,
        activation_state=activation_state,
        resulting_approved_plan_snapshot=resulting_approved_plan_snapshot,
        reused_existing=reused_existing,
        downstream_handoff=ActivationDownstreamHandoff(
            owner_service=WORKFLOW_ORCHESTRATOR_SERVICE_NAME,
            handoff_required=activation_state.status == ACTIVATION_STATUS_ACTIVATED,
            workflow_state=ACTIVATION_WORKFLOW_STATE_NOT_STARTED,
            workflow_instance_id=None,
            source_snapshot_id=(
                review_context.source_snapshot_id
                if activation_state.status == ACTIVATION_STATUS_ACTIVATED
                else None
            ),
            write_back_targets=_build_activation_write_back_targets(
                review_context=review_context,
                selected_delta_ids=activation_state.selected_delta_ids,
            )
            if activation_state.status == ACTIVATION_STATUS_ACTIVATED
            else [],
        ),
    )


def _build_activation_write_back_targets(
    review_context: ReviewContextState,
    selected_delta_ids: List[str],
) -> List[ActivationWriteBackTarget]:
    selected_delta_id_set = set(selected_delta_ids)
    write_back_targets: List[ActivationWriteBackTarget] = []
    ordered_deltas = sorted(
        [
            delta
            for delta in review_context.delta_items
            if delta.delta_id in selected_delta_id_set
        ],
        key=lambda item: (
            item.project_external_id or "",
            item.entity_external_id,
            item.delta_id,
        ),
    )
    for delta in ordered_deltas:
        write_back_targets.append(
            ActivationWriteBackTarget(
                target_id=_stable_id(
                    "activation-write-back-target",
                    review_context.review_context_id,
                    delta.delta_id,
                ),
                delta_id=delta.delta_id,
                entity_type=delta.entity_type,
                entity_external_id=delta.entity_external_id,
                entity_name=delta.entity_name,
                project_external_id=delta.project_external_id,
                write_back_action=_resolve_write_back_action(delta.entity_type),
                write_back_fields=_sorted_write_back_fields(
                    delta.delta_scope_attributes
                ),
            )
        )
    return write_back_targets


def _resolve_write_back_action(entity_type: str) -> str:
    if entity_type == REVIEW_DELTA_ENTITY_TYPE_PROJECT:
        return WRITE_BACK_ACTION_UPDATE_PROJECT_FIELDS
    return WRITE_BACK_ACTION_UPDATE_TASK_FIELDS


def _sorted_write_back_fields(field_names: List[str]) -> List[str]:
    field_order = {
        field_name: index
        for index, field_name in enumerate(WRITE_BACK_FIELD_ORDER)
    }
    return sorted(
        field_names,
        key=lambda field_name: (field_order.get(field_name, 999), field_name),
    )


def _build_activation_business_rule_blockers(
    review_context: ReviewContextState,
    current_approved_plan: Optional[ApprovedOperatingPlanSnapshot],
    blocked_acceptance_resolutions: List[ConnectedChangeSetResolution],
) -> List[ActivationBusinessRuleBlocker]:
    blockers: List[ActivationBusinessRuleBlocker] = []
    selected_delta_ids = sorted(
        [
            delta.delta_id
            for delta in review_context.delta_items
            if delta.selected_for_acceptance
        ]
    )
    if (
        current_approved_plan is None
        or current_approved_plan.approved_plan_id != review_context.approved_plan_id
    ):
        blockers.append(
            ActivationBusinessRuleBlocker(
                rule_id="rule-approved-plan-pointer",
                code="activation_requires_current_approved_plan",
                message=(
                    "Activation requires a current approved operating plan pointer before "
                    "applying accepted changes."
                ),
                entity_type="approved_plan",
                entity_id=review_context.approved_plan_id,
                entity_external_id=None,
            )
        )
    if not selected_delta_ids:
        blockers.append(
            ActivationBusinessRuleBlocker(
                rule_id="rule-approved-set-required",
                code="activation_requires_approved_set",
                message=(
                    "Activation requires at least one dependency-safe accepted change in "
                    "the current review context."
                ),
                entity_type="review_context",
                entity_id=review_context.review_context_id,
                entity_external_id=None,
            )
        )

    review_blocking_issue_codes = {
        issue_fact.code
        for issue_fact in _build_issue_facts(
            review_context=review_context,
            activation_state=None,
            blocked_acceptance_resolutions=blocked_acceptance_resolutions,
        )
        if issue_fact.context_scope == ISSUE_FACT_SCOPE_REVIEW_CONTEXT
        and issue_fact.severity == ISSUE_FACT_SEVERITY_BLOCKING
    }
    if review_blocking_issue_codes:
        blockers.append(
            ActivationBusinessRuleBlocker(
                rule_id="rule-dependency-safe-selection",
                code="activation_requires_dependency_safe_selection",
                message=(
                    "Activation requires a valid dependency-safe approved set with no "
                    "unresolved review blockers."
                ),
                entity_type="review_context",
                entity_id=review_context.review_context_id,
                entity_external_id=None,
            )
        )

    return sorted(blockers, key=lambda item: (item.code, item.entity_type, item.entity_id))


def _build_activated_approved_plan_snapshot(
    review_context: ReviewContextState,
    current_approved_plan: ApprovedOperatingPlanSnapshot,
    selected_delta_ids: List[str],
) -> ApprovedOperatingPlanSnapshot:
    selected_deltas = {
        delta.delta_id: delta
        for delta in review_context.delta_items
        if delta.delta_id in set(selected_delta_ids)
    }
    updated_tasks_by_identity: Dict[Tuple[Optional[str], str, str], ApprovedPlanTaskRecord] = {}
    for task in current_approved_plan.tasks:
        updated_task = task
        matching_delta = _find_matching_selected_delta(
            selected_deltas=selected_deltas,
            entity_type=task.item_type,
            task_id=task.task_id,
            project_external_id=task.project_external_id,
            task_external_id=task.task_external_id,
        )
        if matching_delta is not None:
            updated_task = _apply_task_delta_to_approved_task(
                task=task,
                delta=matching_delta,
            )
        updated_tasks_by_identity[
            (task.task_id, task.project_external_id, task.task_external_id)
        ] = updated_task

    updated_projects_by_identity: Dict[Tuple[Optional[str], str], ApprovedPlanProjectRecord] = {}
    for project in current_approved_plan.projects:
        updated_project = project
        matching_project_delta = _find_matching_project_delta(
            selected_deltas=selected_deltas,
            project_id=project.project_id,
            project_external_id=project.project_external_id,
        )
        if matching_project_delta is not None:
            updated_project = _apply_project_delta_to_approved_project(
                project=project,
                delta=matching_project_delta,
            )
        updated_projects_by_identity[(project.project_id, project.project_external_id)] = (
            updated_project
        )

    selected_delta_fingerprint = ",".join(selected_delta_ids)
    return ApprovedOperatingPlanSnapshot(
        approved_plan_id=_stable_id(
            "approved-plan",
            current_approved_plan.approved_plan_id,
            review_context.review_context_id,
            selected_delta_fingerprint,
        ),
        tasks=[
            updated_tasks_by_identity[(task.task_id, task.project_external_id, task.task_external_id)]
            for task in current_approved_plan.tasks
        ],
        projects=[
            updated_projects_by_identity[(project.project_id, project.project_external_id)]
            for project in current_approved_plan.projects
        ],
    )


def _find_matching_selected_delta(
    selected_deltas: Dict[str, ReviewableDeltaItem],
    entity_type: str,
    task_id: Optional[str],
    project_external_id: str,
    task_external_id: str,
) -> Optional[ReviewableDeltaItem]:
    for delta in selected_deltas.values():
        if delta.entity_type != entity_type:
            continue
        if delta.task_id is not None and task_id is not None and delta.task_id == task_id:
            return delta
        if (
            delta.project_external_id == project_external_id
            and delta.task_external_id == task_external_id
        ):
            return delta
    return None


def _apply_task_delta_to_approved_task(
    task: ApprovedPlanTaskRecord,
    delta: ReviewableDeltaItem,
) -> ApprovedPlanTaskRecord:
    approved_start_date = task.approved_start_date
    approved_due_date = task.approved_due_date
    assigned_resource_external_ids = list(task.assigned_resource_external_ids)
    for attribute_change in delta.attribute_changes:
        if attribute_change.attribute_name == DELTA_SCOPE_ATTRIBUTE_TASK_START_DATE:
            approved_start_date = attribute_change.after_value
        elif attribute_change.attribute_name in (
            DELTA_SCOPE_ATTRIBUTE_TASK_DUE_DATE,
            DELTA_SCOPE_ATTRIBUTE_MILESTONE_DATE,
        ):
            approved_due_date = attribute_change.after_value
        elif (
            attribute_change.attribute_name
            == DELTA_SCOPE_ATTRIBUTE_ASSIGNED_RESOURCE_EXTERNAL_IDS
        ):
            assigned_resource_external_ids = sorted(attribute_change.after_value or [])
    return ApprovedPlanTaskRecord(
        task_id=task.task_id,
        task_external_id=task.task_external_id,
        task_name=task.task_name,
        project_id=task.project_id,
        project_external_id=task.project_external_id,
        approved_start_date=approved_start_date,
        approved_due_date=approved_due_date,
        assigned_resource_external_ids=assigned_resource_external_ids,
        item_type=task.item_type,
    )


def _find_matching_project_delta(
    selected_deltas: Dict[str, ReviewableDeltaItem],
    project_id: Optional[str],
    project_external_id: str,
) -> Optional[ReviewableDeltaItem]:
    for delta in selected_deltas.values():
        if delta.entity_type != REVIEW_DELTA_ENTITY_TYPE_PROJECT:
            continue
        if delta.project_id is not None and project_id is not None and delta.project_id == project_id:
            return delta
        if delta.project_external_id == project_external_id:
            return delta
    return None


def _apply_project_delta_to_approved_project(
    project: ApprovedPlanProjectRecord,
    delta: ReviewableDeltaItem,
) -> ApprovedPlanProjectRecord:
    finish_date = project.finish_date
    for attribute_change in delta.attribute_changes:
        if attribute_change.attribute_name == DELTA_SCOPE_ATTRIBUTE_PROJECT_FINISH_DATE:
            finish_date = attribute_change.after_value
    return ApprovedPlanProjectRecord(
        project_id=project.project_id,
        project_external_id=project.project_external_id,
        project_name=project.project_name,
        finish_date=finish_date,
    )


def _build_issue_facts(
    review_context: ReviewContextState,
    activation_state: Optional[ActivationState],
    blocked_acceptance_resolutions: List[ConnectedChangeSetResolution],
) -> List[ReviewApprovalIssueFact]:
    delta_by_id = {
        delta.delta_id: delta
        for delta in sorted(review_context.delta_items, key=lambda item: item.delta_id)
    }
    selected_delta_ids = {
        delta.delta_id for delta in review_context.delta_items if delta.selected_for_acceptance
    }
    issue_facts_by_id: Dict[str, ReviewApprovalIssueFact] = {}

    for delta_id in sorted(selected_delta_ids):
        delta = delta_by_id[delta_id]
        missing_dependency_ids = sorted(
            dependency_id
            for dependency_id in delta.dependency_delta_ids
            if dependency_id not in selected_delta_ids
        )
        if not missing_dependency_ids:
            continue
        dependency_labels = ", ".join(missing_dependency_ids)
        issue_fact = _build_issue_fact(
            review_context=review_context,
            context_scope=ISSUE_FACT_SCOPE_REVIEW_CONTEXT,
            fact_type=ISSUE_FACT_TYPE_DEPENDENCY_SAFE_BLOCKER,
            activation_id=None,
            severity=ISSUE_FACT_SEVERITY_BLOCKING,
            code="dependency_safe_approval_blocked",
            message=(
                "Delta cannot be accepted in isolation because required dependent "
                f"change(s) are not selected: {dependency_labels}."
            ),
            entity_type="review_delta",
            entity_id=delta.delta_id,
            entity_external_id=delta.entity_external_id,
            related_delta_ids=[delta.delta_id] + missing_dependency_ids,
            related_connected_set_id=delta.connected_set_id,
        )
        issue_facts_by_id[issue_fact.fact_id] = issue_fact

    connected_set_members: Dict[str, List[ReviewableDeltaItem]] = {}
    for delta in sorted(review_context.delta_items, key=lambda item: item.delta_id):
        if delta.connected_set_id is None:
            continue
        connected_set_members.setdefault(delta.connected_set_id, []).append(delta)

    for connected_set_id, members in sorted(connected_set_members.items()):
        selected_members = [
            member for member in members if member.selected_for_acceptance
        ]
        if not selected_members or len(selected_members) == len(members):
            continue
        related_delta_ids = sorted(member.delta_id for member in members)
        issue_fact = _build_issue_fact(
            review_context=review_context,
            context_scope=ISSUE_FACT_SCOPE_REVIEW_CONTEXT,
            fact_type=ISSUE_FACT_TYPE_CONNECTED_SET_REQUIRED,
            activation_id=None,
            severity=ISSUE_FACT_SEVERITY_BLOCKING,
            code="connected_set_required",
            message=(
                "Connected-set acceptance is required before this selection can be "
                "approved safely."
            ),
            entity_type="connected_change_set",
            entity_id=connected_set_id,
            entity_external_id=None,
            related_delta_ids=related_delta_ids,
            related_connected_set_id=connected_set_id,
        )
        issue_facts_by_id[issue_fact.fact_id] = issue_fact

    for issue_fact in _build_resolution_backed_review_issue_facts(
        review_context=review_context,
        delta_by_id=delta_by_id,
        selected_delta_ids=selected_delta_ids,
        blocked_acceptance_resolutions=blocked_acceptance_resolutions,
    ):
        issue_facts_by_id[issue_fact.fact_id] = issue_fact

    if activation_state is not None:
        for issue_fact in _build_activation_issue_facts(
            review_context=review_context,
            activation_state=activation_state,
        ):
            issue_facts_by_id[issue_fact.fact_id] = issue_fact

    return sorted(
        issue_facts_by_id.values(),
        key=lambda fact: (
            fact.context_scope,
            fact.fact_type,
            fact.code,
            fact.entity_type,
            fact.entity_id,
            fact.fact_id,
        ),
    )


def _build_resolution_backed_review_issue_facts(
    review_context: ReviewContextState,
    delta_by_id: Dict[str, ReviewableDeltaItem],
    selected_delta_ids: Set[str],
    blocked_acceptance_resolutions: List[ConnectedChangeSetResolution],
) -> List[ReviewApprovalIssueFact]:
    issue_facts: List[ReviewApprovalIssueFact] = []

    for resolution in sorted(
        blocked_acceptance_resolutions,
        key=lambda item: (
            item.review_context_id,
            item.requested_delta_id,
            item.resolution_id,
        ),
    ):
        if resolution.review_context_id != review_context.review_context_id:
            continue
        if resolution.isolated_acceptance_safe or resolution.connected_change_set is None:
            continue

        connected_set = resolution.connected_change_set
        member_delta_ids = sorted(connected_set.member_delta_ids)
        if all(
            member_delta_id in selected_delta_ids
            for member_delta_id in member_delta_ids
        ):
            continue

        requested_delta = delta_by_id.get(resolution.requested_delta_id)
        if requested_delta is None:
            continue

        unresolved_related_delta_ids = sorted(
            member_delta_id
            for member_delta_id in member_delta_ids
            if member_delta_id != resolution.requested_delta_id
            and member_delta_id not in selected_delta_ids
        )
        if unresolved_related_delta_ids:
            dependency_labels = ", ".join(unresolved_related_delta_ids)
            issue_facts.append(
                _build_issue_fact(
                    review_context=review_context,
                    context_scope=ISSUE_FACT_SCOPE_REVIEW_CONTEXT,
                    fact_type=ISSUE_FACT_TYPE_DEPENDENCY_SAFE_BLOCKER,
                    activation_id=None,
                    severity=ISSUE_FACT_SEVERITY_BLOCKING,
                    code="dependency_safe_approval_blocked",
                    message=(
                        "Delta cannot be accepted in isolation because required dependent "
                        f"change(s) are not selected: {dependency_labels}."
                    ),
                    entity_type="review_delta",
                    entity_id=requested_delta.delta_id,
                    entity_external_id=requested_delta.entity_external_id,
                    related_delta_ids=[requested_delta.delta_id]
                    + unresolved_related_delta_ids,
                    related_connected_set_id=connected_set.connected_set_id,
                )
            )

        issue_facts.append(
            _build_issue_fact(
                review_context=review_context,
                context_scope=ISSUE_FACT_SCOPE_REVIEW_CONTEXT,
                fact_type=ISSUE_FACT_TYPE_CONNECTED_SET_REQUIRED,
                activation_id=None,
                severity=ISSUE_FACT_SEVERITY_BLOCKING,
                code="connected_set_required",
                message=(
                    resolution.blocking_reason_message
                    or (
                        "Connected-set acceptance is required before this selection can "
                        "be approved safely."
                    )
                ),
                entity_type="connected_change_set",
                entity_id=connected_set.connected_set_id,
                entity_external_id=None,
                related_delta_ids=member_delta_ids,
                related_connected_set_id=connected_set.connected_set_id,
            )
        )

    return issue_facts


def _build_activation_issue_facts(
    review_context: ReviewContextState,
    activation_state: ActivationState,
) -> List[ReviewApprovalIssueFact]:
    issue_facts: List[ReviewApprovalIssueFact] = []

    if activation_state.status == ACTIVATION_STATUS_BLOCKED:
        for blocker in sorted(
            activation_state.business_rule_blockers,
            key=lambda item: (item.code, item.entity_type, item.entity_id, item.rule_id),
        ):
            issue_facts.append(
                _build_issue_fact(
                    review_context=review_context,
                    context_scope=ISSUE_FACT_SCOPE_ACTIVATION,
                    fact_type=ISSUE_FACT_TYPE_ACTIVATION_BLOCKER,
                    activation_id=activation_state.activation_id,
                    severity=ISSUE_FACT_SEVERITY_BLOCKING,
                    code=blocker.code,
                    message=blocker.message,
                    entity_type=blocker.entity_type,
                    entity_id=blocker.entity_id,
                    entity_external_id=blocker.entity_external_id,
                    related_delta_ids=[],
                    related_connected_set_id=None,
                )
            )

    if (
        activation_state.status == ACTIVATION_STATUS_ACTIVATED
        and activation_state.outcome is not None
    ):
        issue_facts.append(
            _build_issue_fact(
                review_context=review_context,
                context_scope=ISSUE_FACT_SCOPE_ACTIVATION,
                fact_type=ISSUE_FACT_TYPE_ACTIVATION_OUTCOME,
                activation_id=activation_state.activation_id,
                severity=ISSUE_FACT_SEVERITY_INFO,
                code=activation_state.outcome.code,
                message=activation_state.outcome.message,
                entity_type="activation_record",
                entity_id=activation_state.activation_id,
                entity_external_id=None,
                related_delta_ids=sorted(activation_state.outcome.activated_delta_ids),
                related_connected_set_id=None,
            )
        )

    return issue_facts


def _build_issue_fact(
    review_context: ReviewContextState,
    context_scope: str,
    fact_type: str,
    activation_id: Optional[str],
    severity: str,
    code: str,
    message: str,
    entity_type: str,
    entity_id: str,
    entity_external_id: Optional[str],
    related_delta_ids: List[str],
    related_connected_set_id: Optional[str],
) -> ReviewApprovalIssueFact:
    return ReviewApprovalIssueFact(
        fact_id=_stable_id(
            "review-approval-issue-fact",
            review_context.review_context_id,
            activation_id or "none",
            context_scope,
            fact_type,
            code,
            entity_type,
            entity_id,
            ",".join(sorted(related_delta_ids)),
            related_connected_set_id or "none",
        ),
        emitted_by_service=SERVICE_NAME,
        context_scope=context_scope,
        fact_type=fact_type,
        review_context_id=review_context.review_context_id,
        planning_run_id=review_context.planning_run_id,
        source_snapshot_id=review_context.source_snapshot_id,
        approved_plan_id=review_context.approved_plan_id,
        activation_id=activation_id,
        severity=severity,
        code=code,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_external_id=entity_external_id,
        related_delta_ids=sorted(related_delta_ids),
        related_connected_set_id=related_connected_set_id,
    )


def _attribute_change_fingerprint(
    attribute_changes: Iterable[ReviewableDeltaAttributeChange],
) -> str:
    return "|".join(
        "%s=%s->%s"
        % (
            attribute_change.attribute_name,
            repr(attribute_change.before_value),
            repr(attribute_change.after_value),
        )
        for attribute_change in attribute_changes
    )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"
