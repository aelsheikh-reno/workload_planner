"""Decision Support contracts for warning/trust and recommendation state."""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


WARNING_TRUST_LIFECYCLE_STATE_CURRENT = "current"
RECOMMENDATION_CONTEXT_STATE_AVAILABLE = "available"
RECOMMENDATION_CONTEXT_STATE_NO_ACTIONABLE = "no_actionable_recommendations"
RECOMMENDATION_CONTEXT_STATE_NOT_AVAILABLE = "not_available"

RECOMMENDATION_FRESHNESS_FRESH = "fresh"
RECOMMENDATION_FRESHNESS_STALE = "stale"
RECOMMENDATION_FRESHNESS_NOT_GENERATED = "not_generated"

RECOMMENDATION_ACTION_FAMILY_RECHUNK = "rechunk"
RECOMMENDATION_ACTION_FAMILY_MOVE_DEFER = "move_defer"
RECOMMENDATION_ACTION_FAMILY_REASSIGNMENT = "reassignment"
RECOMMENDATION_ACTION_FAMILY_DATE_EXTENSION = "date_extension"

RECOMMENDATION_ACTION_FAMILY_ORDER = {
    RECOMMENDATION_ACTION_FAMILY_RECHUNK: 0,
    RECOMMENDATION_ACTION_FAMILY_MOVE_DEFER: 1,
    RECOMMENDATION_ACTION_FAMILY_REASSIGNMENT: 2,
    RECOMMENDATION_ACTION_FAMILY_DATE_EXTENSION: 3,
}

RECOMMENDATION_RANKING_POLICY_MVP_V1 = "locked_mvp_v1"

SIGNAL_TYPE_WARNING = "warning"
SIGNAL_TYPE_TRUST = "trust"

INTERPRETATION_CATEGORY_SETUP_BLOCKER = "setup_blocker"
INTERPRETATION_CATEGORY_SETUP_WARNING = "setup_warning"
INTERPRETATION_CATEGORY_ADVISORY_WARNING = "advisory_warning"
INTERPRETATION_CATEGORY_TRUST_LIMITED = "trust_limited"
INTERPRETATION_CATEGORY_REVIEW_BLOCKER = "review_blocker"
INTERPRETATION_CATEGORY_ACTIVATION_BLOCKER = "activation_blocker"


@dataclass(frozen=True)
class ScreenWarningTrustSignal:
    signal_id: str
    screen_id: str
    source_snapshot_id: Optional[str]
    planning_context_key: Optional[str]
    signal_type: str
    severity: str
    code: str
    message: str
    advisory: bool
    blocking: bool = False
    interpretation_category: Optional[str] = None
    lifecycle_state: str = WARNING_TRUST_LIFECYCLE_STATE_CURRENT
    source_issue_service: Optional[str] = None
    source_fact_id: Optional[str] = None
    source_fact_type: Optional[str] = None
    source_fact_severity: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    entity_external_id: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScreenWarningTrustState:
    interpretation_id: str
    screen_id: str
    source_snapshot_id: Optional[str]
    planning_context_key: Optional[str]
    lifecycle_state: str
    active_signal_count: int
    advisory_signal_count: int
    blocking_signal_count: int
    warning_signal_count: int
    trust_signal_count: int
    trust_limited_signal_count: int
    total_input_fact_count: int
    interpreted_signal_count: int
    signals: List[ScreenWarningTrustSignal]

    def to_dict(self) -> Dict[str, object]:
        return {
            "interpretation_id": self.interpretation_id,
            "screen_id": self.screen_id,
            "source_snapshot_id": self.source_snapshot_id,
            "planning_context_key": self.planning_context_key,
            "lifecycle_state": self.lifecycle_state,
            "active_signal_count": self.active_signal_count,
            "advisory_signal_count": self.advisory_signal_count,
            "blocking_signal_count": self.blocking_signal_count,
            "warning_signal_count": self.warning_signal_count,
            "trust_signal_count": self.trust_signal_count,
            "trust_limited_signal_count": self.trust_limited_signal_count,
            "total_input_fact_count": self.total_input_fact_count,
            "interpreted_signal_count": self.interpreted_signal_count,
            "signals": [signal.to_dict() for signal in self.signals],
        }


@dataclass(frozen=True)
class RecommendationOriginContext:
    origin_screen_id: str
    planning_run_id: str
    draft_schedule_id: str
    diagnostics_id: str
    planning_context_key: Optional[str]
    source_snapshot_id: Optional[str]
    resource_id: Optional[str]
    resource_external_id: str
    task_id: str
    task_external_id: str
    trigger_issue_fact_ids: List[str]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RecommendationCandidate:
    recommendation_id: str
    resource_id: Optional[str]
    resource_external_id: str
    planning_context_key: Optional[str]
    source_snapshot_id: Optional[str]
    title: str
    summary: str
    action_family: str
    priority_rank: int
    requires_review: bool
    rationale: Optional[str]
    affected_task_ids: List[str]
    affected_task_external_ids: List[str]
    effect_summary: Optional[str] = None
    ranking_score: int = 0
    disruption_score: int = 0
    handoff_overhead_score: int = 0
    origin_context: Optional[RecommendationOriginContext] = None
    ranking_policy: str = RECOMMENDATION_RANKING_POLICY_MVP_V1
    trigger_issue_fact_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ResourceRecommendationContextState:
    context_id: str
    resource_id: Optional[str]
    resource_external_id: str
    planning_context_key: Optional[str]
    source_snapshot_id: Optional[str]
    state: str
    freshness_status: str
    actionable_recommendation_count: int
    total_recommendation_count: int
    recommendations: List[RecommendationCandidate]

    def to_dict(self) -> Dict[str, object]:
        return {
            "context_id": self.context_id,
            "resource_id": self.resource_id,
            "resource_external_id": self.resource_external_id,
            "planning_context_key": self.planning_context_key,
            "source_snapshot_id": self.source_snapshot_id,
            "state": self.state,
            "freshness_status": self.freshness_status,
            "actionable_recommendation_count": self.actionable_recommendation_count,
            "total_recommendation_count": self.total_recommendation_count,
            "recommendations": [
                recommendation.to_dict()
                for recommendation in self.recommendations
            ],
        }
