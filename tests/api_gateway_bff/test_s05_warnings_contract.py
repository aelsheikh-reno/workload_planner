import json
import unittest
from pathlib import Path

from services.api_gateway_bff.s05_warnings_contract import (
    build_s05_warnings_workspace_contract,
)
from services.decision_support_service import (
    DecisionSupportService,
    ScreenWarningTrustSignal,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def publish_fixture(decision_support_service, fixture_name):
    payload = load_fixture(fixture_name)
    state = decision_support_service.publish_screen_warning_trust_state(
        screen_id=payload["screen_id"],
        planning_context_key=payload.get("planning_context_key"),
        source_snapshot_id=payload.get("source_snapshot_id"),
        signals=[
            ScreenWarningTrustSignal(**signal_payload)
            for signal_payload in payload.get("signals", [])
        ],
    )
    return payload, state


class S05WarningsWorkspaceContractTests(unittest.TestCase):
    def test_s05_normal_warning_review_state(self):
        decision_support_service = DecisionSupportService()
        payload, _ = publish_fixture(
            decision_support_service,
            "decision_support_s05_workspace_normal.json",
        )

        contract = build_s05_warnings_workspace_contract(
            decision_support_service=decision_support_service,
            planning_context_key=payload["planning_context_key"],
            source_snapshot_id=payload["source_snapshot_id"],
        )

        self.assertEqual(
            contract["screen"],
            {"id": "S05", "label": "Planning Warnings Workspace"},
        )
        self.assertEqual(contract["viewState"]["screenState"], "ready")
        self.assertEqual(contract["workspaceSummary"]["filteredSignalCount"], 3)
        self.assertEqual(contract["workspaceSummary"]["blockingWarningCount"], 1)
        self.assertEqual(contract["workspaceSummary"]["advisoryWarningCount"], 1)
        self.assertEqual(contract["workspaceSummary"]["trustLimitedCount"], 1)
        self.assertEqual(contract["workspaceSummary"]["affectedWorkflowCount"], 3)
        self.assertTrue(contract["workspaceSummary"]["oneListPresentation"])
        self.assertEqual(
            [summary["workflowId"] for summary in contract["groupSummaries"]],
            ["S01", "S02", "S03"],
        )
        self.assertEqual(len(contract["trustGuidance"]), 1)
        self.assertIsNone(contract["returnNavigation"])

    def test_s05_no_warning_state(self):
        contract = build_s05_warnings_workspace_contract(
            decision_support_service=DecisionSupportService(),
            planning_context_key="portfolio-warnings-empty",
            source_snapshot_id="source-snapshot-warnings-empty",
        )

        self.assertEqual(contract["viewState"]["screenState"], "no_warnings")
        self.assertEqual(contract["warningItems"], [])
        self.assertEqual(
            contract["emptyState"]["reason"],
            "no_active_warnings",
        )
        self.assertEqual(contract["workspaceSummary"]["filteredSignalCount"], 0)

    def test_s05_warning_heavy_state(self):
        decision_support_service = DecisionSupportService()
        payload, _ = publish_fixture(
            decision_support_service,
            "decision_support_s05_workspace_heavy.json",
        )

        contract = build_s05_warnings_workspace_contract(
            decision_support_service=decision_support_service,
            planning_context_key=payload["planning_context_key"],
            source_snapshot_id=payload["source_snapshot_id"],
        )

        self.assertEqual(contract["viewState"]["screenState"], "warning_heavy")
        self.assertTrue(contract["workspaceSummary"]["warningHeavy"])
        self.assertEqual(contract["workspaceSummary"]["filteredSignalCount"], 5)
        self.assertEqual(contract["workspaceSummary"]["affectedWorkflowCount"], 4)
        self.assertEqual(
            contract["groupSummaries"][-1],
            {
                "workflowId": "S04",
                "workflowLabel": "Delta Review",
                "itemCount": 2,
                "blockingCount": 2,
                "advisoryCount": 0,
                "trustLimitedCount": 0,
            },
        )

    def test_s05_trust_limited_state(self):
        decision_support_service = DecisionSupportService()
        payload, _ = publish_fixture(
            decision_support_service,
            "decision_support_s05_workspace_trust_only.json",
        )

        contract = build_s05_warnings_workspace_contract(
            decision_support_service=decision_support_service,
            planning_context_key=payload["planning_context_key"],
            source_snapshot_id=payload["source_snapshot_id"],
        )

        self.assertEqual(contract["viewState"]["screenState"], "trust_limited")
        self.assertEqual(contract["workspaceSummary"]["blockingWarningCount"], 0)
        self.assertEqual(contract["workspaceSummary"]["advisoryWarningCount"], 0)
        self.assertEqual(contract["workspaceSummary"]["trustLimitedCount"], 2)
        self.assertTrue(contract["workspaceSummary"]["trustLimitedPresent"])
        self.assertTrue(
            all(item["classification"] == "trust_limited" for item in contract["warningItems"])
        )
        self.assertEqual(len(contract["trustGuidance"]), 2)

    def test_s05_scoped_entry_behavior_from_origin_screens(self):
        decision_support_service = DecisionSupportService()
        payload, _ = publish_fixture(
            decision_support_service,
            "decision_support_s05_workspace_heavy.json",
        )

        cases = [
            {
                "origin_screen_id": "S01",
                "expected_codes": {"draft_unschedulable"},
            },
            {
                "origin_screen_id": "S02",
                "expected_codes": {"missing_task_name"},
            },
            {
                "origin_screen_id": "S03",
                "origin_scope_type": "resource",
                "origin_scope_id": "resource-ada",
                "origin_scope_external_id": "user-ada",
                "origin_scope_label": "Ada Lovelace",
                "expected_codes": {"dependency_chain_pressure"},
            },
            {
                "origin_screen_id": "S04",
                "origin_scope_type": "activation",
                "origin_scope_id": "activation-01",
                "origin_scope_external_id": "activation-01",
                "origin_scope_label": "Activation 01",
                "expected_codes": {"activation_requires_current_approved_plan"},
            },
        ]

        for case in cases:
            with self.subTest(origin_screen_id=case["origin_screen_id"]):
                contract = build_s05_warnings_workspace_contract(
                    decision_support_service=decision_support_service,
                    planning_context_key=payload["planning_context_key"],
                    source_snapshot_id=payload["source_snapshot_id"],
                    origin_screen_id=case["origin_screen_id"],
                    origin_scope_type=case.get("origin_scope_type"),
                    origin_scope_id=case.get("origin_scope_id"),
                    origin_scope_external_id=case.get("origin_scope_external_id"),
                    origin_scope_label=case.get("origin_scope_label"),
                )

                self.assertTrue(contract["filterState"]["scopedEntryDefaulted"])
                self.assertEqual(
                    contract["filterState"]["activeWorkflowIds"],
                    [case["origin_screen_id"]],
                )
                self.assertEqual(
                    {item["code"] for item in contract["warningItems"]},
                    case["expected_codes"],
                )
                self.assertEqual(
                    contract["returnNavigation"]["screen"]["id"],
                    case["origin_screen_id"],
                )

    def test_s05_default_grouping_is_by_affected_workflow(self):
        decision_support_service = DecisionSupportService()
        payload, _ = publish_fixture(
            decision_support_service,
            "decision_support_s05_workspace_heavy.json",
        )

        contract = build_s05_warnings_workspace_contract(
            decision_support_service=decision_support_service,
            planning_context_key=payload["planning_context_key"],
            source_snapshot_id=payload["source_snapshot_id"],
        )

        self.assertEqual(contract["filterState"]["defaultGroupBy"], "affected_workflow")
        self.assertEqual(contract["filterState"]["groupBy"], "affected_workflow")
        self.assertEqual(
            contract["filterState"]["availableGroupings"],
            [{"id": "affected_workflow", "label": "Affected workflow"}],
        )
        self.assertEqual(
            [summary["workflowId"] for summary in contract["groupSummaries"]],
            ["S01", "S02", "S03", "S04"],
        )

    def test_s05_filter_behavior_preserves_grouped_one_list_view(self):
        decision_support_service = DecisionSupportService()
        payload, _ = publish_fixture(
            decision_support_service,
            "decision_support_s05_workspace_heavy.json",
        )

        contract = build_s05_warnings_workspace_contract(
            decision_support_service=decision_support_service,
            planning_context_key=payload["planning_context_key"],
            source_snapshot_id=payload["source_snapshot_id"],
            workflow_filter_ids=["S04"],
            classification_filters=["blocking"],
            signal_type_filters=["warning"],
        )

        self.assertEqual(contract["workspaceSummary"]["filteredSignalCount"], 2)
        self.assertEqual(
            {item["code"] for item in contract["warningItems"]},
            {
                "dependency_safe_approval_blocked",
                "activation_requires_current_approved_plan",
            },
        )
        self.assertEqual(
            contract["groupSummaries"],
            [
                {
                    "workflowId": "S04",
                    "workflowLabel": "Delta Review",
                    "itemCount": 2,
                    "blockingCount": 2,
                    "advisoryCount": 0,
                    "trustLimitedCount": 0,
                }
            ],
        )

    def test_s05_one_list_blocking_advisory_and_trust_presentation(self):
        decision_support_service = DecisionSupportService()
        payload, _ = publish_fixture(
            decision_support_service,
            "decision_support_s05_workspace_normal.json",
        )

        contract = build_s05_warnings_workspace_contract(
            decision_support_service=decision_support_service,
            planning_context_key=payload["planning_context_key"],
            source_snapshot_id=payload["source_snapshot_id"],
        )

        self.assertTrue(contract["workspaceSummary"]["oneListPresentation"])
        self.assertEqual(
            {item["classification"] for item in contract["warningItems"]},
            {"blocking", "advisory", "trust_limited"},
        )
        self.assertEqual(
            {item["classificationLabel"] for item in contract["warningItems"]},
            {"Blocking", "Advisory", "Trust-limited"},
        )

    def test_s05_loading_state_if_requested(self):
        contract = build_s05_warnings_workspace_contract(
            decision_support_service=DecisionSupportService(),
            planning_context_key="portfolio-warnings-loading",
            source_snapshot_id="source-snapshot-warnings-loading",
            is_loading=True,
        )

        self.assertEqual(contract["viewState"]["screenState"], "loading")
        self.assertTrue(contract["viewState"]["isLoading"])
        self.assertIsNone(contract["emptyState"])

    def test_s05_access_restricted_state_if_requested(self):
        contract = build_s05_warnings_workspace_contract(
            decision_support_service=DecisionSupportService(),
            planning_context_key="portfolio-warnings-restricted",
            source_snapshot_id="source-snapshot-warnings-restricted",
            origin_screen_id="S02",
            access_restricted=True,
            access_restricted_reason="role_missing",
        )

        self.assertEqual(contract["viewState"]["screenState"], "access_restricted")
        self.assertTrue(contract["viewState"]["accessRestricted"])
        self.assertEqual(contract["viewState"]["accessRestrictedReason"], "role_missing")
        self.assertEqual(contract["warningItems"], [])
        self.assertEqual(contract["returnNavigation"]["screen"]["id"], "S02")

    def test_s05_contract_shape(self):
        decision_support_service = DecisionSupportService()
        payload, _ = publish_fixture(
            decision_support_service,
            "decision_support_s05_workspace_normal.json",
        )

        contract = build_s05_warnings_workspace_contract(
            decision_support_service=decision_support_service,
            planning_context_key=payload["planning_context_key"],
            source_snapshot_id=payload["source_snapshot_id"],
        )

        self.assertEqual(
            sorted(contract.keys()),
            [
                "emptyState",
                "filterState",
                "groupSummaries",
                "queryContext",
                "returnNavigation",
                "screen",
                "trustGuidance",
                "viewState",
                "warningItems",
                "workspaceSummary",
            ],
        )
        self.assertEqual(
            sorted(contract["warningItems"][0].keys()),
            [
                "affectedScope",
                "affectedWorkflow",
                "classification",
                "classificationLabel",
                "code",
                "interpretationCategory",
                "itemId",
                "message",
                "navigationTarget",
                "severity",
                "signalType",
                "sourceFact",
                "sourceIssueService",
                "trustGuidance",
            ],
        )
