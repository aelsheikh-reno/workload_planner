import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.workflow_orchestrator_service import (
    PlanningEngineExecutionReceipt,
    PlanningEngineGateway,
    PlanningEngineGatewayError,
    PlanningRunAdmissionError,
    PlanningRunTrigger,
    WorkflowOrchestratorService,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class FakePlanningEngineGateway(PlanningEngineGateway):
    def __init__(self):
        self.requests = []
        self.fail_next = None
        self.run_counter = 0

    def submit_planning_run(self, request):
        self.requests.append(request)
        if self.fail_next is not None:
            error = self.fail_next
            self.fail_next = None
            raise PlanningEngineGatewayError(
                code=error["error_code"],
                message=error["error_message"],
            )

        self.run_counter += 1
        return PlanningEngineExecutionReceipt(
            planning_run_id="planning-run-%02d" % self.run_counter,
            accepted_at="2026-04-04T12:00:%02dZ" % self.run_counter,
        )


class PlanningRunLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.integration_service = IntegrationService()
        self.bundle = self.integration_service.import_source_plan(
            load_fixture("source_plan_valid.json")
        )
        self.gateway = FakePlanningEngineGateway()
        self.service = WorkflowOrchestratorService(
            integration_service=self.integration_service,
            planning_engine_gateway=self.gateway,
        )

    def _build_trigger(self):
        payload = load_fixture("planning_run_trigger_baseline.json")
        payload["source_snapshot_id"] = self.bundle.snapshot.snapshot_id
        return PlanningRunTrigger(**payload)

    def test_run_creation(self):
        result = self.service.start_planning_run(self._build_trigger())

        self.assertFalse(result.reused_existing)
        self.assertEqual(result.workflow_instance.current_status, "dispatched")
        self.assertEqual(
            result.workflow_instance.source_snapshot_id, self.bundle.snapshot.snapshot_id
        )
        self.assertEqual(result.workflow_instance.planning_engine_run_id, "planning-run-01")
        self.assertEqual(len(self.gateway.requests), 1)

    def test_handoff_payload_shape_and_values(self):
        self.service.start_planning_run(self._build_trigger())

        self.assertEqual(len(self.gateway.requests), 1)
        self.assertEqual(
            self.gateway.requests[0].to_dict(),
            {
                "workflow_instance_id": self.service.get_planning_run_status(
                    planning_context_key="project-apollo::baseline-plan",
                    source_snapshot_id=self.bundle.snapshot.snapshot_id,
                ).workflow_instance_id,
                "planning_context_key": "project-apollo::baseline-plan",
                "source_snapshot_id": self.bundle.snapshot.snapshot_id,
                "source_artifact_id": self.bundle.artifact.artifact_id,
                "requested_by": "delivery-manager@example.com",
                "requested_at": "2026-04-04T12:00:00Z",
                "attempt_number": 1,
            },
        )

    def test_valid_transition_sequence(self):
        result = self.service.start_planning_run(self._build_trigger())
        workflow_id = result.workflow_instance.workflow_instance_id

        running = self.service.mark_planning_run_running(
            workflow_instance_id=workflow_id,
            occurred_at="2026-04-04T12:03:00Z",
        )
        succeeded = self.service.mark_planning_run_succeeded(
            workflow_instance_id=workflow_id,
            occurred_at="2026-04-04T12:04:00Z",
        )

        self.assertEqual(running.current_status, "running")
        self.assertEqual(succeeded.current_status, "succeeded")
        self.assertEqual(succeeded.completed_at, "2026-04-04T12:04:00Z")
        transitions = self.service.list_workflow_transitions(workflow_id)
        self.assertEqual(
            [transition.to_status for transition in transitions],
            ["queued", "dispatched", "running", "succeeded"],
        )

    def test_failed_run_transition_and_retry(self):
        result = self.service.start_planning_run(self._build_trigger())
        workflow_id = result.workflow_instance.workflow_instance_id
        failure_event = load_fixture("planning_run_failure_event.json")

        retry_pending = self.service.mark_planning_run_failed(
            workflow_instance_id=workflow_id,
            occurred_at=failure_event["occurred_at"],
            error_code=failure_event["error_code"],
            error_message=failure_event["error_message"],
            retryable=failure_event["retryable"],
        )

        self.assertEqual(retry_pending.current_status, "retry_pending")
        retried = self.service.retry_planning_run(
            workflow_instance_id=workflow_id,
            retried_at="2026-04-04T12:05:00Z",
        )
        self.assertEqual(retried.current_status, "dispatched")
        self.assertEqual(retried.current_attempt, 2)
        self.assertEqual(retried.planning_engine_run_id, "planning-run-02")

    def test_failed_run_transition_without_retry(self):
        result = self.service.start_planning_run(self._build_trigger())
        workflow_id = result.workflow_instance.workflow_instance_id

        failed = self.service.mark_planning_run_failed(
            workflow_instance_id=workflow_id,
            occurred_at="2026-04-04T12:02:30Z",
            error_code="planning_engine_rejected",
            error_message="Planning Engine rejected the request.",
            retryable=False,
        )

        self.assertEqual(failed.current_status, "failed")
        self.assertEqual(failed.completed_at, "2026-04-04T12:02:30Z")
        self.assertEqual(failed.last_error_code, "planning_engine_rejected")

    def test_duplicate_trigger_idempotency_handling(self):
        first = self.service.start_planning_run(self._build_trigger())
        second = self.service.start_planning_run(self._build_trigger())

        self.assertFalse(first.reused_existing)
        self.assertTrue(second.reused_existing)
        self.assertEqual(
            first.workflow_instance.workflow_instance_id,
            second.workflow_instance.workflow_instance_id,
        )
        self.assertEqual(len(self.gateway.requests), 1)

    def test_handoff_failure_moves_to_retry_pending_when_attempts_remain(self):
        self.gateway.fail_next = load_fixture("planning_run_failure_event.json")

        result = self.service.start_planning_run(self._build_trigger())

        self.assertEqual(result.workflow_instance.current_status, "retry_pending")
        self.assertEqual(
            result.workflow_instance.last_error_code, "planning_engine_unavailable"
        )
        transitions = self.service.list_workflow_transitions(
            result.workflow_instance.workflow_instance_id
        )
        self.assertEqual(
            [transition.to_status for transition in transitions],
            ["queued", "retry_pending"],
        )

    def test_missing_snapshot_rejection(self):
        trigger_payload = load_fixture("planning_run_trigger_baseline.json")
        trigger_payload["source_snapshot_id"] = "snapshot_missing"

        with self.assertRaises(PlanningRunAdmissionError) as raised:
            self.service.start_planning_run(PlanningRunTrigger(**trigger_payload))

        self.assertEqual(raised.exception.code, "missing_normalized_source_snapshot")

    def test_non_runnable_snapshot_rejection(self):
        blocked_integration_service = IntegrationService()
        blocked_bundle = blocked_integration_service.import_source_plan(
            load_fixture("source_plan_invalid_missing_required_fields.json")
        )
        blocked_service = WorkflowOrchestratorService(
            integration_service=blocked_integration_service,
            planning_engine_gateway=FakePlanningEngineGateway(),
        )
        trigger_payload = load_fixture("planning_run_trigger_baseline.json")
        trigger_payload["source_snapshot_id"] = blocked_bundle.snapshot.snapshot_id

        with self.assertRaises(PlanningRunAdmissionError) as raised:
            blocked_service.start_planning_run(PlanningRunTrigger(**trigger_payload))

        self.assertEqual(raised.exception.code, "source_not_runnable")


if __name__ == "__main__":
    unittest.main()
