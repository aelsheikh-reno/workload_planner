"""In-memory repository for Planning Engine capacity and draft scheduling outputs."""

from typing import Dict, Optional

from .contracts import (
    CapacityModelResult,
    DraftScheduleResult,
    PlanningDiagnosticsResult,
    PlanningRunExecutionResult,
)


class InMemoryPlanningEngineRepository:
    def __init__(self) -> None:
        self._capacity_results_by_snapshot_id: Dict[str, CapacityModelResult] = {}
        self._latest_capacity_snapshot_id: Optional[str] = None
        self._draft_results_by_planning_run_id: Dict[str, DraftScheduleResult] = {}
        self._diagnostics_results_by_planning_run_id: Dict[
            str, PlanningDiagnosticsResult
        ] = {}
        self._latest_planning_run_id: Optional[str] = None
        self._execution_results_by_planning_run_id: Dict[
            str, PlanningRunExecutionResult
        ] = {}

    def save_capacity_model(self, result: CapacityModelResult) -> None:
        self._capacity_results_by_snapshot_id[result.source_snapshot_id] = result
        self._latest_capacity_snapshot_id = result.source_snapshot_id

    def get_capacity_model(
        self, source_snapshot_id: Optional[str] = None
    ) -> Optional[CapacityModelResult]:
        if source_snapshot_id is None:
            if self._latest_capacity_snapshot_id is None:
                return None
            return self._capacity_results_by_snapshot_id.get(
                self._latest_capacity_snapshot_id
            )
        return self._capacity_results_by_snapshot_id.get(source_snapshot_id)

    def save_draft_schedule(self, result: DraftScheduleResult) -> None:
        self._draft_results_by_planning_run_id[result.planning_run_id] = result
        self._latest_planning_run_id = result.planning_run_id

    def get_draft_schedule(
        self, planning_run_id: Optional[str] = None
    ) -> Optional[DraftScheduleResult]:
        if planning_run_id is None:
            if self._latest_planning_run_id is None:
                return None
            return self._draft_results_by_planning_run_id.get(
                self._latest_planning_run_id
            )
        return self._draft_results_by_planning_run_id.get(planning_run_id)

    def save_diagnostics_result(self, result: PlanningDiagnosticsResult) -> None:
        self._diagnostics_results_by_planning_run_id[result.planning_run_id] = result
        self._latest_planning_run_id = result.planning_run_id

    def get_diagnostics_result(
        self, planning_run_id: Optional[str] = None
    ) -> Optional[PlanningDiagnosticsResult]:
        if planning_run_id is None:
            if self._latest_planning_run_id is None:
                return None
            return self._diagnostics_results_by_planning_run_id.get(
                self._latest_planning_run_id
            )
        return self._diagnostics_results_by_planning_run_id.get(planning_run_id)

    def save_execution_result(self, result: PlanningRunExecutionResult) -> None:
        self._execution_results_by_planning_run_id[
            result.execution_record.planning_run_id
        ] = result
        self._latest_planning_run_id = result.execution_record.planning_run_id

    def get_execution_result(
        self, planning_run_id: Optional[str] = None
    ) -> Optional[PlanningRunExecutionResult]:
        if planning_run_id is None:
            if self._latest_planning_run_id is None:
                return None
            return self._execution_results_by_planning_run_id.get(
                self._latest_planning_run_id
            )
        return self._execution_results_by_planning_run_id.get(planning_run_id)
