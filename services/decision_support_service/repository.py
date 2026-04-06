"""In-memory repository for Decision Support warning/trust and recommendation state."""

from typing import Dict, List, Optional, Tuple

from .contracts import (
    RecommendationCandidate,
    RecommendationOriginContext,
    ResourceRecommendationContextState,
    ScreenWarningTrustState,
)


StateKey = Tuple[str, Optional[str], Optional[str]]
RecommendationContextKey = Tuple[str, Optional[str], Optional[str]]


class InMemoryDecisionSupportRepository:
    def __init__(self) -> None:
        self._states_by_key: Dict[StateKey, ScreenWarningTrustState] = {}
        self._save_order: List[StateKey] = []
        self._recommendation_contexts_by_key: Dict[
            RecommendationContextKey, ResourceRecommendationContextState
        ] = {}
        self._recommendation_save_order: List[RecommendationContextKey] = []
        self._recommendation_ids_by_key: Dict[
            RecommendationContextKey, List[str]
        ] = {}
        self._recommendation_candidates_by_id: Dict[str, RecommendationCandidate] = {}

    def save_screen_warning_trust_state(self, state: ScreenWarningTrustState) -> None:
        key = (state.screen_id, state.planning_context_key, state.source_snapshot_id)
        self._states_by_key[key] = state
        self._save_order = [saved_key for saved_key in self._save_order if saved_key != key]
        self._save_order.append(key)

    def get_screen_warning_trust_state(
        self,
        screen_id: str,
        planning_context_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
    ) -> Optional[ScreenWarningTrustState]:
        key = (screen_id, planning_context_key, source_snapshot_id)
        if key in self._states_by_key:
            return self._states_by_key[key]

        for saved_key in reversed(self._save_order):
            saved_screen_id, saved_context_key, saved_snapshot_id = saved_key
            if saved_screen_id != screen_id:
                continue
            if (
                planning_context_key is not None
                and saved_context_key != planning_context_key
            ):
                continue
            if source_snapshot_id is not None and saved_snapshot_id != source_snapshot_id:
                continue
            return self._states_by_key[saved_key]
        return None

    def save_resource_recommendation_context(
        self, state: ResourceRecommendationContextState
    ) -> None:
        key = (
            state.resource_external_id,
            state.planning_context_key,
            state.source_snapshot_id,
        )
        for recommendation_id in self._recommendation_ids_by_key.get(key, []):
            self._recommendation_candidates_by_id.pop(recommendation_id, None)

        self._recommendation_contexts_by_key[key] = state
        self._recommendation_save_order = [
            saved_key
            for saved_key in self._recommendation_save_order
            if saved_key != key
        ]
        self._recommendation_save_order.append(key)
        recommendation_ids: List[str] = []
        for recommendation in state.recommendations:
            self._recommendation_candidates_by_id[
                recommendation.recommendation_id
            ] = recommendation
            recommendation_ids.append(recommendation.recommendation_id)
        self._recommendation_ids_by_key[key] = recommendation_ids

    def get_resource_recommendation_context(
        self,
        resource_external_id: str,
        planning_context_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
    ) -> Optional[ResourceRecommendationContextState]:
        key = (resource_external_id, planning_context_key, source_snapshot_id)
        if key in self._recommendation_contexts_by_key:
            return self._recommendation_contexts_by_key[key]

        for saved_key in reversed(self._recommendation_save_order):
            (
                saved_resource_external_id,
                saved_context_key,
                saved_snapshot_id,
            ) = saved_key
            if saved_resource_external_id != resource_external_id:
                continue
            if (
                planning_context_key is not None
                and saved_context_key != planning_context_key
            ):
                continue
            if source_snapshot_id is not None and saved_snapshot_id != source_snapshot_id:
                continue
            return self._recommendation_contexts_by_key[saved_key]
        return None

    def get_recommendation_candidate(
        self, recommendation_id: str
    ) -> Optional[RecommendationCandidate]:
        return self._recommendation_candidates_by_id.get(recommendation_id)

    def get_recommendation_origin_context(
        self, recommendation_id: str
    ) -> Optional[RecommendationOriginContext]:
        recommendation = self.get_recommendation_candidate(recommendation_id)
        if recommendation is None:
            return None
        return recommendation.origin_context
