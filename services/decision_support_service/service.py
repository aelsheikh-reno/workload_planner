"""Decision Support warning/trust interpretation and recommendation lifecycle."""

from dataclasses import replace
from datetime import date, timedelta
import hashlib
from typing import Dict, List, Optional, Tuple

from services.integration_service import SourceSetupIssueFact
from services.planning_engine_service import (
    PlanningIssueFact,
    PlanningRunExecutionResult,
)
from services.review_approval_service import (
    ISSUE_FACT_TYPE_ACTIVATION_BLOCKER,
    ISSUE_FACT_TYPE_ACTIVATION_OUTCOME,
    ReviewApprovalIssueFact,
)

from .contracts import (
    INTERPRETATION_CATEGORY_ACTIVATION_BLOCKER,
    INTERPRETATION_CATEGORY_ADVISORY_WARNING,
    INTERPRETATION_CATEGORY_REVIEW_BLOCKER,
    INTERPRETATION_CATEGORY_SETUP_BLOCKER,
    INTERPRETATION_CATEGORY_SETUP_WARNING,
    INTERPRETATION_CATEGORY_TRUST_LIMITED,
    RECOMMENDATION_ACTION_FAMILY_DATE_EXTENSION,
    RECOMMENDATION_ACTION_FAMILY_MOVE_DEFER,
    RECOMMENDATION_ACTION_FAMILY_ORDER,
    RECOMMENDATION_ACTION_FAMILY_REASSIGNMENT,
    RECOMMENDATION_ACTION_FAMILY_RECHUNK,
    RECOMMENDATION_CONTEXT_STATE_AVAILABLE,
    RECOMMENDATION_CONTEXT_STATE_NOT_AVAILABLE,
    RECOMMENDATION_CONTEXT_STATE_NO_ACTIONABLE,
    RECOMMENDATION_FRESHNESS_FRESH,
    RECOMMENDATION_FRESHNESS_NOT_GENERATED,
    RecommendationCandidate,
    RecommendationOriginContext,
    ResourceRecommendationContextState,
    SIGNAL_TYPE_TRUST,
    SIGNAL_TYPE_WARNING,
    WARNING_TRUST_LIFECYCLE_STATE_CURRENT,
    ScreenWarningTrustSignal,
    ScreenWarningTrustState,
)
from .repository import InMemoryDecisionSupportRepository


DECISION_SUPPORT_SERVICE_NAME = "Decision Support Service"
INTEGRATION_SERVICE_NAME = "Integration Service"
PLANNING_ENGINE_SERVICE_NAME = "Planning Engine Service"
REVIEW_APPROVAL_SERVICE_NAME = "Review & Approval Service"

TRUST_LIMITED_PLANNING_CODES = {
    "criticality_zero_slack",
    "dependency_chain_pressure",
}

RESOURCE_PRESSURE_CODES = {"draft_partially_schedulable", "draft_unschedulable"}
MIN_RECHUNK_EFFORT_HOURS = 16.0


class DecisionSupportService:
    """Owns warning/trust interpretation while exposing a read seam for BFFs."""

    def __init__(
        self,
        repository: Optional[InMemoryDecisionSupportRepository] = None,
    ) -> None:
        self._repository = repository or InMemoryDecisionSupportRepository()

    def publish_screen_warning_trust_state(
        self,
        screen_id: str,
        signals: List[ScreenWarningTrustSignal],
        planning_context_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
    ) -> ScreenWarningTrustState:
        state = _build_screen_warning_trust_state(
            screen_id=screen_id,
            signals=signals,
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
            total_input_fact_count=len(signals),
        )
        self._repository.save_screen_warning_trust_state(state)
        return state

    def refresh_warning_trust_interpretation(
        self,
        screen_id: str,
        source_issue_facts: Optional[List[SourceSetupIssueFact]] = None,
        planning_issue_facts: Optional[List[PlanningIssueFact]] = None,
        review_issue_facts: Optional[List[ReviewApprovalIssueFact]] = None,
        planning_context_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
    ) -> ScreenWarningTrustState:
        source_issue_facts = list(source_issue_facts or [])
        planning_issue_facts = list(planning_issue_facts or [])
        review_issue_facts = list(review_issue_facts or [])
        resolved_snapshot_id = _resolve_source_snapshot_id(
            source_snapshot_id=source_snapshot_id,
            source_issue_facts=source_issue_facts,
            planning_issue_facts=planning_issue_facts,
            review_issue_facts=review_issue_facts,
        )
        signals: List[ScreenWarningTrustSignal] = []

        for issue_fact in source_issue_facts:
            signals.append(
                _interpret_source_issue_fact(
                    screen_id=screen_id,
                    planning_context_key=planning_context_key,
                    issue_fact=issue_fact,
                )
            )

        for issue_fact in planning_issue_facts:
            signals.append(
                _interpret_planning_issue_fact(
                    screen_id=screen_id,
                    planning_context_key=planning_context_key,
                    issue_fact=issue_fact,
                )
            )

        for issue_fact in review_issue_facts:
            interpreted_signal = _interpret_review_issue_fact(
                screen_id=screen_id,
                planning_context_key=planning_context_key,
                issue_fact=issue_fact,
            )
            if interpreted_signal is not None:
                signals.append(interpreted_signal)

        state = _build_screen_warning_trust_state(
            screen_id=screen_id,
            signals=signals,
            planning_context_key=planning_context_key,
            source_snapshot_id=resolved_snapshot_id,
            total_input_fact_count=(
                len(source_issue_facts)
                + len(planning_issue_facts)
                + len(review_issue_facts)
            ),
        )
        self._repository.save_screen_warning_trust_state(state)
        return state

    def get_screen_warning_trust_state(
        self,
        screen_id: str,
        planning_context_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
    ) -> Optional[ScreenWarningTrustState]:
        return self._repository.get_screen_warning_trust_state(
            screen_id=screen_id,
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
        )

    def refresh_resource_recommendation_context(
        self,
        execution_result: PlanningRunExecutionResult,
        resource_external_id: str,
    ) -> ResourceRecommendationContextState:
        context_state = _generate_resource_recommendation_context_state(
            execution_result=execution_result,
            resource_external_id=resource_external_id,
        )
        self._repository.save_resource_recommendation_context(context_state)
        return context_state

    def publish_resource_recommendation_context(
        self,
        resource_external_id: str,
        recommendations: List[RecommendationCandidate],
        resource_id: Optional[str] = None,
        planning_context_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
        state: str = RECOMMENDATION_CONTEXT_STATE_AVAILABLE,
        freshness_status: str = RECOMMENDATION_FRESHNESS_FRESH,
    ) -> ResourceRecommendationContextState:
        context_state = _build_resource_recommendation_context_state(
            resource_external_id=resource_external_id,
            recommendations=recommendations,
            resource_id=resource_id,
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
            state=state,
            freshness_status=freshness_status,
        )
        self._repository.save_resource_recommendation_context(context_state)
        return context_state

    def get_resource_recommendation_context(
        self,
        resource_external_id: str,
        planning_context_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
    ) -> Optional[ResourceRecommendationContextState]:
        return self._repository.get_resource_recommendation_context(
            resource_external_id=resource_external_id,
            planning_context_key=planning_context_key,
            source_snapshot_id=source_snapshot_id,
        )

    def get_recommendation_candidate(
        self,
        recommendation_id: str,
    ) -> Optional[RecommendationCandidate]:
        return self._repository.get_recommendation_candidate(recommendation_id)

    def get_recommendation_origin_context(
        self,
        recommendation_id: str,
    ) -> Optional[RecommendationOriginContext]:
        return self._repository.get_recommendation_origin_context(recommendation_id)


def _build_screen_warning_trust_state(
    screen_id: str,
    signals: List[ScreenWarningTrustSignal],
    planning_context_key: Optional[str],
    source_snapshot_id: Optional[str],
    total_input_fact_count: int,
) -> ScreenWarningTrustState:
    ordered_signals = sorted(signals, key=_signal_sort_key)
    warning_signal_count = len(
        [signal for signal in ordered_signals if signal.signal_type == SIGNAL_TYPE_WARNING]
    )
    trust_signal_count = len(
        [signal for signal in ordered_signals if signal.signal_type == SIGNAL_TYPE_TRUST]
    )
    trust_limited_signal_count = len(
        [
            signal
            for signal in ordered_signals
            if signal.interpretation_category == INTERPRETATION_CATEGORY_TRUST_LIMITED
        ]
    )
    advisory_signal_count = len(
        [signal for signal in ordered_signals if signal.advisory and not signal.blocking]
    )
    blocking_signal_count = len(
        [signal for signal in ordered_signals if signal.blocking or not signal.advisory]
    )
    interpretation_id = _stable_id(
        "warning-trust-state",
        screen_id,
        planning_context_key or "none",
        source_snapshot_id or "none",
        ",".join(signal.signal_id for signal in ordered_signals) or "no-signals",
        str(total_input_fact_count),
    )
    return ScreenWarningTrustState(
        interpretation_id=interpretation_id,
        screen_id=screen_id,
        source_snapshot_id=source_snapshot_id,
        planning_context_key=planning_context_key,
        lifecycle_state=WARNING_TRUST_LIFECYCLE_STATE_CURRENT,
        active_signal_count=len(ordered_signals),
        advisory_signal_count=advisory_signal_count,
        blocking_signal_count=blocking_signal_count,
        warning_signal_count=warning_signal_count,
        trust_signal_count=trust_signal_count,
        trust_limited_signal_count=trust_limited_signal_count,
        total_input_fact_count=total_input_fact_count,
        interpreted_signal_count=len(ordered_signals),
        signals=ordered_signals,
    )


def _generate_resource_recommendation_context_state(
    execution_result: PlanningRunExecutionResult,
    resource_external_id: str,
) -> ResourceRecommendationContextState:
    execution_record = execution_result.execution_record
    resource_summary = _find_resource_summary(
        execution_result=execution_result,
        resource_external_id=resource_external_id,
    )
    if resource_summary is None:
        return _build_resource_recommendation_context_state(
            resource_external_id=resource_external_id,
            recommendations=[],
            resource_id=None,
            planning_context_key=execution_record.planning_context_key,
            source_snapshot_id=execution_record.source_snapshot_id,
            state=RECOMMENDATION_CONTEXT_STATE_NOT_AVAILABLE,
            freshness_status=RECOMMENDATION_FRESHNESS_NOT_GENERATED,
        )

    recommendations = _generate_recommendation_candidates(
        execution_result=execution_result,
        resource_id=resource_summary.resource_id,
        resource_external_id=resource_external_id,
    )
    state = (
        RECOMMENDATION_CONTEXT_STATE_AVAILABLE
        if recommendations
        else RECOMMENDATION_CONTEXT_STATE_NO_ACTIONABLE
    )
    return _build_resource_recommendation_context_state(
        resource_external_id=resource_external_id,
        recommendations=recommendations,
        resource_id=resource_summary.resource_id,
        planning_context_key=execution_record.planning_context_key,
        source_snapshot_id=execution_record.source_snapshot_id,
        state=state,
        freshness_status=RECOMMENDATION_FRESHNESS_FRESH,
    )


def _generate_recommendation_candidates(
    execution_result: PlanningRunExecutionResult,
    resource_id: str,
    resource_external_id: str,
) -> List[RecommendationCandidate]:
    draft_schedule_result = execution_result.draft_schedule_result
    capacity_result = execution_result.capacity_result
    diagnostics_result = execution_result.diagnostics_result
    execution_record = execution_result.execution_record

    variance_by_task_id = {
        fact.task_id: fact for fact in diagnostics_result.variance_facts
    }
    criticality_by_task_id = {
        fact.task_id: fact for fact in diagnostics_result.criticality_facts
    }
    issue_facts_by_task_id: Dict[str, List[PlanningIssueFact]] = {}
    for issue_fact in diagnostics_result.planning_issue_facts:
        issue_facts_by_task_id.setdefault(issue_fact.entity_id, []).append(issue_fact)

    free_capacity_by_resource_date = _build_free_capacity_by_resource_date(
        execution_result=execution_result,
    )
    resource_pressure_score = _build_resource_pressure_score(
        task_schedules=draft_schedule_result.task_schedules,
        issue_facts_by_task_id=issue_facts_by_task_id,
        resource_id=resource_id,
    )
    if resource_pressure_score <= 0:
        return []

    candidate_list: List[RecommendationCandidate] = []
    for task_schedule in sorted(
        draft_schedule_result.task_schedules,
        key=lambda item: (item.task_external_id, item.task_id),
    ):
        if resource_id not in task_schedule.assigned_resource_ids:
            continue

        variance_fact = variance_by_task_id.get(task_schedule.task_id)
        criticality_fact = criticality_by_task_id.get(task_schedule.task_id)
        if variance_fact is None or criticality_fact is None:
            continue
        task_issue_facts = issue_facts_by_task_id.get(task_schedule.task_id, [])

        for candidate in [
            _build_rechunk_recommendation(
                execution_result=execution_result,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
                task_schedule=task_schedule,
                variance_fact=variance_fact,
                criticality_fact=criticality_fact,
                task_issue_facts=task_issue_facts,
            ),
            _build_reassignment_recommendation(
                execution_result=execution_result,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
                task_schedule=task_schedule,
                variance_fact=variance_fact,
                criticality_fact=criticality_fact,
                task_issue_facts=task_issue_facts,
                free_capacity_by_resource_date=free_capacity_by_resource_date,
            ),
            _build_date_extension_recommendation(
                execution_result=execution_result,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
                task_schedule=task_schedule,
                variance_fact=variance_fact,
                criticality_fact=criticality_fact,
                task_issue_facts=task_issue_facts,
            ),
            _build_move_defer_recommendation(
                execution_record=execution_record,
                diagnostics_id=diagnostics_result.diagnostics_id,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
                task_schedule=task_schedule,
                criticality_fact=criticality_fact,
                task_issue_facts=task_issue_facts,
                resource_pressure_score=resource_pressure_score,
                source_snapshot_id=draft_schedule_result.source_snapshot_id,
                planning_context_key=execution_record.planning_context_key,
                draft_schedule_id=draft_schedule_result.draft_schedule_id,
            ),
        ]:
            if candidate is not None:
                candidate_list.append(candidate)

    return _rank_recommendation_candidates(candidate_list)


def _build_resource_recommendation_context_state(
    resource_external_id: str,
    recommendations: List[RecommendationCandidate],
    resource_id: Optional[str],
    planning_context_key: Optional[str],
    source_snapshot_id: Optional[str],
    state: str,
    freshness_status: str,
) -> ResourceRecommendationContextState:
    ordered_recommendations = sorted(
        recommendations,
        key=_recommendation_context_sort_key,
    )
    actionable_recommendation_count = len(ordered_recommendations)
    if state != RECOMMENDATION_CONTEXT_STATE_AVAILABLE:
        actionable_recommendation_count = 0

    context_id = _stable_id(
        "recommendation-context",
        resource_external_id,
        planning_context_key or "none",
        source_snapshot_id or "none",
        state,
        freshness_status,
        ",".join(
            recommendation.recommendation_id
            for recommendation in ordered_recommendations
        )
        or "no-recommendations",
    )
    return ResourceRecommendationContextState(
        context_id=context_id,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
        state=state,
        freshness_status=freshness_status,
        actionable_recommendation_count=actionable_recommendation_count,
        total_recommendation_count=len(ordered_recommendations),
        recommendations=ordered_recommendations,
    )


def _find_resource_summary(
    execution_result: PlanningRunExecutionResult,
    resource_external_id: str,
):
    for summary in execution_result.capacity_result.resource_summaries:
        if summary.resource_external_id == resource_external_id:
            return summary
    return None


def _build_free_capacity_by_resource_date(
    execution_result: PlanningRunExecutionResult,
) -> Dict[Tuple[str, str], float]:
    allocations_by_resource_date: Dict[Tuple[str, str], float] = {}
    for allocation in execution_result.draft_schedule_result.allocation_outputs:
        key = (allocation.resource_external_id, allocation.date)
        allocations_by_resource_date[key] = round(
            allocations_by_resource_date.get(key, 0.0) + allocation.allocated_hours,
            4,
        )

    free_capacity_by_resource_date: Dict[Tuple[str, str], float] = {}
    for output in execution_result.capacity_result.daily_capacity_outputs:
        key = (output.resource_external_id, output.date)
        free_capacity_by_resource_date[key] = round(
            output.productive_capacity_hours - allocations_by_resource_date.get(key, 0.0),
            4,
        )
    return free_capacity_by_resource_date


def _build_resource_pressure_score(
    task_schedules: List,
    issue_facts_by_task_id: Dict[str, List[PlanningIssueFact]],
    resource_id: str,
) -> int:
    scores = []
    for task_schedule in task_schedules:
        if resource_id not in task_schedule.assigned_resource_ids:
            continue
        issue_codes = {
            issue_fact.code
            for issue_fact in issue_facts_by_task_id.get(task_schedule.task_id, [])
        }
        if (
            task_schedule.unscheduled_effort_hours > 0
            or issue_codes & RESOURCE_PRESSURE_CODES
        ):
            scores.append(_task_pressure_score(task_schedule))
    return max(scores) if scores else 0


def _task_pressure_score(task_schedule) -> int:
    score = 0
    if task_schedule.status == "unschedulable":
        score += 100
    elif task_schedule.status == "partially_scheduled":
        score += 90
    elif task_schedule.unscheduled_effort_hours > 0:
        score += 80
    else:
        score += 60
    score += min(int(round(task_schedule.unscheduled_effort_hours)), 24)
    score += min(int(round(task_schedule.required_effort_hours / 8.0)), 8)
    return score


def _build_rechunk_recommendation(
    execution_result: PlanningRunExecutionResult,
    resource_id: str,
    resource_external_id: str,
    task_schedule,
    variance_fact,
    criticality_fact,
    task_issue_facts: List[PlanningIssueFact],
) -> Optional[RecommendationCandidate]:
    if criticality_fact.blocked_by_unscheduled_predecessor:
        return None
    if task_schedule.required_effort_hours < MIN_RECHUNK_EFFORT_HOURS:
        return None
    if not (
        task_schedule.unscheduled_effort_hours > 0
        or variance_fact.slippage_detected
        or _has_issue_code(task_issue_facts, "draft_partially_schedulable")
        or _has_issue_code(task_issue_facts, "draft_unschedulable")
    ):
        return None

    return _build_recommendation_candidate(
        execution_result=execution_result,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        task_schedule=task_schedule,
        action_family=RECOMMENDATION_ACTION_FAMILY_RECHUNK,
        ranking_score=_task_pressure_score(task_schedule),
        disruption_score=1,
        handoff_overhead_score=1,
        requires_review=True,
        title=f"Rechunk {task_schedule.task_name}",
        summary=(
            "Split the task into smaller pieces so the remaining effort can be"
            " reviewed and placed with lower disruption."
        ),
        rationale=(
            "The current draft leaves effort under pressure, and smaller units"
            " reduce blast radius while preserving dependency intent."
        ),
        effect_summary=(
            f"Creates a smaller reviewable work shape for up to "
            f"{round(task_schedule.unscheduled_effort_hours or task_schedule.required_effort_hours, 4)}"
            " hours of pressured work."
        ),
        trigger_issue_fact_ids=_sorted_fact_ids(task_issue_facts),
    )


def _build_reassignment_recommendation(
    execution_result: PlanningRunExecutionResult,
    resource_id: str,
    resource_external_id: str,
    task_schedule,
    variance_fact,
    criticality_fact,
    task_issue_facts: List[PlanningIssueFact],
    free_capacity_by_resource_date: Dict[Tuple[str, str], float],
) -> Optional[RecommendationCandidate]:
    if criticality_fact.blocked_by_unscheduled_predecessor:
        return None
    if not (
        task_schedule.unscheduled_effort_hours > 0
        or (
            variance_fact.finish_variance_days is not None
            and variance_fact.finish_variance_days > 0
        )
    ):
        return None

    target_resource = _find_reassignment_target(
        execution_result=execution_result,
        current_resource_external_id=resource_external_id,
        task_schedule=task_schedule,
        free_capacity_by_resource_date=free_capacity_by_resource_date,
    )
    if target_resource is None:
        return None

    target_resource_external_id, target_resource_id, transferable_hours = target_resource
    return _build_recommendation_candidate(
        execution_result=execution_result,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        task_schedule=task_schedule,
        action_family=RECOMMENDATION_ACTION_FAMILY_REASSIGNMENT,
        ranking_score=_task_pressure_score(task_schedule),
        disruption_score=3,
        handoff_overhead_score=2,
        requires_review=True,
        title=f"Reassign pressured work from {task_schedule.task_name}",
        summary=(
            f"Shift up to {transferable_hours} hours to {target_resource_external_id}"
            " where authoritative daily capacity remains available."
        ),
        rationale=(
            "Another resource has compatible free capacity inside the current task"
            " window, so reassignment can relieve pressure without changing"
            " dependency ordering."
        ),
        effect_summary=(
            f"Targets {target_resource_external_id} for up to {transferable_hours}"
            " hours of relieved load."
        ),
        target_suffix=target_resource_id,
        trigger_issue_fact_ids=_sorted_fact_ids(task_issue_facts),
    )


def _build_date_extension_recommendation(
    execution_result: PlanningRunExecutionResult,
    resource_id: str,
    resource_external_id: str,
    task_schedule,
    variance_fact,
    criticality_fact,
    task_issue_facts: List[PlanningIssueFact],
) -> Optional[RecommendationCandidate]:
    if criticality_fact.blocked_by_unscheduled_predecessor:
        return None
    if task_schedule.requested_due_date is None:
        return None
    if not (
        task_schedule.unscheduled_effort_hours > 0
        or (
            variance_fact.finish_variance_days is not None
            and variance_fact.finish_variance_days > 0
        )
    ):
        return None

    extension_days = max(
        1,
        int(round(task_schedule.unscheduled_effort_hours / 8.0))
        if task_schedule.unscheduled_effort_hours > 0
        else (variance_fact.finish_variance_days or variance_fact.start_variance_days or 1),
    )
    return _build_recommendation_candidate(
        execution_result=execution_result,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        task_schedule=task_schedule,
        action_family=RECOMMENDATION_ACTION_FAMILY_DATE_EXTENSION,
        ranking_score=_task_pressure_score(task_schedule),
        disruption_score=3,
        handoff_overhead_score=2,
        requires_review=True,
        title=f"Extend the date window for {task_schedule.task_name}",
        summary=(
            f"Extend the due date by about {extension_days} day(s) so the draft can"
            " absorb current capacity pressure explicitly."
        ),
        rationale=(
            "The current window does not fully absorb the draft effort safely, so an"
            " explicit date extension is safer than presenting the work as fully"
            " placeable."
        ),
        effect_summary=(
            f"Adds roughly {extension_days} day(s) of reviewable schedule room for"
            f" {task_schedule.task_external_id}."
        ),
        target_suffix=str(extension_days),
        trigger_issue_fact_ids=_sorted_fact_ids(task_issue_facts),
    )


def _build_move_defer_recommendation(
    execution_record,
    diagnostics_id: str,
    resource_id: str,
    resource_external_id: str,
    task_schedule,
    criticality_fact,
    task_issue_facts: List[PlanningIssueFact],
    resource_pressure_score: int,
    source_snapshot_id: str,
    planning_context_key: Optional[str],
    draft_schedule_id: str,
) -> Optional[RecommendationCandidate]:
    if resource_pressure_score <= 0:
        return None
    if task_schedule.status != "scheduled":
        return None
    if criticality_fact.blocked_by_unscheduled_predecessor or criticality_fact.critical:
        return None
    if criticality_fact.slack_days is None or criticality_fact.slack_days <= 0:
        return None
    if _has_issue_code(task_issue_facts, "draft_unschedulable"):
        return None

    recommendation_id = _stable_id(
        "recommendation",
        execution_record.planning_run_id,
        resource_external_id,
        task_schedule.task_id,
        RECOMMENDATION_ACTION_FAMILY_MOVE_DEFER,
        "same-resource",
    )
    trigger_issue_fact_ids = _sorted_fact_ids(task_issue_facts)
    origin_context = RecommendationOriginContext(
        origin_screen_id="S03",
        planning_run_id=execution_record.planning_run_id,
        draft_schedule_id=draft_schedule_id,
        diagnostics_id=diagnostics_id,
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        task_id=task_schedule.task_id,
        task_external_id=task_schedule.task_external_id,
        trigger_issue_fact_ids=trigger_issue_fact_ids,
    )
    return RecommendationCandidate(
        recommendation_id=recommendation_id,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        planning_context_key=planning_context_key,
        source_snapshot_id=source_snapshot_id,
        title=f"Move or defer {task_schedule.task_name}",
        summary=(
            "Treat this lower-criticality work as a release valve for the overloaded"
            " queue before changing higher-pressure tasks."
        ),
        action_family=RECOMMENDATION_ACTION_FAMILY_MOVE_DEFER,
        priority_rank=0,
        requires_review=False,
        rationale=(
            "The task still has slack and no blocking dependency pressure, so moving"
            " it is a lower-overhead way to release capacity."
        ),
        affected_task_ids=[task_schedule.task_id],
        affected_task_external_ids=[task_schedule.task_external_id],
        effect_summary=(
            f"Preserves the overloaded task path by freeing up to "
            f"{round(task_schedule.required_effort_hours, 4)} hours from a lower-criticality queue item."
        ),
        ranking_score=max(resource_pressure_score - 20, 1),
        disruption_score=2,
        handoff_overhead_score=1,
        origin_context=origin_context,
        trigger_issue_fact_ids=trigger_issue_fact_ids,
    )


def _build_recommendation_candidate(
    execution_result: PlanningRunExecutionResult,
    resource_id: str,
    resource_external_id: str,
    task_schedule,
    action_family: str,
    ranking_score: int,
    disruption_score: int,
    handoff_overhead_score: int,
    requires_review: bool,
    title: str,
    summary: str,
    rationale: str,
    effect_summary: str,
    trigger_issue_fact_ids: List[str],
    target_suffix: str = "none",
) -> RecommendationCandidate:
    execution_record = execution_result.execution_record
    diagnostics_id = execution_result.diagnostics_result.diagnostics_id
    recommendation_id = _stable_id(
        "recommendation",
        execution_record.planning_run_id,
        resource_external_id,
        task_schedule.task_id,
        action_family,
        target_suffix,
    )
    origin_context = RecommendationOriginContext(
        origin_screen_id="S03",
        planning_run_id=execution_record.planning_run_id,
        draft_schedule_id=execution_result.draft_schedule_result.draft_schedule_id,
        diagnostics_id=diagnostics_id,
        planning_context_key=execution_record.planning_context_key,
        source_snapshot_id=execution_record.source_snapshot_id,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        task_id=task_schedule.task_id,
        task_external_id=task_schedule.task_external_id,
        trigger_issue_fact_ids=trigger_issue_fact_ids,
    )
    return RecommendationCandidate(
        recommendation_id=recommendation_id,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        planning_context_key=execution_record.planning_context_key,
        source_snapshot_id=execution_record.source_snapshot_id,
        title=title,
        summary=summary,
        action_family=action_family,
        priority_rank=0,
        requires_review=requires_review,
        rationale=rationale,
        affected_task_ids=[task_schedule.task_id],
        affected_task_external_ids=[task_schedule.task_external_id],
        effect_summary=effect_summary,
        ranking_score=ranking_score,
        disruption_score=disruption_score,
        handoff_overhead_score=handoff_overhead_score,
        origin_context=origin_context,
        trigger_issue_fact_ids=trigger_issue_fact_ids,
    )


def _find_reassignment_target(
    execution_result: PlanningRunExecutionResult,
    current_resource_external_id: str,
    task_schedule,
    free_capacity_by_resource_date: Dict[Tuple[str, str], float],
) -> Optional[Tuple[str, str, float]]:
    required_hours = round(
        task_schedule.unscheduled_effort_hours
        if task_schedule.unscheduled_effort_hours > 0
        else task_schedule.required_effort_hours,
        4,
    )
    if required_hours <= 0:
        return None

    window_dates = _task_window_dates(task_schedule)
    if not window_dates:
        return None

    candidates: List[Tuple[float, str, str]] = []
    for resource_summary in execution_result.capacity_result.resource_summaries:
        if resource_summary.resource_external_id == current_resource_external_id:
            continue
        available_hours = round(
            sum(
                max(
                    0.0,
                    free_capacity_by_resource_date.get(
                        (resource_summary.resource_external_id, candidate_date),
                        0.0,
                    ),
                )
                for candidate_date in window_dates
            ),
            4,
        )
        if available_hours >= required_hours:
            candidates.append(
                (
                    available_hours,
                    resource_summary.resource_external_id,
                    resource_summary.resource_id,
                )
            )

    if not candidates:
        return None

    available_hours, target_resource_external_id, target_resource_id = sorted(
        candidates,
        key=lambda item: (-item[0], item[1], item[2]),
    )[0]
    return (
        target_resource_external_id,
        target_resource_id,
        round(min(required_hours, available_hours), 4),
    )


def _task_window_dates(task_schedule) -> List[str]:
    window_start = task_schedule.requested_start_date or task_schedule.scheduled_start_date
    window_end = task_schedule.requested_due_date or task_schedule.scheduled_end_date
    if window_start is None or window_end is None:
        return []
    start_date = date.fromisoformat(window_start)
    end_date = date.fromisoformat(window_end)
    if end_date < start_date:
        return []

    candidate_dates: List[str] = []
    current = start_date
    while current <= end_date:
        candidate_dates.append(current.isoformat())
        current += timedelta(days=1)
    return candidate_dates


def _sorted_fact_ids(task_issue_facts: List[PlanningIssueFact]) -> List[str]:
    return sorted(issue_fact.fact_id for issue_fact in task_issue_facts)


def _has_issue_code(task_issue_facts: List[PlanningIssueFact], code: str) -> bool:
    return any(issue_fact.code == code for issue_fact in task_issue_facts)


def _rank_recommendation_candidates(
    candidates: List[RecommendationCandidate],
) -> List[RecommendationCandidate]:
    ordered_candidates = sorted(candidates, key=_recommendation_ranking_sort_key)
    return [
        replace(candidate, priority_rank=index)
        for index, candidate in enumerate(ordered_candidates, start=1)
    ]


def _recommendation_ranking_sort_key(
    recommendation: RecommendationCandidate,
) -> Tuple[int, int, int, int, str]:
    return (
        -recommendation.ranking_score,
        recommendation.disruption_score,
        recommendation.handoff_overhead_score,
        _recommendation_action_family_rank(recommendation.action_family),
        recommendation.recommendation_id,
    )


def _recommendation_context_sort_key(
    recommendation: RecommendationCandidate,
) -> Tuple[int, int, str]:
    return (
        recommendation.priority_rank,
        _recommendation_action_family_rank(recommendation.action_family),
        recommendation.recommendation_id,
    )


def _recommendation_action_family_rank(action_family: str) -> int:
    return RECOMMENDATION_ACTION_FAMILY_ORDER.get(action_family, 999)


def _interpret_source_issue_fact(
    screen_id: str,
    planning_context_key: Optional[str],
    issue_fact: SourceSetupIssueFact,
) -> ScreenWarningTrustSignal:
    blocking = issue_fact.severity == "blocking"
    interpretation_category = (
        INTERPRETATION_CATEGORY_SETUP_BLOCKER
        if blocking
        else INTERPRETATION_CATEGORY_SETUP_WARNING
    )
    return ScreenWarningTrustSignal(
        signal_id=_stable_id(
            "warning-signal",
            screen_id,
            INTEGRATION_SERVICE_NAME,
            issue_fact.issue_id,
            interpretation_category,
            issue_fact.code,
        ),
        screen_id=screen_id,
        source_snapshot_id=issue_fact.source_snapshot_id,
        planning_context_key=planning_context_key,
        signal_type=SIGNAL_TYPE_WARNING,
        severity="blocking" if blocking else "warning",
        code=issue_fact.code,
        message=issue_fact.message,
        advisory=not blocking,
        blocking=blocking,
        interpretation_category=interpretation_category,
        source_issue_service=INTEGRATION_SERVICE_NAME,
        source_fact_id=issue_fact.issue_id,
        source_fact_type="source_setup_issue_fact",
        source_fact_severity=issue_fact.severity,
        entity_type=issue_fact.entity_type,
        entity_id=None,
        entity_external_id=issue_fact.entity_external_id,
    )


def _interpret_planning_issue_fact(
    screen_id: str,
    planning_context_key: Optional[str],
    issue_fact: PlanningIssueFact,
) -> ScreenWarningTrustSignal:
    trust_limited = issue_fact.code in TRUST_LIMITED_PLANNING_CODES
    signal_type = SIGNAL_TYPE_TRUST if trust_limited else SIGNAL_TYPE_WARNING
    interpretation_category = (
        INTERPRETATION_CATEGORY_TRUST_LIMITED
        if trust_limited
        else INTERPRETATION_CATEGORY_ADVISORY_WARNING
    )
    return ScreenWarningTrustSignal(
        signal_id=_stable_id(
            "warning-signal",
            screen_id,
            PLANNING_ENGINE_SERVICE_NAME,
            issue_fact.fact_id,
            interpretation_category,
            issue_fact.code,
        ),
        screen_id=screen_id,
        source_snapshot_id=issue_fact.source_snapshot_id,
        planning_context_key=planning_context_key,
        signal_type=signal_type,
        severity="warning",
        code=issue_fact.code,
        message=issue_fact.message,
        advisory=True,
        blocking=False,
        interpretation_category=interpretation_category,
        source_issue_service=PLANNING_ENGINE_SERVICE_NAME,
        source_fact_id=issue_fact.fact_id,
        source_fact_type="planning_issue_fact",
        source_fact_severity=issue_fact.severity,
        entity_type=issue_fact.entity_type,
        entity_id=issue_fact.entity_id,
        entity_external_id=issue_fact.entity_external_id,
    )


def _interpret_review_issue_fact(
    screen_id: str,
    planning_context_key: Optional[str],
    issue_fact: ReviewApprovalIssueFact,
) -> Optional[ScreenWarningTrustSignal]:
    if issue_fact.fact_type == ISSUE_FACT_TYPE_ACTIVATION_OUTCOME:
        return None

    interpretation_category = (
        INTERPRETATION_CATEGORY_ACTIVATION_BLOCKER
        if issue_fact.fact_type == ISSUE_FACT_TYPE_ACTIVATION_BLOCKER
        else INTERPRETATION_CATEGORY_REVIEW_BLOCKER
    )
    return ScreenWarningTrustSignal(
        signal_id=_stable_id(
            "warning-signal",
            screen_id,
            REVIEW_APPROVAL_SERVICE_NAME,
            issue_fact.fact_id,
            interpretation_category,
            issue_fact.code,
        ),
        screen_id=screen_id,
        source_snapshot_id=issue_fact.source_snapshot_id,
        planning_context_key=planning_context_key,
        signal_type=SIGNAL_TYPE_WARNING,
        severity="blocking",
        code=issue_fact.code,
        message=issue_fact.message,
        advisory=False,
        blocking=True,
        interpretation_category=interpretation_category,
        source_issue_service=REVIEW_APPROVAL_SERVICE_NAME,
        source_fact_id=issue_fact.fact_id,
        source_fact_type=issue_fact.fact_type,
        source_fact_severity=issue_fact.severity,
        entity_type=issue_fact.entity_type,
        entity_id=issue_fact.entity_id,
        entity_external_id=issue_fact.entity_external_id,
    )


def _resolve_source_snapshot_id(
    source_snapshot_id: Optional[str],
    source_issue_facts: List[SourceSetupIssueFact],
    planning_issue_facts: List[PlanningIssueFact],
    review_issue_facts: List[ReviewApprovalIssueFact],
) -> Optional[str]:
    candidate_snapshot_ids = [
        snapshot_id
        for snapshot_id in [
            source_snapshot_id,
            *[issue_fact.source_snapshot_id for issue_fact in source_issue_facts],
            *[issue_fact.source_snapshot_id for issue_fact in planning_issue_facts],
            *[issue_fact.source_snapshot_id for issue_fact in review_issue_facts],
        ]
        if snapshot_id is not None
    ]
    if not candidate_snapshot_ids:
        return None

    resolved_snapshot_id = candidate_snapshot_ids[0]
    for candidate_snapshot_id in candidate_snapshot_ids[1:]:
        if candidate_snapshot_id != resolved_snapshot_id:
            raise ValueError(
                "Warning/trust interpretation requires a single source_snapshot_id."
            )
    return resolved_snapshot_id


def _signal_sort_key(signal: ScreenWarningTrustSignal) -> tuple:
    return (
        0 if signal.blocking else 1,
        signal.interpretation_category or "",
        signal.signal_type,
        signal.code,
        signal.source_issue_service or "",
        signal.entity_type or "",
        signal.entity_id or "",
        signal.entity_external_id or "",
        signal.source_fact_id or "",
        signal.signal_id,
    )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"
