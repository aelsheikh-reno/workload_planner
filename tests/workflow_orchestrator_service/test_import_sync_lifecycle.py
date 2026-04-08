import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.workflow_orchestrator_service import (
    ImportSyncExecutionGateway,
    ImportSyncExecutionGatewayError,
    ImportSyncExecutionReceipt,
    ImportSyncTrigger,
    PlanningEngineGateway,
    WorkflowOrchestratorService,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class UnusedPlanningEngineGateway(PlanningEngineGateway):
    def submit_planning_run(self, request):
        raise AssertionError("Planning Engine should not be called for import/sync tests.")


class FakeImportSyncExecutionGateway(ImportSyncExecutionGateway):
    def __init__(self):
        self.requests = []
        self.fail_next = None

    def submit_import_sync(self, request):
        self.requests.append(request)
        if self.fail_next is not None:
            error = self.fail_next
            self.fail_next = None
            raise ImportSyncExecutionGatewayError(
                code=error["error_code"],
                message=error["error_message"],
            )
        return ImportSyncExecutionReceipt(
            handoff_id="import-sync-handoff-%02d" % len(self.requests),
            accepted_at=request.requested_at,
        )


class ImportSyncLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.integration_service = IntegrationService()
        self.gateway = FakeImportSyncExecutionGateway()
        self.service = WorkflowOrchestratorService(
            integration_service=self.integration_service,
            planning_engine_gateway=UnusedPlanningEngineGateway(),
            import_sync_execution_gateway=self.gateway,
        )

    def test_import_sync_start_creates_dispatched_workflow_and_handoff(self):
        result = self.service.start_import_sync(
            ImportSyncTrigger(
                raw_payload=load_fixture("source_plan_valid.json"),
                requested_by="planner@example.com",
                requested_at="2026-04-07T09:00:00Z",
                idempotency_key="import-sync::happy-path",
            )
        )

        self.assertFalse(result.reused_existing)
        self.assertEqual(result.workflow_instance.workflow_type, "import_sync")
        self.assertEqual(result.workflow_instance.current_status, "dispatched")
        self.assertIsNone(result.source_snapshot_id)
        self.assertIsNone(result.source_readiness)
        self.assertIsNotNone(result.handoff_request)
        self.assertEqual(result.handoff_request.source_system, "asana")
        self.assertEqual(result.handoff_request.attempt_number, 1)
        self.assertEqual(len(self.gateway.requests), 1)
        self.assertEqual(self.gateway.requests[0].workflow_instance_id, result.workflow_instance.workflow_instance_id)
        self.assertIsNone(self.integration_service.get_normalized_source_bundle())
        transitions = self.service.list_import_sync_transitions(
            result.workflow_instance.workflow_instance_id
        )
        self.assertEqual(
            [transition.to_status for transition in transitions],
            ["queued", "dispatched"],
        )

    def test_import_sync_start_reuses_existing_idempotent_workflow(self):
        first = self.service.start_import_sync(
            ImportSyncTrigger(
                raw_payload=load_fixture("source_plan_valid.json"),
                requested_by="planner@example.com",
                requested_at="2026-04-07T09:00:00Z",
                idempotency_key="import-sync::reuse",
            )
        )
        second = self.service.start_import_sync(
            ImportSyncTrigger(
                raw_payload=load_fixture("source_plan_valid.json"),
                requested_by="planner@example.com",
                requested_at="2026-04-07T09:01:00Z",
                idempotency_key="import-sync::reuse",
            )
        )

        self.assertFalse(first.reused_existing)
        self.assertTrue(second.reused_existing)
        self.assertEqual(
            first.workflow_instance.workflow_instance_id,
            second.workflow_instance.workflow_instance_id,
        )
        self.assertEqual(first.source_snapshot_id, second.source_snapshot_id)
        self.assertEqual(len(self.gateway.requests), 1)

    def test_import_sync_handoff_failure_returns_failed_workflow(self):
        self.gateway.fail_next = {
            "error_code": "integration_import_sync_unavailable",
            "error_message": "Integration import/sync handoff is unavailable.",
        }

        result = self.service.start_import_sync(
            ImportSyncTrigger(
                raw_payload=load_fixture("source_plan_valid.json"),
                requested_by="planner@example.com",
                requested_at="2026-04-07T09:00:00Z",
                idempotency_key="import-sync::failure",
            )
        )

        self.assertEqual(result.workflow_instance.current_status, "failed")
        self.assertEqual(
            result.workflow_instance.last_error_code,
            "integration_import_sync_unavailable",
        )
        self.assertIsNotNone(result.handoff_request)
        transitions = self.service.list_import_sync_transitions(
            result.workflow_instance.workflow_instance_id
        )
        self.assertEqual([transition.to_status for transition in transitions], ["queued", "failed"])


if __name__ == "__main__":
    unittest.main()
