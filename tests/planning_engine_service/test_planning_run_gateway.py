import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService
from services.planning_engine_service import (
    PlanningEngineService,
    PlanningEngineWorkflowGateway,
)
from services.workflow_orchestrator_service import PlanningEngineExecutionRequest


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class PlanningEngineWorkflowGatewayTests(unittest.TestCase):
    def test_gateway_executes_planning_run_from_orchestrator_handoff_contract(self):
        integration_service = IntegrationService()
        bundle = integration_service.import_source_plan(
            load_fixture("source_plan_schedule_happy_path.json")
        )
        planning_engine_service = PlanningEngineService()
        gateway = PlanningEngineWorkflowGateway(
            integration_service=integration_service,
            planning_engine_service=planning_engine_service,
        )

        request = PlanningEngineExecutionRequest(
            workflow_instance_id="workflow_01",
            planning_context_key="project-schedule-happy::baseline-plan",
            source_snapshot_id=bundle.snapshot.snapshot_id,
            source_artifact_id=bundle.artifact.artifact_id,
            requested_by="delivery-manager@example.com",
            requested_at="2026-04-04T12:30:00Z",
            attempt_number=1,
        )

        receipt = gateway.submit_planning_run(request)
        execution_result = planning_engine_service.get_execution_result(
            planning_run_id=receipt.planning_run_id
        )

        self.assertEqual(receipt.accepted_at, "2026-04-04T12:30:00Z")
        self.assertIsNotNone(execution_result)
        self.assertEqual(
            execution_result.execution_record.workflow_instance_id,
            "workflow_01",
        )
        self.assertEqual(
            execution_result.execution_record.planning_context_key,
            "project-schedule-happy::baseline-plan",
        )
        self.assertEqual(
            execution_result.draft_schedule_result.schedule_state,
            "scheduled",
        )
        self.assertEqual(
            execution_result.draft_schedule_result.source_snapshot_id,
            bundle.snapshot.snapshot_id,
        )
        self.assertEqual(
            execution_result.diagnostics_result.planning_run_id,
            receipt.planning_run_id,
        )
        self.assertEqual(
            execution_result.diagnostics_result.comparison_context,
            "source_baseline_only",
        )


if __name__ == "__main__":
    unittest.main()
