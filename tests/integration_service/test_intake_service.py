import json
import unittest
from pathlib import Path

from services.integration_service.service import IntegrationService


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def load_fixture(name):
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class IntegrationServiceIntakeTests(unittest.TestCase):
    def setUp(self):
        self.service = IntegrationService()

    def test_valid_source_intake_and_normalization(self):
        bundle = self.service.import_source_plan(load_fixture("source_plan_valid.json"))

        self.assertEqual(bundle.source_readiness.state, "ready")
        self.assertTrue(bundle.source_readiness.runnable)
        self.assertEqual(bundle.snapshot.project_count, 1)
        self.assertEqual(bundle.snapshot.task_count, 3)
        self.assertEqual(bundle.snapshot.dependency_count, 1)
        self.assertEqual(bundle.snapshot.assignment_count, 3)
        self.assertEqual(bundle.issue_facts, [])
        self.assertEqual(len(bundle.project_mappings), 1)
        self.assertEqual(len(bundle.task_mappings), 3)
        self.assertEqual(len(bundle.resource_mappings), 3)
        self.assertTrue(
            all(mapping.scope_external_id == "project-apollo" for mapping in bundle.task_mappings)
        )
        self.assertIsNotNone(
            self.service.get_normalized_source_bundle(bundle.snapshot.snapshot_id)
        )

    def test_deterministic_normalization_for_identical_inputs(self):
        first_bundle = self.service.import_source_plan(load_fixture("source_plan_valid.json"))
        second_bundle = self.service.import_source_plan(
            load_fixture("source_plan_valid.json")
        )

        self.assertEqual(first_bundle.to_dict(), second_bundle.to_dict())
        self.assertEqual(
            first_bundle.snapshot.snapshot_id, second_bundle.snapshot.snapshot_id
        )
        self.assertEqual(first_bundle.artifact.payload_digest, second_bundle.artifact.payload_digest)

    def test_hierarchy_preservation(self):
        bundle = self.service.import_source_plan(load_fixture("source_plan_valid.json"))
        tasks_by_external_id = {
            task.external_task_id: task
            for task in bundle.tasks
        }

        parent_task = tasks_by_external_id["task-design"]
        child_task = tasks_by_external_id["task-design-review"]
        self.assertEqual(child_task.parent_task_id, parent_task.task_id)
        self.assertEqual(child_task.hierarchy_depth, 1)
        self.assertEqual(
            child_task.hierarchy_path,
            [parent_task.task_id, child_task.task_id],
        )

    def test_dependency_preservation_at_normalization_layer(self):
        bundle = self.service.import_source_plan(load_fixture("source_plan_valid.json"))

        self.assertEqual(len(bundle.dependencies), 1)
        dependency = bundle.dependencies[0]
        self.assertEqual(dependency.predecessor_external_task_id, "task-design")
        self.assertEqual(dependency.successor_external_task_id, "task-build-model")

    def test_malformed_input_handling(self):
        bundle = self.service.import_source_plan(
            load_fixture("source_plan_invalid_missing_required_fields.json")
        )

        self.assertEqual(bundle.source_readiness.state, "blocked")
        self.assertFalse(bundle.source_readiness.runnable)
        issue_codes = {issue.code for issue in bundle.issue_facts}
        self.assertIn("missing_task_name", issue_codes)
        self.assertIn("missing_effort", issue_codes)

    def test_source_setup_issue_fact_emission_for_invalid_source_conditions(self):
        bundle = self.service.import_source_plan(
            load_fixture("source_plan_invalid_dependency_target.json")
        )

        self.assertEqual(bundle.source_readiness.state, "blocked")
        self.assertEqual(bundle.snapshot.dependency_count, 0)
        self.assertEqual(bundle.snapshot.task_count, 2)
        self.assertIn(
            "dependency_target_not_found",
            {issue.code for issue in bundle.issue_facts},
        )

    def test_normalized_output_contract_shape(self):
        bundle = self.service.import_source_plan(load_fixture("source_plan_valid.json"))
        contract = bundle.to_dict()

        self.assertEqual(
            sorted(contract.keys()),
            [
                "artifact",
                "dependencies",
                "issue_facts",
                "project_mappings",
                "resource_assignments",
                "resource_exceptions",
                "resource_mappings",
                "resources",
                "snapshot",
                "source_readiness",
                "task_mappings",
                "tasks",
            ],
        )
        self.assertEqual(
            sorted(contract["artifact"].keys()),
            [
                "artifact_id",
                "captured_at",
                "external_artifact_id",
                "payload_digest",
                "raw_payload",
                "source_system",
            ],
        )
        self.assertEqual(
            sorted(contract["snapshot"].keys()),
            [
                "artifact_id",
                "assignment_count",
                "captured_at",
                "dependency_count",
                "issue_count",
                "project_count",
                "snapshot_id",
                "source_system",
                "task_count",
            ],
        )
        self.assertEqual(contract["resources"], [])
        self.assertEqual(contract["resource_exceptions"], [])

    def test_resource_capacity_inputs_are_normalized_when_present(self):
        bundle = self.service.import_source_plan(load_fixture("source_plan_capacity_fte.json"))

        self.assertEqual(len(bundle.resources), 1)
        self.assertEqual(bundle.resource_exceptions, [])
        resource = bundle.resources[0]
        self.assertEqual(resource.external_resource_id, "user-ada")
        self.assertEqual(resource.default_daily_capacity_hours, 8.0)
        self.assertEqual(resource.availability_ratio, 1.0)
        self.assertEqual(
            resource.working_days,
            ["monday", "tuesday", "wednesday", "thursday", "friday"],
        )


if __name__ == "__main__":
    unittest.main()
