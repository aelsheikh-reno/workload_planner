"""In-memory persistence for Workflow Orchestrator workflow/job state."""

from typing import Dict, List, Optional

from .contracts import (
    ACTIVE_WORKFLOW_STATUSES,
    ActivationWorkflowInstance,
    PlanningRunWorkflowInstance,
    WorkflowStepInstance,
    WorkflowTransitionRecord,
)


class InMemoryWorkflowOrchestratorRepository:
    """Persistence seam for workflow/job execution state owned by the Orchestrator."""

    def __init__(self) -> None:
        self._workflow_order: List[str] = []
        self._workflows_by_id: Dict[str, PlanningRunWorkflowInstance] = {}
        self._steps_by_workflow_id: Dict[str, WorkflowStepInstance] = {}
        self._transitions_by_workflow_id: Dict[str, List[WorkflowTransitionRecord]] = {}
        self._activation_workflow_order: List[str] = []
        self._activation_workflows_by_id: Dict[str, ActivationWorkflowInstance] = {}
        self._activation_steps_by_workflow_id: Dict[str, Dict[str, WorkflowStepInstance]] = {}
        self._activation_transitions_by_workflow_id: Dict[
            str, List[WorkflowTransitionRecord]
        ] = {}

    def save_workflow(self, workflow: PlanningRunWorkflowInstance) -> None:
        if workflow.workflow_instance_id not in self._workflows_by_id:
            self._workflow_order.append(workflow.workflow_instance_id)
        self._workflows_by_id[workflow.workflow_instance_id] = workflow

    def get_workflow(
        self, workflow_instance_id: str
    ) -> Optional[PlanningRunWorkflowInstance]:
        return self._workflows_by_id.get(workflow_instance_id)

    def get_latest_workflow(self) -> Optional[PlanningRunWorkflowInstance]:
        if not self._workflow_order:
            return None
        return self._workflows_by_id[self._workflow_order[-1]]

    def get_latest_workflow_for_snapshot(
        self, source_snapshot_id: str
    ) -> Optional[PlanningRunWorkflowInstance]:
        for workflow_instance_id in reversed(self._workflow_order):
            workflow = self._workflows_by_id[workflow_instance_id]
            if workflow.source_snapshot_id == source_snapshot_id:
                return workflow
        return None

    def get_latest_workflow_for_context(
        self, planning_context_key: str
    ) -> Optional[PlanningRunWorkflowInstance]:
        for workflow_instance_id in reversed(self._workflow_order):
            workflow = self._workflows_by_id[workflow_instance_id]
            if workflow.planning_context_key == planning_context_key:
                return workflow
        return None

    def get_latest_workflow_for_context_and_snapshot(
        self, planning_context_key: str, source_snapshot_id: str
    ) -> Optional[PlanningRunWorkflowInstance]:
        for workflow_instance_id in reversed(self._workflow_order):
            workflow = self._workflows_by_id[workflow_instance_id]
            if (
                workflow.planning_context_key == planning_context_key
                and workflow.source_snapshot_id == source_snapshot_id
            ):
                return workflow
        return None

    def find_active_workflow_for_context(
        self, planning_context_key: str, source_snapshot_id: str
    ) -> Optional[PlanningRunWorkflowInstance]:
        for workflow_instance_id in reversed(self._workflow_order):
            workflow = self._workflows_by_id[workflow_instance_id]
            if (
                workflow.planning_context_key == planning_context_key
                and workflow.source_snapshot_id == source_snapshot_id
                and workflow.current_status in ACTIVE_WORKFLOW_STATUSES
            ):
                return workflow
        return None

    def save_step(self, step: WorkflowStepInstance) -> None:
        self._steps_by_workflow_id[step.workflow_instance_id] = step

    def get_step(self, workflow_instance_id: str) -> Optional[WorkflowStepInstance]:
        return self._steps_by_workflow_id.get(workflow_instance_id)

    def append_transition(
        self,
        workflow_instance_id: str,
        from_status: Optional[str],
        to_status: str,
        occurred_at: str,
        reason: str,
    ) -> WorkflowTransitionRecord:
        existing = self._transitions_by_workflow_id.setdefault(workflow_instance_id, [])
        record = WorkflowTransitionRecord(
            workflow_instance_id=workflow_instance_id,
            transition_index=len(existing) + 1,
            from_status=from_status,
            to_status=to_status,
            occurred_at=occurred_at,
            reason=reason,
        )
        existing.append(record)
        return record

    def list_transitions(self, workflow_instance_id: str) -> List[WorkflowTransitionRecord]:
        return list(self._transitions_by_workflow_id.get(workflow_instance_id, []))

    def save_activation_workflow(self, workflow: ActivationWorkflowInstance) -> None:
        if workflow.workflow_instance_id not in self._activation_workflows_by_id:
            self._activation_workflow_order.append(workflow.workflow_instance_id)
        self._activation_workflows_by_id[workflow.workflow_instance_id] = workflow

    def get_activation_workflow(
        self, workflow_instance_id: str
    ) -> Optional[ActivationWorkflowInstance]:
        return self._activation_workflows_by_id.get(workflow_instance_id)

    def get_latest_activation_workflow(self) -> Optional[ActivationWorkflowInstance]:
        if not self._activation_workflow_order:
            return None
        return self._activation_workflows_by_id[self._activation_workflow_order[-1]]

    def get_latest_activation_workflow_for_review_context(
        self, review_context_id: str
    ) -> Optional[ActivationWorkflowInstance]:
        for workflow_instance_id in reversed(self._activation_workflow_order):
            workflow = self._activation_workflows_by_id[workflow_instance_id]
            if workflow.review_context_id == review_context_id:
                return workflow
        return None

    def get_latest_activation_workflow_for_activation(
        self, activation_id: str
    ) -> Optional[ActivationWorkflowInstance]:
        for workflow_instance_id in reversed(self._activation_workflow_order):
            workflow = self._activation_workflows_by_id[workflow_instance_id]
            if workflow.activation_id == activation_id:
                return workflow
        return None

    def find_active_activation_workflow(
        self, activation_id: str
    ) -> Optional[ActivationWorkflowInstance]:
        for workflow_instance_id in reversed(self._activation_workflow_order):
            workflow = self._activation_workflows_by_id[workflow_instance_id]
            if (
                workflow.activation_id == activation_id
                and workflow.current_status in ACTIVE_WORKFLOW_STATUSES
            ):
                return workflow
        return None

    def save_activation_step(self, step: WorkflowStepInstance) -> None:
        steps = self._activation_steps_by_workflow_id.setdefault(
            step.workflow_instance_id, {}
        )
        steps[step.step_name] = step

    def get_activation_step(
        self, workflow_instance_id: str, step_name: str
    ) -> Optional[WorkflowStepInstance]:
        return self._activation_steps_by_workflow_id.get(workflow_instance_id, {}).get(
            step_name
        )

    def list_activation_steps(
        self, workflow_instance_id: str
    ) -> List[WorkflowStepInstance]:
        steps = self._activation_steps_by_workflow_id.get(workflow_instance_id, {})
        return [steps[step_name] for step_name in sorted(steps.keys())]

    def append_activation_transition(
        self,
        workflow_instance_id: str,
        from_status: Optional[str],
        to_status: str,
        occurred_at: str,
        reason: str,
    ) -> WorkflowTransitionRecord:
        existing = self._activation_transitions_by_workflow_id.setdefault(
            workflow_instance_id, []
        )
        record = WorkflowTransitionRecord(
            workflow_instance_id=workflow_instance_id,
            transition_index=len(existing) + 1,
            from_status=from_status,
            to_status=to_status,
            occurred_at=occurred_at,
            reason=reason,
        )
        existing.append(record)
        return record

    def list_activation_transitions(
        self, workflow_instance_id: str
    ) -> List[WorkflowTransitionRecord]:
        return list(self._activation_transitions_by_workflow_id.get(workflow_instance_id, []))
