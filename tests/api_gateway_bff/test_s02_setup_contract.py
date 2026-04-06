import json
import unittest
from pathlib import Path

from services.api_gateway_bff.s02_setup_contract import build_s02_setup_contract
from services.decision_support_service import (
    DecisionSupportService,
    ScreenWarningTrustSignal,
)
from services.integration_service.service import IntegrationService
from services.planning_engine_service.service import PlanningEngineService
from services.workflow_orchestrator_service import (
    PlanningEngineExecutionReceipt,
    PlanningEngineGateway,
    PlanningRunTrigger,
    WorkflowOrchestratorService,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class FakePlanningEngineGateway(PlanningEngineGateway):
    def submit_planning_run(self, request):
        return PlanningEngineExecutionReceipt(
            planning_run_id="planning-run-01",
            accepted_at="2026-04-04T12:00:01Z",
        )


class S02SetupContractTests(unittest.TestCase):
    def test_contract_defaults_when_no_import_exists(self):
        contract = build_s02_setup_contract(
            integration_service=IntegrationService(),
            planning_engine_service=PlanningEngineService(),
            decision_support_service=DecisionSupportService(),
        )

        self.assertEqual(contract["screen"], {"id": "S02", "label": "Planning Setup"})
        self.assertEqual(contract["queryContext"], {"planningContextKey": None, "sourceSnapshotId": None})
        self.assertEqual(contract["viewState"]["screenState"], "missing")
        self.assertEqual(contract["sourceReadiness"]["state"], "missing")
        self.assertFalse(contract["sourceReadiness"]["runnable"])
        self.assertEqual(contract["capacityInputReadiness"]["state"], "missing")
        self.assertEqual(contract["overallReadiness"]["state"], "missing")
        self.assertFalse(contract["overallReadiness"]["canContinueToPlanning"])
        self.assertIsNone(contract["latestImport"])
        self.assertIsNone(contract["planningRunStatus"])
        self.assertEqual(contract["noRunnablePlanBlockers"][0]["code"], "missing_normalized_source_snapshot")
        self.assertEqual(
            contract["stubbedDependencies"],
            ["planningRunStatus", "workflowOrchestration"],
        )

    def test_contract_exposes_ready_state_when_source_and_capacity_are_runnable(self):
        integration_service = IntegrationService()
        integration_service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))
        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=PlanningEngineService(),
            decision_support_service=DecisionSupportService(),
        )

        self.assertEqual(contract["sourceReadiness"]["state"], "ready")
        self.assertTrue(contract["sourceReadiness"]["runnable"])
        self.assertEqual(contract["capacityInputReadiness"]["state"], "ready")
        self.assertTrue(contract["capacityInputReadiness"]["runnable"])
        self.assertEqual(contract["viewState"]["screenState"], "ready")
        self.assertEqual(contract["overallReadiness"]["state"], "ready")
        self.assertTrue(contract["overallReadiness"]["runnable"])
        self.assertTrue(contract["overallReadiness"]["canContinueToPlanning"])
        self.assertEqual(contract["latestImport"]["sourceSystem"], "asana")
        self.assertEqual(contract["latestImport"]["projectCount"], 1)
        self.assertEqual(contract["latestImport"]["taskCount"], 1)
        self.assertIsNone(contract["planningRunStatus"])
        self.assertEqual(contract["sourceSetupIssues"], [])
        self.assertEqual(contract["capacityInputIssues"], [])
        self.assertEqual(contract["advisorySignals"], [])
        self.assertEqual(contract["noRunnablePlanBlockers"], [])
        self.assertEqual(contract["stubbedDependencies"], ["planningRunStatus", "workflowOrchestration"])

    def test_contract_marks_partially_configured_when_advisory_warning_exists(self):
        integration_service = IntegrationService()
        bundle = integration_service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))
        planning_engine_service = PlanningEngineService()
        decision_support_service = DecisionSupportService()
        decision_support_service.publish_screen_warning_trust_state(
            screen_id="S02",
            source_snapshot_id=bundle.snapshot.snapshot_id,
            signals=[
                ScreenWarningTrustSignal(
                    signal_id="signal-01",
                    screen_id="S02",
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    planning_context_key=None,
                    signal_type="warning",
                    severity="warning",
                    code="fallback_calendar_inference",
                    message="Capacity used a fallback calendar inference that should be reviewed.",
                    advisory=True,
                )
            ],
        )
        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=planning_engine_service,
            decision_support_service=decision_support_service,
        )

        self.assertEqual(contract["viewState"]["screenState"], "partially_configured")
        self.assertEqual(contract["overallReadiness"]["state"], "ready_with_advisories")
        self.assertTrue(contract["overallReadiness"]["runnable"])
        self.assertTrue(contract["overallReadiness"]["canContinueToPlanning"])
        self.assertEqual(contract["setupWarningTrustState"]["activeSignalCount"], 1)
        self.assertEqual(contract["setupWarningTrustState"]["advisorySignalCount"], 1)
        self.assertEqual(contract["advisorySignals"][0]["ownerService"], "Decision Support Service")
        self.assertEqual(contract["noRunnablePlanBlockers"], [])

    def test_contract_exposes_planning_run_status_for_s02(self):
        integration_service = IntegrationService()
        bundle = integration_service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))
        orchestrator = WorkflowOrchestratorService(
            integration_service=integration_service,
            planning_engine_gateway=FakePlanningEngineGateway(),
        )
        trigger_payload = load_fixture("planning_run_trigger_baseline.json")
        trigger_payload["source_snapshot_id"] = bundle.snapshot.snapshot_id
        orchestrator.start_planning_run(PlanningRunTrigger(**trigger_payload))

        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=PlanningEngineService(),
            decision_support_service=DecisionSupportService(),
            workflow_orchestrator_service=orchestrator,
            planning_context_key=trigger_payload["planning_context_key"],
            snapshot_id=bundle.snapshot.snapshot_id,
        )

        self.assertEqual(contract["planningRunStatus"]["status"], "dispatched")
        self.assertEqual(contract["planningRunStatus"]["planningRunId"], "planning-run-01")
        self.assertEqual(
            contract["planningRunStatus"]["sourceSnapshotId"],
            bundle.snapshot.snapshot_id,
        )
        self.assertEqual(contract["stubbedDependencies"], [])

    def test_contract_exposes_source_issue_state(self):
        integration_service = IntegrationService()
        integration_service.import_source_plan(
            load_fixture("source_plan_invalid_missing_required_fields.json")
        )

        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=PlanningEngineService(),
            decision_support_service=DecisionSupportService(),
        )

        self.assertEqual(contract["sourceReadiness"]["state"], "blocked")
        self.assertFalse(contract["sourceReadiness"]["runnable"])
        self.assertEqual(contract["overallReadiness"]["state"], "blocked")
        self.assertIn(
            "missing_task_name",
            {issue["code"] for issue in contract["sourceSetupIssues"]},
        )
        self.assertIn(
            "Integration Service",
            {issue["ownerService"] for issue in contract["noRunnablePlanBlockers"]},
        )

    def test_contract_exposes_capacity_input_issue_state(self):
        integration_service = IntegrationService()
        integration_service.import_source_plan(
            load_fixture("source_plan_capacity_missing_availability.json")
        )

        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=PlanningEngineService(),
            decision_support_service=DecisionSupportService(),
        )

        self.assertEqual(contract["sourceReadiness"]["state"], "ready")
        self.assertEqual(contract["capacityInputReadiness"]["state"], "blocked")
        self.assertEqual(contract["overallReadiness"]["state"], "blocked")
        self.assertFalse(contract["overallReadiness"]["runnable"])
        self.assertIn(
            "missing_availability_ratio",
            {issue["code"] for issue in contract["capacityInputIssues"]},
        )
        self.assertIn(
            "Planning Engine Service",
            {issue["ownerService"] for issue in contract["noRunnablePlanBlockers"]},
        )

    def test_contract_distinguishes_advisory_warning_from_blocking_state(self):
        integration_service = IntegrationService()
        bundle = integration_service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))
        planning_engine_service = PlanningEngineService()
        decision_support_service = DecisionSupportService()
        decision_support_service.publish_screen_warning_trust_state(
            screen_id="S02",
            source_snapshot_id=bundle.snapshot.snapshot_id,
            planning_context_key="portfolio-alpha",
            signals=[
                ScreenWarningTrustSignal(
                    signal_id="signal-02",
                    screen_id="S02",
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    planning_context_key="portfolio-alpha",
                    signal_type="trust",
                    severity="warning",
                    code="low_planning_confidence",
                    message="Planning confidence is limited because fallback heuristics were used.",
                    advisory=True,
                )
            ],
        )

        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=planning_engine_service,
            decision_support_service=decision_support_service,
            planning_context_key="portfolio-alpha",
            snapshot_id=bundle.snapshot.snapshot_id,
        )

        self.assertTrue(contract["overallReadiness"]["runnable"])
        self.assertTrue(contract["overallReadiness"]["canContinueToPlanning"])
        self.assertEqual(contract["overallReadiness"]["noRunnablePlanBlockerCount"], 0)
        self.assertEqual(contract["overallReadiness"]["advisorySignalCount"], 1)
        self.assertEqual(contract["advisorySignals"][0]["code"], "low_planning_confidence")

    def test_contract_normalizes_non_advisory_decision_support_signals_to_s02_advisories(self):
        integration_service = IntegrationService()
        bundle = integration_service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))
        decision_support_service = DecisionSupportService()
        decision_support_service.publish_screen_warning_trust_state(
            screen_id="S02",
            source_snapshot_id=bundle.snapshot.snapshot_id,
            signals=[
                ScreenWarningTrustSignal(
                    signal_id="signal-04",
                    screen_id="S02",
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    planning_context_key=None,
                    signal_type="trust",
                    severity="warning",
                    code="trust_limited_context",
                    message="The current planning context has limited trust metadata.",
                    advisory=False,
                )
            ],
        )

        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=PlanningEngineService(),
            decision_support_service=decision_support_service,
        )

        self.assertEqual(contract["setupWarningTrustState"]["activeSignalCount"], 1)
        self.assertEqual(contract["setupWarningTrustState"]["advisorySignalCount"], 1)
        self.assertEqual(contract["setupWarningTrustState"]["blockingSignalCount"], 0)
        self.assertTrue(contract["setupWarningTrustState"]["signals"][0]["advisory"])
        self.assertEqual(contract["overallReadiness"]["state"], "ready_with_advisories")
        self.assertTrue(contract["overallReadiness"]["runnable"])

    def test_contract_supports_refresh_view_state(self):
        integration_service = IntegrationService()
        integration_service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))

        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=PlanningEngineService(),
            decision_support_service=DecisionSupportService(),
            is_refreshing=True,
        )

        self.assertTrue(contract["viewState"]["isRefreshing"])
        self.assertEqual(contract["viewState"]["screenState"], "ready")

    def test_contract_supports_access_restricted_view_state(self):
        integration_service = IntegrationService()
        integration_service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))
        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=PlanningEngineService(),
            decision_support_service=DecisionSupportService(),
            access_restricted=True,
            access_restricted_reason="missing_planning_setup_permission",
        )

        self.assertEqual(contract["viewState"]["screenState"], "access_restricted")
        self.assertTrue(contract["viewState"]["accessRestricted"])
        self.assertEqual(
            contract["viewState"]["accessRestrictedReason"],
            "missing_planning_setup_permission",
        )
        self.assertEqual(
            contract["queryContext"],
            {"planningContextKey": None, "sourceSnapshotId": None},
        )
        self.assertIsNone(contract["sourceReadiness"])
        self.assertIsNone(contract["capacityInputReadiness"])
        self.assertIsNone(contract["overallReadiness"])

    def test_stubbed_capacity_path_preserves_advisory_counts(self):
        integration_service = IntegrationService()
        bundle = integration_service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))
        decision_support_service = DecisionSupportService()
        decision_support_service.publish_screen_warning_trust_state(
            screen_id="S02",
            source_snapshot_id=bundle.snapshot.snapshot_id,
            signals=[
                ScreenWarningTrustSignal(
                    signal_id="signal-03",
                    screen_id="S02",
                    source_snapshot_id=bundle.snapshot.snapshot_id,
                    planning_context_key=None,
                    signal_type="warning",
                    severity="warning",
                    code="calendar_review_recommended",
                    message="Calendar assumptions should be reviewed before planning.",
                    advisory=True,
                )
            ],
        )

        contract = build_s02_setup_contract(
            integration_service=integration_service,
            decision_support_service=decision_support_service,
        )

        self.assertEqual(contract["capacityInputReadiness"]["state"], "stubbed")
        self.assertEqual(contract["overallReadiness"]["state"], "ready_with_advisories")
        self.assertEqual(contract["overallReadiness"]["basis"], "source_readiness_only")
        self.assertEqual(contract["overallReadiness"]["advisorySignalCount"], 1)
        self.assertEqual(contract["viewState"]["screenState"], "partially_configured")

    def test_contract_shape_is_stable(self):
        integration_service = IntegrationService()
        integration_service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))

        contract = build_s02_setup_contract(
            integration_service=integration_service,
            planning_engine_service=PlanningEngineService(),
            decision_support_service=DecisionSupportService(),
        )

        self.assertEqual(
            set(contract.keys()),
            {
                "screen",
                "queryContext",
                "viewState",
                "sourceReadiness",
                "capacityInputReadiness",
                "overallReadiness",
                "latestImport",
                "planningRunStatus",
                "sourceSetupIssues",
                "capacityInputIssues",
                "setupWarningTrustState",
                "noRunnablePlanBlockers",
                "advisorySignals",
                "stubbedDependencies",
            },
        )


if __name__ == "__main__":
    unittest.main()
