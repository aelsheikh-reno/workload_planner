"""In-memory persistence for Review & Approval review contexts and issue facts."""

from typing import Dict, List, Optional, Tuple

from .contracts import (
    ActivationState,
    ApprovedOperatingPlanSnapshot,
    ConnectedChangeSetResolution,
    ReviewApprovalIssueFactEmission,
    ReviewContextState,
)


ResolutionKey = Tuple[str, str]


class InMemoryReviewApprovalRepository:
    def __init__(self) -> None:
        self._review_contexts_by_id: Dict[str, ReviewContextState] = {}
        self._review_context_save_order: List[str] = []
        self._approved_plan_snapshots_by_id: Dict[str, ApprovedOperatingPlanSnapshot] = {}
        self._current_approved_plan_id: Optional[str] = None
        self._connected_set_resolutions_by_key: Dict[
            ResolutionKey, ConnectedChangeSetResolution
        ] = {}
        self._resolution_save_order: List[ResolutionKey] = []
        self._blocked_acceptance_attempt_keys: List[ResolutionKey] = []
        self._activation_states_by_id: Dict[str, ActivationState] = {}
        self._activation_ids_by_review_context: Dict[str, str] = {}
        self._activation_save_order: List[str] = []
        self._emissions_by_review_context: Dict[str, ReviewApprovalIssueFactEmission] = {}
        self._emissions_by_activation_id: Dict[str, ReviewApprovalIssueFactEmission] = {}
        self._emission_save_order: List[str] = []

    def save_review_context(self, review_context: ReviewContextState) -> None:
        self._review_contexts_by_id[review_context.review_context_id] = review_context
        self._review_context_save_order = [
            saved_review_context_id
            for saved_review_context_id in self._review_context_save_order
            if saved_review_context_id != review_context.review_context_id
        ]
        self._review_context_save_order.append(review_context.review_context_id)

    def get_review_context(
        self, review_context_id: Optional[str] = None
    ) -> Optional[ReviewContextState]:
        if review_context_id is not None:
            return self._review_contexts_by_id.get(review_context_id)
        if not self._review_context_save_order:
            return None
        return self._review_contexts_by_id[self._review_context_save_order[-1]]

    def save_approved_plan_snapshot(
        self,
        approved_plan_snapshot: ApprovedOperatingPlanSnapshot,
        *,
        set_current: bool = False,
    ) -> None:
        self._approved_plan_snapshots_by_id[
            approved_plan_snapshot.approved_plan_id
        ] = approved_plan_snapshot
        if set_current:
            self._current_approved_plan_id = approved_plan_snapshot.approved_plan_id

    def get_approved_plan_snapshot(
        self,
        approved_plan_id: Optional[str] = None,
        *,
        current: bool = False,
    ) -> Optional[ApprovedOperatingPlanSnapshot]:
        if current:
            if self._current_approved_plan_id is None:
                return None
            return self._approved_plan_snapshots_by_id.get(self._current_approved_plan_id)
        if approved_plan_id is None:
            return None
        return self._approved_plan_snapshots_by_id.get(approved_plan_id)

    def save_connected_set_resolution(
        self, resolution: ConnectedChangeSetResolution
    ) -> None:
        key = (resolution.review_context_id, resolution.requested_delta_id)
        self._connected_set_resolutions_by_key[key] = resolution
        self._resolution_save_order = [
            saved_key for saved_key in self._resolution_save_order if saved_key != key
        ]
        self._resolution_save_order.append(key)

    def get_connected_set_resolution(
        self,
        review_context_id: Optional[str] = None,
        requested_delta_id: Optional[str] = None,
    ) -> Optional[ConnectedChangeSetResolution]:
        if review_context_id is not None and requested_delta_id is not None:
            return self._connected_set_resolutions_by_key.get(
                (review_context_id, requested_delta_id)
            )
        if not self._resolution_save_order:
            return None
        for saved_review_context_id, saved_delta_id in reversed(self._resolution_save_order):
            if review_context_id is not None and saved_review_context_id != review_context_id:
                continue
            if requested_delta_id is not None and saved_delta_id != requested_delta_id:
                continue
            return self._connected_set_resolutions_by_key[
                (saved_review_context_id, saved_delta_id)
            ]
        return None

    def list_connected_set_resolutions(
        self,
        review_context_id: Optional[str] = None,
    ) -> List[ConnectedChangeSetResolution]:
        resolutions: List[ConnectedChangeSetResolution] = []
        for saved_review_context_id, saved_delta_id in self._resolution_save_order:
            if review_context_id is not None and saved_review_context_id != review_context_id:
                continue
            resolutions.append(
                self._connected_set_resolutions_by_key[
                    (saved_review_context_id, saved_delta_id)
                ]
            )
        return resolutions

    def save_blocked_acceptance_attempt(
        self,
        resolution: ConnectedChangeSetResolution,
    ) -> None:
        key = (resolution.review_context_id, resolution.requested_delta_id)
        self._blocked_acceptance_attempt_keys = [
            saved_key
            for saved_key in self._blocked_acceptance_attempt_keys
            if saved_key != key
        ]
        self._blocked_acceptance_attempt_keys.append(key)

    def list_blocked_acceptance_attempts(
        self,
        review_context_id: Optional[str] = None,
    ) -> List[ConnectedChangeSetResolution]:
        resolutions: List[ConnectedChangeSetResolution] = []
        for saved_review_context_id, saved_delta_id in self._blocked_acceptance_attempt_keys:
            if review_context_id is not None and saved_review_context_id != review_context_id:
                continue
            resolution = self._connected_set_resolutions_by_key.get(
                (saved_review_context_id, saved_delta_id)
            )
            if resolution is not None:
                resolutions.append(resolution)
        return resolutions

    def clear_blocked_acceptance_attempts(
        self,
        review_context_id: str,
        requested_delta_ids: List[str],
    ) -> None:
        requested_delta_id_set = set(requested_delta_ids)
        self._blocked_acceptance_attempt_keys = [
            saved_key
            for saved_key in self._blocked_acceptance_attempt_keys
            if not (
                saved_key[0] == review_context_id
                and saved_key[1] in requested_delta_id_set
            )
        ]

    def save_activation_state(self, activation_state: ActivationState) -> None:
        self._activation_states_by_id[activation_state.activation_id] = activation_state
        if activation_state.review_context_id is not None:
            self._activation_ids_by_review_context[
                activation_state.review_context_id
            ] = activation_state.activation_id
        self._activation_save_order = [
            saved_activation_id
            for saved_activation_id in self._activation_save_order
            if saved_activation_id != activation_state.activation_id
        ]
        self._activation_save_order.append(activation_state.activation_id)

    def get_activation_state(
        self,
        *,
        review_context_id: Optional[str] = None,
        activation_id: Optional[str] = None,
    ) -> Optional[ActivationState]:
        if activation_id is not None:
            return self._activation_states_by_id.get(activation_id)
        if review_context_id is not None:
            saved_activation_id = self._activation_ids_by_review_context.get(review_context_id)
            if saved_activation_id is None:
                return None
            return self._activation_states_by_id.get(saved_activation_id)
        if not self._activation_save_order:
            return None
        return self._activation_states_by_id[self._activation_save_order[-1]]

    def save_issue_fact_emission(self, emission: ReviewApprovalIssueFactEmission) -> None:
        self._emissions_by_review_context[emission.review_context_id] = emission
        if emission.activation_id is not None:
            self._emissions_by_activation_id[emission.activation_id] = emission
        self._emission_save_order = [
            review_context_id
            for review_context_id in self._emission_save_order
            if review_context_id != emission.review_context_id
        ]
        self._emission_save_order.append(emission.review_context_id)

    def get_issue_fact_emission(
        self,
        review_context_id: Optional[str] = None,
        activation_id: Optional[str] = None,
    ) -> Optional[ReviewApprovalIssueFactEmission]:
        if activation_id is not None and activation_id in self._emissions_by_activation_id:
            return self._emissions_by_activation_id[activation_id]
        if review_context_id is not None:
            return self._emissions_by_review_context.get(review_context_id)
        if not self._emission_save_order:
            return None
        return self._emissions_by_review_context[self._emission_save_order[-1]]
