import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.planning_engine_service.service import PlanningEngineService
from services.review_approval_service import (
    ApprovedOperatingPlanSnapshot,
    ApprovedPlanProjectRecord,
    ApprovedPlanTaskRecord,
    RecommendationOriginReference,
    ReviewApprovalService,
)
from services.workflow_orchestrator_service import (
    ACTIVATION_RECOMPUTATION_STEP,
    ACTIVATION_SIDE_EFFECTS_STEP,
    ActivationExecutionGateway,
    ActivationExecutionGatewayError,
    ActivationExecutionStepReceipt,
    ActivationWorkflowAdmissionError,
    ActivationWriteBackTargetReference,
    ActivationWorkflowTrigger,
    PlanningEngineGateway,
    WorkflowOrchestratorService,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def build_activated_review_context(fixture_name, planning_run_key):
    scenario = load_fixture(fixture_name)
    source_payload = load_fixture(scenario["source_plan_fixture"])
    integration_service = IntegrationService()
    planning_engine_service = PlanningEngineService()
    bundle = integration_service.import_source_plan(source_payload)
    execution_result = planning_engine_service.execute_planning_run(
        bundle=bundle,
        workflow_instance_id=f"workflow::{planning_run_key}",
        planning_context_key=f"context::{planning_run_key}",
        source_snapshot_id=bundle.snapshot.snapshot_id,
        source_artifact_id=bundle.artifact.artifact_id,
        requested_by="review-manager@example.com",
        requested_at="2026-04-06T08:00:00Z",
        attempt_number=1,
    )
    approved_plan_snapshot = ApprovedOperatingPlanSnapshot(
        approved_plan_id=scenario["approved_plan"]["approved_plan_id"],
        projects=[
            ApprovedPlanProjectRecord(
                project_id=project.get("project_id"),
                project_external_id=project["project_external_id"],
                project_name=project["project_name"],
                finish_date=project.get("finish_date"),
            )
            for project in scenario["approved_plan"]["projects"]
        ],
        tasks=[
            ApprovedPlanTaskRecord(
                task_id=task.get("task_id"),
                task_external_id=task["task_external_id"],
                task_name=task["task_name"],
                project_id=task.get("project_id"),
                project_external_id=task["project_external_id"],
                approved_start_date=task.get("approved_start_date"),
                approved_due_date=task.get("approved_due_date"),
                assigned_resource_external_ids=list(
                    task.get("assigned_resource_external_ids", [])
                ),
                item_type=task.get("item_type", "task"),
            )
            for task in scenario["approved_plan"]["tasks"]
        ],
    )
    recommendation_origin_refs = [
        RecommendationOriginReference(
            recommendation_id=item["recommendation_id"],
            origin_screen_id=item["origin_screen_id"],
            project_external_id=item.get("project_external_id"),
            task_external_id=item["task_external_id"],
            requires_review_handoff=item["requires_review_handoff"],
        )
        for item in scenario.get("recommendation_origin_refs", [])
    ]
    review_approval_service = ReviewApprovalService()
    review_context = review_approval_service.generate_reviewable_delta_set(
        execution_result=execution_result,
        approved_plan_snapshot=approved_plan_snapshot,
        recommendation_origin_refs=recommendation_origin_refs,
    )
    requested_delta = next(
        delta
        for delta in review_context.delta_items
        if delta.entity_external_id == "task-rollout"
    )
    review_approval_service.record_delta_acceptance_selection(
        review_context_id=review_context.review_context_id,
        delta_id=requested_delta.delta_id,
        selected=True,
    )
    activation_result = review_approval_service.activate_approved_changes(
        review_context_id=review_context.review_context_id,
        requested_by="approver@example.com",
        requested_at="2026-04-06T10:00:00Z",
    )
    return review_context, activation_result


class UnusedPlanningEngineGateway(PlanningEngineGateway):
    def submit_planning_run(self, request):
        raise AssertionError("Planning Engine gateway should not be used in activation tests.")


class FakeActivationExecutionGateway(ActivationExecutionGateway):
    def __init__(self):
        self.requests = []
        self.fail_next_by_step = {}
        self._request_count = 0

    def submit_step(self, request):
        self.requests.append(request)
        if request.step_name in self.fail_next_by_step:
            error = self.fail_next_by_step.pop(request.step_name)
            raise ActivationExecutionGatewayError(
                code=error["error_code"],
                message=error["error_message"],
            )

        self._request_count += 1
        return ActivationExecutionStepReceipt(
            step_name=request.step_name,
            handoff_id=f"{request.step_name}-hook-{self._request_count:02d}",
            accepted_at=f"2026-04-06T11:00:{self._request_count:02d}Z",
        )


class ActivationWorkflowLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.review_context, self.activation_result = build_activated_review_context(
            "review_approval_delta_simple.json",
            "activation-workflow",
        )
        self.gateway = FakeActivationExecutionGateway()
        self.service = WorkflowOrchestratorService(
            integration_service=IntegrationService(),
            planning_engine_gateway=UnusedPlanningEngineGateway(),
            activation_execution_gateway=self.gateway,
        )

    def _build_trigger(self):
        payload = load_fixture("activation_workflow_trigger_baseline.json")
        return ActivationWorkflowTrigger(
            activation_command_id=self.activation_result.command_id,
            activation_id=self.activation_result.activation_state.activation_id,
            review_context_id=self.review_context.review_context_id,
            approved_plan_id=self.activation_result.activation_state.approved_plan_id_after,
            source_snapshot_id=self.activation_result.downstream_handoff.source_snapshot_id,
            write_back_targets=[
                ActivationWriteBackTargetReference(
                    target_id=target.target_id,
                    delta_id=target.delta_id,
                    entity_type=target.entity_type,
                    entity_external_id=target.entity_external_id,
                    entity_name=target.entity_name,
                    project_external_id=target.project_external_id,
                    write_back_action=target.write_back_action,
                    write_back_fields=list(target.write_back_fields),
                )
                for target in self.activation_result.downstream_handoff.write_back_targets
            ],
            requested_by=payload["requested_by"],
            requested_at=payload["requested_at"],
            idempotency_key=payload["idempotency_key"],
            max_attempts=payload["max_attempts"],
        )

    def test_activation_workflow_start_from_valid_activation_trigger(self):
        result = self.service.start_activation_workflow(self._build_trigger())

        self.assertFalse(result.reused_existing)
        self.assertEqual(result.workflow_instance.current_status, "dispatched")
        self.assertEqual(result.workflow_instance.current_step, ACTIVATION_RECOMPUTATION_STEP)
        self.assertEqual(result.workflow_instance.activation_id, self.activation_result.activation_state.activation_id)
        self.assertEqual(
            result.workflow_instance.source_snapshot_id,
            self.activation_result.downstream_handoff.source_snapshot_id,
        )
        self.assertEqual(len(self.gateway.requests), 1)
        self.assertEqual(self.gateway.requests[0].step_name, ACTIVATION_RECOMPUTATION_STEP)
        self.assertEqual(
            self.gateway.requests[0].source_snapshot_id,
            self.activation_result.downstream_handoff.source_snapshot_id,
        )
        self.assertEqual(
            [target.entity_external_id for target in self.gateway.requests[0].write_back_targets],
            ["task-rollout"],
        )

    def test_activation_workflow_rejects_missing_source_snapshot_id_when_write_back_targets_exist(self):
        trigger = self._build_trigger()
        trigger_without_snapshot = ActivationWorkflowTrigger(
            activation_command_id=trigger.activation_command_id,
            activation_id=trigger.activation_id,
            review_context_id=trigger.review_context_id,
            approved_plan_id=trigger.approved_plan_id,
            source_snapshot_id=None,
            write_back_targets=list(trigger.write_back_targets),
            requested_by=trigger.requested_by,
            requested_at=trigger.requested_at,
            idempotency_key=trigger.idempotency_key,
            max_attempts=trigger.max_attempts,
        )

        with self.assertRaises(ActivationWorkflowAdmissionError) as raised:
            self.service.start_activation_workflow(trigger_without_snapshot)

        self.assertEqual(raised.exception.code, "missing_source_snapshot_id")
        self.assertIn("source_snapshot_id is required", raised.exception.message)
        self.assertEqual(self.gateway.requests, [])

    def test_activation_workflow_allows_write_back_targets_when_source_snapshot_id_is_present(self):
        result = self.service.start_activation_workflow(self._build_trigger())

        self.assertEqual(result.workflow_instance.current_status, "dispatched")
        self.assertEqual(len(self.gateway.requests), 1)
        self.assertEqual(
            self.gateway.requests[0].source_snapshot_id,
            self.activation_result.downstream_handoff.source_snapshot_id,
        )
        self.assertTrue(self.gateway.requests[0].write_back_targets)

    def test_async_status_progression_to_completion(self):
        result = self.service.start_activation_workflow(self._build_trigger())
        workflow_id = result.workflow_instance.workflow_instance_id

        self.service.mark_activation_step_running(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            occurred_at="2026-04-06T11:01:00Z",
        )
        dispatched_next = self.service.mark_activation_step_succeeded(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            occurred_at="2026-04-06T11:02:00Z",
        )
        self.service.mark_activation_step_running(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_SIDE_EFFECTS_STEP,
            occurred_at="2026-04-06T11:03:00Z",
        )
        succeeded = self.service.mark_activation_step_succeeded(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_SIDE_EFFECTS_STEP,
            occurred_at="2026-04-06T11:04:00Z",
        )
        status = self.service.get_activation_workflow_status(
            workflow_instance_id=workflow_id
        )

        self.assertEqual(dispatched_next.current_status, "dispatched")
        self.assertEqual(dispatched_next.current_step, ACTIVATION_SIDE_EFFECTS_STEP)
        self.assertEqual(succeeded.current_status, "succeeded")
        self.assertEqual(status.status, "succeeded")
        self.assertEqual(status.completed_at, "2026-04-06T11:04:00Z")
        self.assertEqual(
            [step.step_name for step in status.step_states],
            [ACTIVATION_RECOMPUTATION_STEP, ACTIVATION_SIDE_EFFECTS_STEP],
        )
        self.assertEqual(
            [step.status for step in status.step_states],
            ["succeeded", "succeeded"],
        )
        self.assertEqual(
            [transition.to_status for transition in self.service.list_activation_workflow_transitions(workflow_id)],
            ["queued", "dispatched", "running", "dispatched", "running", "succeeded"],
        )

    def test_downstream_step_failure_and_retry(self):
        result = self.service.start_activation_workflow(self._build_trigger())
        workflow_id = result.workflow_instance.workflow_instance_id
        failure = load_fixture("activation_workflow_failure_event.json")

        self.service.mark_activation_step_running(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            occurred_at="2026-04-06T11:01:00Z",
        )
        self.gateway.fail_next_by_step[ACTIVATION_SIDE_EFFECTS_STEP] = failure
        retry_pending = self.service.mark_activation_step_succeeded(
            workflow_instance_id=workflow_id,
            step_name=ACTIVATION_RECOMPUTATION_STEP,
            occurred_at="2026-04-06T11:02:00Z",
        )

        self.assertEqual(retry_pending.current_status, "retry_pending")
        self.assertEqual(retry_pending.current_step, ACTIVATION_SIDE_EFFECTS_STEP)
        self.assertEqual(retry_pending.last_error_code, failure["error_code"])
        status_before_retry = self.service.get_activation_workflow_status(
            workflow_instance_id=workflow_id
        )
        self.assertEqual(status_before_retry.step_states[1].status, "retry_pending")
        self.assertEqual(status_before_retry.step_states[1].attempt_number, 1)

        retried = self.service.retry_activation_workflow(
            workflow_instance_id=workflow_id,
            retried_at="2026-04-06T11:05:00Z",
        )
        self.assertEqual(retried.current_status, "dispatched")
        self.assertEqual(retried.current_attempt, 2)
        self.assertEqual(retried.current_step, ACTIVATION_SIDE_EFFECTS_STEP)
        status = self.service.get_activation_workflow_status(workflow_instance_id=workflow_id)
        self.assertEqual(status.step_states[1].status, "dispatched")
        self.assertEqual(status.step_states[1].attempt_number, 2)

    def test_duplicate_trigger_reuses_existing_activation_workflow(self):
        first = self.service.start_activation_workflow(self._build_trigger())
        second = self.service.start_activation_workflow(self._build_trigger())

        self.assertFalse(first.reused_existing)
        self.assertTrue(second.reused_existing)
        self.assertEqual(
            first.workflow_instance.workflow_instance_id,
            second.workflow_instance.workflow_instance_id,
        )
        self.assertEqual(len(self.gateway.requests), 1)

    def test_activation_workflow_status_contract_shape(self):
        result = self.service.start_activation_workflow(self._build_trigger())

        payload = self.service.get_activation_workflow_status(
            workflow_instance_id=result.workflow_instance.workflow_instance_id
        ).to_dict()

        self.assertEqual(
            sorted(payload.keys()),
            [
                "activation_command_id",
                "activation_id",
                "approved_plan_id",
                "completed_at",
                "current_attempt",
                "current_step",
                "last_error_code",
                "last_error_message",
                "last_transition_at",
                "max_attempts",
                "requested_at",
                "requested_by",
                "review_context_id",
                "status",
                "step_states",
                "workflow_instance_id",
            ],
        )
        self.assertEqual(
            sorted(payload["step_states"][0].keys()),
            [
                "attempt_number",
                "handoff_id",
                "last_updated_at",
                "status",
                "step_name",
                "workflow_instance_id",
            ],
        )

    def test_activation_business_truth_is_not_owned_here(self):
        result = self.service.start_activation_workflow(self._build_trigger())
        payload = result.to_dict()

        self.assertNotIn("activation_state", payload)
        self.assertNotIn("resulting_approved_plan_snapshot", payload)
        self.assertEqual(
            payload["workflow_instance"]["approved_plan_id"],
            self.activation_result.activation_state.approved_plan_id_after,
        )
        self.assertEqual(
            payload["workflow_instance"]["activation_id"],
            self.activation_result.activation_state.activation_id,
        )


if __name__ == "__main__":
    unittest.main()
