import json
import unittest
from urllib.parse import urlencode

from services.api_gateway_bff import (
    ApiGatewayBffApplication,
    build_local_demo_runtime,
    build_test_environ,
)


class LocalDemoRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = build_local_demo_runtime()
        self.app = ApiGatewayBffApplication(self.runtime.dependencies)

    def _request(self, method, path, query=None, body=None):
        status_holder = {}

        def start_response(status, headers):
            status_holder["status"] = status
            status_holder["headers"] = headers

        environ = build_test_environ(
            method=method,
            path=path,
            query_string=urlencode(query or {}, doseq=True),
            body=body,
        )
        response = b"".join(self.app(environ, start_response)).decode("utf-8")
        return int(status_holder["status"].split()[0]), json.loads(response)

    def test_seeded_local_demo_runtime_exposes_browser_flow_contracts(self):
        seed_state = self.runtime.seed_state

        status, s01_payload = self._request("GET", "/api/screens/s01/portfolio")
        self.assertEqual(status, 200)
        self.assertEqual(s01_payload["screen"]["id"], "S01")
        self.assertTrue(s01_payload["dailySwimlanes"])
        self.assertEqual(
            s01_payload["queryContext"]["planningRunId"], seed_state.planning_run_id
        )

        status, s02_payload = self._request(
            "GET",
            "/api/screens/s02/setup",
            query={"planningContextKey": seed_state.planning_context_key},
        )
        self.assertEqual(status, 200)
        self.assertEqual(s02_payload["screen"]["id"], "S02")
        self.assertEqual(
            s02_payload["queryContext"]["sourceSnapshotId"],
            seed_state.source_snapshot_id,
        )
        self.assertTrue(s02_payload["overallReadiness"]["canContinueToPlanning"])

        status, d01_payload = self._request(
            "GET",
            "/api/drawers/d01/task-drilldown",
            query={
                "planningRunId": seed_state.planning_run_id,
                "resourceExternalId": seed_state.resource_external_id,
                "date": seed_state.drilldown_date,
                "weekStartDate": seed_state.drilldown_week_start,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(d01_payload["drawer"]["id"], "D01")
        self.assertTrue(d01_payload["tasks"])

        status, s03_payload = self._request("GET", "/api/screens/s03/resource-detail")
        self.assertEqual(status, 200)
        self.assertEqual(s03_payload["screen"]["id"], "S03")
        self.assertEqual(
            s03_payload["queryContext"]["resourceExternalId"],
            seed_state.resource_external_id,
        )

        status, s04_payload = self._request("GET", "/api/screens/s04/delta-review")
        self.assertEqual(status, 200)
        self.assertEqual(s04_payload["screen"]["id"], "S04")
        self.assertEqual(
            s04_payload["queryContext"]["reviewContextId"], seed_state.review_context_id
        )
        self.assertTrue(s04_payload["groupedDeltaReview"])

        status, m01_payload = self._request(
            "GET",
            "/api/modals/m01/connected-change-set",
            query={
                "reviewContextId": seed_state.review_context_id,
                "requestedDeltaId": seed_state.connected_set_delta_id,
                "planningContextKey": seed_state.planning_context_key,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(m01_payload["screen"]["id"], "M01")
        self.assertTrue(m01_payload["connectedSet"]["memberDeltaIds"])

        status, s05_payload = self._request(
            "GET",
            "/api/screens/s05/warnings-workspace",
            query={
                "planningContextKey": seed_state.planning_context_key,
                "sourceSnapshotId": seed_state.source_snapshot_id,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(s05_payload["screen"]["id"], "S05")
        self.assertGreater(s05_payload["workspaceSummary"]["filteredSignalCount"], 0)

    def test_local_auto_progressor_completes_browser_triggered_activation_flow(self):
        seed_state = self.runtime.seed_state

        status, selection_payload = self._request(
            "POST",
            "/api/modals/m01/connected-change-set/acceptance-selection",
            body={
                "reviewContextId": seed_state.review_context_id,
                "requestedDeltaId": seed_state.connected_set_delta_id,
                "selected": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(selection_payload["status"], "applied")

        status, activation_payload = self._request(
            "POST",
            "/api/screens/s04/activation",
            body={
                "reviewContextId": seed_state.review_context_id,
                "requestedBy": "approver@example.com",
                "requestedAt": "2026-04-08T10:00:00Z",
            },
        )
        self.assertEqual(status, 200)
        workflow_instance_id = activation_payload["downstreamWorkflow"]["workflowInstanceId"]
        self.assertEqual(activation_payload["status"], "activated")
        self.assertIsNotNone(workflow_instance_id)

        self.runtime.workflow_auto_progressor.tick("2026-04-08T10:00:05Z")
        self.runtime.workflow_auto_progressor.tick("2026-04-08T10:00:10Z")
        self.runtime.workflow_auto_progressor.tick("2026-04-08T10:00:15Z")
        self.runtime.workflow_auto_progressor.tick("2026-04-08T10:00:20Z")

        workflow_status = (
            self.runtime.dependencies.workflow_orchestrator_service.get_activation_workflow_status(
                workflow_instance_id=workflow_instance_id
            )
        )
        self.assertIsNotNone(workflow_status)
        self.assertEqual(workflow_status.status, "succeeded")

        write_back_result = self.runtime.dependencies.integration_service.get_write_back_result(
            activation_id=activation_payload["activationId"]
        )
        self.assertIsNotNone(write_back_result)
        self.assertEqual(write_back_result.status, "succeeded")


if __name__ == "__main__":
    unittest.main()
