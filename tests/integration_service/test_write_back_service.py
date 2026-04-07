import json
import unittest
from pathlib import Path

from services.integration_service import (
    BOUND_WRITE_BACK_TRIGGER_STEP,
    BoundedWriteBackExecutionReceipt,
    BoundedWriteBackItemResult,
    BoundedWriteBackRequest,
    BoundedWriteBackTarget,
    ExternalWriteBackGateway,
    InMemoryIntegrationRepository,
    IntegrationService,
)
from services.planning_engine_service.service import PlanningEngineService
from services.review_approval_service import (
    ApprovedOperatingPlanSnapshot,
    ApprovedPlanProjectRecord,
    ApprovedPlanTaskRecord,
    RecommendationOriginReference,
    ReviewApprovalService,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class FixtureExternalWriteBackGateway(ExternalWriteBackGateway):
    def __init__(self, *fixture_names):
        self._fixtures = [load_fixture(name) for name in fixture_names]
        self.requests = []

    def execute_write_back(self, request):
        self.requests.append(request)
        fixture = self._fixtures.pop(0)
        item_results = []
        for target in request.targets:
            outcome = fixture["target_outcomes"][target.entity_external_id]
            item_results.append(
                BoundedWriteBackItemResult(
                    target_id=target.target_id,
                    delta_id=target.delta_id,
                    entity_type=target.entity_type,
                    entity_external_id=target.entity_external_id,
                    status=outcome["status"],
                    applied_fields=list(outcome.get("applied_fields", [])),
                    error_code=outcome.get("error_code"),
                    error_message=outcome.get("error_message"),
                )
            )
        return BoundedWriteBackExecutionReceipt(
            completed_at=fixture["completed_at"],
            item_results=item_results,
        )


def build_activated_context(
    review_fixture_name,
    planning_run_key,
    selected_entity_external_ids,
):
    scenario = load_fixture(review_fixture_name)
    source_payload = load_fixture(scenario["source_plan_fixture"])
    integration_repository = InMemoryIntegrationRepository()
    integration_service = IntegrationService(repository=integration_repository)
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
    for entity_external_id in selected_entity_external_ids:
        requested_delta = next(
            delta
            for delta in review_context.delta_items
            if delta.entity_external_id == entity_external_id
        )
        selection_result = review_approval_service.record_delta_acceptance_selection(
            review_context_id=review_context.review_context_id,
            delta_id=requested_delta.delta_id,
            selected=True,
        )
        if (
            selection_result.status == "blocked"
            and selection_result.connected_set_resolution is not None
            and selection_result.connected_set_resolution.connected_change_set is not None
        ):
            review_approval_service.record_connected_set_acceptance_selection(
                review_context_id=review_context.review_context_id,
                requested_delta_id=requested_delta.delta_id,
                selected=True,
            )
    activation_result = review_approval_service.activate_approved_changes(
        review_context_id=review_context.review_context_id,
        requested_by="approver@example.com",
        requested_at="2026-04-06T10:00:00Z",
    )
    return (
        integration_repository,
        bundle,
        review_approval_service,
        review_context,
        activation_result,
    )


def build_write_back_request(
    activation_result,
    request_id,
    attempt_number=1,
    workflow_instance_id="activation-workflow-01",
    requested_at="2026-04-06T12:00:00Z",
    step_name=BOUND_WRITE_BACK_TRIGGER_STEP,
    idempotency_key=None,
):
    return BoundedWriteBackRequest(
        request_id=request_id,
        activation_command_id=activation_result.command_id,
        activation_id=activation_result.activation_state.activation_id,
        review_context_id=activation_result.review_context_id,
        approved_plan_id=activation_result.activation_state.approved_plan_id_after,
        source_snapshot_id=activation_result.downstream_handoff.source_snapshot_id,
        orchestrator_workflow_instance_id=workflow_instance_id,
        orchestrator_step_name=step_name,
        requested_by="workflow-orchestrator@example.com",
        requested_at=requested_at,
        attempt_number=attempt_number,
        targets=[
            BoundedWriteBackTarget(
                target_id=target.target_id,
                delta_id=target.delta_id,
                entity_type=target.entity_type,
                entity_external_id=target.entity_external_id,
                entity_name=target.entity_name,
                project_external_id=target.project_external_id,
                write_back_action=target.write_back_action,
                write_back_fields=list(target.write_back_fields),
            )
            for target in activation_result.downstream_handoff.write_back_targets
        ],
        idempotency_key=idempotency_key,
    )


class IntegrationWriteBackTests(unittest.TestCase):
    def test_successful_post_activation_write_back(self):
        repository, bundle, _, _, activation_result = build_activated_context(
            "review_approval_delta_simple.json",
            "write-back-success",
            ["task-rollout"],
        )
        gateway = FixtureExternalWriteBackGateway("integration_write_back_success.json")
        service = IntegrationService(
            repository=repository,
            external_write_back_gateway=gateway,
        )
        request = build_write_back_request(
            activation_result,
            request_id="write-back-request-success",
            idempotency_key="write-back-success",
        )

        result = service.execute_bounded_external_write_back(request)
        queried = service.get_write_back_result(
            activation_id=activation_result.activation_state.activation_id
        )

        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.reused_existing)
        self.assertEqual(result.source_system, bundle.snapshot.source_system)
        self.assertEqual(result.total_target_count, 1)
        self.assertEqual(result.succeeded_target_count, 1)
        self.assertEqual(result.failed_target_count, 0)
        self.assertIsNotNone(queried)
        self.assertEqual(queried.request_id, result.request_id)
        self.assertEqual(len(gateway.requests), 1)

    def test_failed_write_back_does_not_roll_back_approved_plan_truth(self):
        repository, _, review_approval_service, _, activation_result = build_activated_context(
            "review_approval_delta_simple.json",
            "write-back-failure",
            ["task-rollout"],
        )
        gateway = FixtureExternalWriteBackGateway("integration_write_back_failure.json")
        service = IntegrationService(
            repository=repository,
            external_write_back_gateway=gateway,
        )
        request = build_write_back_request(
            activation_result,
            request_id="write-back-request-failure",
        )
        approved_plan_id_before_write_back = (
            review_approval_service.get_approved_operating_plan_snapshot(current=True).approved_plan_id
        )

        result = service.execute_bounded_external_write_back(request)
        approved_plan_id_after_write_back = (
            review_approval_service.get_approved_operating_plan_snapshot(current=True).approved_plan_id
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            approved_plan_id_before_write_back,
            activation_result.activation_state.approved_plan_id_after,
        )
        self.assertEqual(
            approved_plan_id_after_write_back,
            activation_result.activation_state.approved_plan_id_after,
        )

    def test_partial_result_handling(self):
        repository, _, _, _, activation_result = build_activated_context(
            "review_approval_delta_dependency_linked.json",
            "write-back-partial",
            ["task-design", "task-implement"],
        )
        gateway = FixtureExternalWriteBackGateway("integration_write_back_partial.json")
        service = IntegrationService(
            repository=repository,
            external_write_back_gateway=gateway,
        )
        request = build_write_back_request(
            activation_result,
            request_id="write-back-request-partial",
        )

        result = service.execute_bounded_external_write_back(request)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.total_target_count, 2)
        self.assertEqual(result.succeeded_target_count, 1)
        self.assertEqual(result.failed_target_count, 1)
        self.assertEqual(
            [item_result.entity_external_id for item_result in result.item_results],
            ["task-design", "task-implement"],
        )

    def test_retry_and_idempotent_reuse_behavior(self):
        repository, _, _, _, activation_result = build_activated_context(
            "review_approval_delta_simple.json",
            "write-back-retry",
            ["task-rollout"],
        )
        gateway = FixtureExternalWriteBackGateway(
            "integration_write_back_failure.json",
            "integration_write_back_success.json",
        )
        service = IntegrationService(
            repository=repository,
            external_write_back_gateway=gateway,
        )
        first_request = build_write_back_request(
            activation_result,
            request_id="write-back-request-retry-1",
            attempt_number=1,
            idempotency_key="write-back-retry-1",
        )
        second_request = build_write_back_request(
            activation_result,
            request_id="write-back-request-retry-2",
            attempt_number=2,
            requested_at="2026-04-06T12:05:00Z",
            idempotency_key="write-back-retry-2",
        )

        failed = service.execute_bounded_external_write_back(first_request)
        reused = service.execute_bounded_external_write_back(first_request)
        succeeded = service.execute_bounded_external_write_back(second_request)
        latest = service.get_write_back_result(
            activation_id=activation_result.activation_state.activation_id
        )

        self.assertEqual(failed.status, "failed")
        self.assertFalse(failed.reused_existing)
        self.assertTrue(reused.reused_existing)
        self.assertEqual(succeeded.status, "succeeded")
        self.assertEqual(succeeded.attempt_number, 2)
        self.assertEqual(latest.request_id, succeeded.request_id)
        self.assertEqual(len(gateway.requests), 2)

    def test_write_back_requires_orchestrated_post_activation_request(self):
        repository, _, _, _, activation_result = build_activated_context(
            "review_approval_delta_simple.json",
            "write-back-orchestrated-only",
            ["task-rollout"],
        )
        gateway = FixtureExternalWriteBackGateway("integration_write_back_success.json")
        service = IntegrationService(
            repository=repository,
            external_write_back_gateway=gateway,
        )
        request = build_write_back_request(
            activation_result,
            request_id="write-back-request-invalid-step",
            step_name="activation_recomputation",
        )

        with self.assertRaisesRegex(
            ValueError,
            "activation side-effect sequencing step",
        ):
            service.execute_bounded_external_write_back(request)

        self.assertEqual(len(gateway.requests), 0)

    def test_write_back_contract_shape_and_ownership_boundary(self):
        repository, _, review_approval_service, _, activation_result = build_activated_context(
            "review_approval_delta_simple.json",
            "write-back-contract-shape",
            ["task-rollout"],
        )
        gateway = FixtureExternalWriteBackGateway("integration_write_back_success.json")
        service = IntegrationService(
            repository=repository,
            external_write_back_gateway=gateway,
        )
        request = build_write_back_request(
            activation_result,
            request_id="write-back-request-contract-shape",
        )

        payload = service.execute_bounded_external_write_back(request).to_dict()

        self.assertEqual(
            sorted(payload.keys()),
            [
                "activation_command_id",
                "activation_id",
                "approved_plan_id",
                "attempt_number",
                "completed_at",
                "failed_target_count",
                "item_results",
                "orchestrator_step_name",
                "orchestrator_workflow_instance_id",
                "request_id",
                "requested_at",
                "requested_by",
                "reused_existing",
                "review_context_id",
                "source_snapshot_id",
                "source_system",
                "status",
                "succeeded_target_count",
                "total_target_count",
            ],
        )
        self.assertNotIn("approved_plan_snapshot", payload)
        self.assertNotIn("activation_state", payload)
        self.assertEqual(
            review_approval_service.get_approved_operating_plan_snapshot(current=True).approved_plan_id,
            activation_result.activation_state.approved_plan_id_after,
        )


if __name__ == "__main__":
    unittest.main()
