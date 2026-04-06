"""Fixture-driven source normalization owned by the Integration Service."""

import hashlib
import json
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .contracts import (
    NormalizedDependencyRecord,
    NormalizedResourceExceptionRecord,
    NormalizedResourceRecord,
    NormalizedResourceAssignmentRecord,
    NormalizedSourceBundle,
    NormalizedTaskRecord,
    SourceArtifact,
    SourceMapping,
    SourceReadiness,
    SourceSetupIssueFact,
    SourceSnapshot,
)


DependencyRef = Tuple[str, str, Any]
VALID_WORKING_DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def normalize_source_plan(raw_payload: Dict[str, Any]) -> NormalizedSourceBundle:
    """Normalize imported source data into the Integration Service contract."""

    canonical_payload = _canonical_json(raw_payload)
    payload_digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    source_system = raw_payload.get("source_system")
    if not isinstance(source_system, str) or not source_system.strip():
        source_system = "unknown-source"

    artifact_section = raw_payload.get("artifact", {})
    artifact_external_id = ""
    if isinstance(artifact_section, dict):
        artifact_external_id = artifact_section.get("external_id", "") or ""

    captured_at = raw_payload.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at.strip():
        captured_at = "unknown-captured-at"

    artifact_id = _stable_id(
        "artifact",
        source_system,
        artifact_external_id or payload_digest[:16],
    )
    snapshot_id = _stable_id("snapshot", artifact_id, payload_digest)

    project_mapping_index: Dict[str, SourceMapping] = {}
    task_mapping_index: Dict[Tuple[str, str], SourceMapping] = {}
    resource_mapping_index: Dict[str, SourceMapping] = {}
    normalized_tasks: List[NormalizedTaskRecord] = []
    normalized_dependencies: List[NormalizedDependencyRecord] = []
    normalized_resource_assignments: List[NormalizedResourceAssignmentRecord] = []
    normalized_resources: List[NormalizedResourceRecord] = []
    normalized_resource_exceptions: List[NormalizedResourceExceptionRecord] = []
    issue_facts: List[SourceSetupIssueFact] = []
    pending_dependencies: List[DependencyRef] = []
    task_lookup: Dict[Tuple[str, str], NormalizedTaskRecord] = {}

    if raw_payload.get("source_system") != source_system:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="missing_source_system",
                message="source_system is required for source normalization.",
                entity_type="artifact",
                entity_external_id=artifact_external_id or None,
                field="source_system",
            )
        )

    if not artifact_external_id:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="missing_artifact_external_id",
                message="artifact.external_id is required for source artifact tracking.",
                entity_type="artifact",
                entity_external_id=None,
                field="artifact.external_id",
            )
        )

    if raw_payload.get("captured_at") != captured_at:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="missing_captured_at",
                message="captured_at is required for source snapshot semantics.",
                entity_type="artifact",
                entity_external_id=artifact_external_id or None,
                field="captured_at",
            )
        )

    raw_projects = raw_payload.get("projects", [])
    if not isinstance(raw_projects, list):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_projects_collection",
                message="projects must be provided as a list.",
                entity_type="artifact",
                entity_external_id=artifact_external_id or None,
                field="projects",
            )
        )
        raw_projects = []

    for raw_project in _sorted_records(raw_projects):
        if not isinstance(raw_project, dict):
            issue_facts.append(
                _build_issue(
                    snapshot_id=snapshot_id,
                    source_system=source_system,
                    severity="blocking",
                    code="invalid_project_record",
                    message="Each project record must be an object.",
                    entity_type="project",
                    entity_external_id=None,
                    field="projects[]",
                )
            )
            continue

        project_external_id = raw_project.get("external_id")
        project_name = raw_project.get("name")
        if not isinstance(project_external_id, str) or not project_external_id.strip():
            issue_facts.append(
                _build_issue(
                    snapshot_id=snapshot_id,
                    source_system=source_system,
                    severity="blocking",
                    code="missing_project_external_id",
                    message="Project external_id is required.",
                    entity_type="project",
                    entity_external_id=None,
                    field="external_id",
                )
            )
            continue
        if not isinstance(project_name, str) or not project_name.strip():
            issue_facts.append(
                _build_issue(
                    snapshot_id=snapshot_id,
                    source_system=source_system,
                    severity="blocking",
                    code="missing_project_name",
                    message="Project name is required.",
                    entity_type="project",
                    entity_external_id=project_external_id,
                    field="name",
                )
            )
            continue

        project_id = _stable_id("project", source_system, project_external_id)
        project_mapping_index[project_external_id] = SourceMapping(
            mapping_id=_stable_id("project-mapping", source_system, project_external_id),
            external_id=project_external_id,
            scope_external_id=None,
            internal_id=project_id,
            source_system=source_system,
            display_name=project_name,
        )

        raw_tasks = raw_project.get("tasks", [])
        if not isinstance(raw_tasks, list):
            issue_facts.append(
                _build_issue(
                    snapshot_id=snapshot_id,
                    source_system=source_system,
                    severity="blocking",
                    code="invalid_task_collection",
                    message="Project tasks must be provided as a list.",
                    entity_type="project",
                    entity_external_id=project_external_id,
                    field="tasks",
                )
            )
            continue

        for raw_task in _sorted_records(raw_tasks):
            _normalize_task(
                raw_task=raw_task,
                snapshot_id=snapshot_id,
                source_system=source_system,
                project_id=project_id,
                project_external_id=project_external_id,
                task_lookup=task_lookup,
                task_mapping_index=task_mapping_index,
                resource_mapping_index=resource_mapping_index,
                normalized_tasks=normalized_tasks,
                normalized_resource_assignments=normalized_resource_assignments,
                issue_facts=issue_facts,
                pending_dependencies=pending_dependencies,
                parent_task_id=None,
                hierarchy_path=[],
            )

    for project_external_id, successor_external_id, dependency_ref in pending_dependencies:
        _resolve_dependency(
            dependency_ref=dependency_ref,
            snapshot_id=snapshot_id,
            source_system=source_system,
            project_external_id=project_external_id,
            successor_external_id=successor_external_id,
            task_lookup=task_lookup,
            normalized_dependencies=normalized_dependencies,
            issue_facts=issue_facts,
        )

    _normalize_resources(
        raw_payload=raw_payload,
        snapshot_id=snapshot_id,
        source_system=source_system,
        resource_mapping_index=resource_mapping_index,
        normalized_resources=normalized_resources,
        normalized_resource_exceptions=normalized_resource_exceptions,
    )

    project_mappings = _sort_mappings(project_mapping_index.values())
    task_mappings = _sort_mappings(task_mapping_index.values())
    resource_mappings = _sort_mappings(resource_mapping_index.values())
    normalized_tasks.sort(
        key=lambda task: (
            task.project_external_id,
            task.hierarchy_path,
            task.external_task_id,
        )
    )
    normalized_dependencies.sort(
        key=lambda dependency: (
            dependency.successor_external_task_id,
            dependency.predecessor_external_task_id,
        )
    )
    normalized_resource_assignments.sort(
        key=lambda assignment: (assignment.task_external_id, assignment.resource_external_id)
    )
    normalized_resources.sort(
        key=lambda resource: resource.external_resource_id
    )
    normalized_resource_exceptions.sort(
        key=lambda exception: (exception.resource_external_id, exception.date)
    )
    issue_facts.sort(
        key=lambda issue: (issue.severity, issue.code, issue.entity_external_id or "")
    )

    readiness = _build_readiness(issue_facts)
    artifact = SourceArtifact(
        artifact_id=artifact_id,
        external_artifact_id=artifact_external_id or "missing-artifact-external-id",
        source_system=source_system,
        captured_at=captured_at,
        payload_digest=payload_digest,
        raw_payload=json.loads(canonical_payload),
    )
    snapshot = SourceSnapshot(
        snapshot_id=snapshot_id,
        artifact_id=artifact.artifact_id,
        source_system=source_system,
        captured_at=captured_at,
        project_count=len(project_mappings),
        task_count=len(normalized_tasks),
        dependency_count=len(normalized_dependencies),
        assignment_count=len(normalized_resource_assignments),
        issue_count=len(issue_facts),
    )

    return NormalizedSourceBundle(
        artifact=artifact,
        snapshot=snapshot,
        project_mappings=project_mappings,
        task_mappings=task_mappings,
        resource_mappings=resource_mappings,
        tasks=normalized_tasks,
        dependencies=normalized_dependencies,
        resource_assignments=normalized_resource_assignments,
        resources=normalized_resources,
        resource_exceptions=normalized_resource_exceptions,
        issue_facts=issue_facts,
        source_readiness=readiness,
    )


def _normalize_resources(
    raw_payload: Dict[str, Any],
    snapshot_id: str,
    source_system: str,
    resource_mapping_index: Dict[str, SourceMapping],
    normalized_resources: List[NormalizedResourceRecord],
    normalized_resource_exceptions: List[NormalizedResourceExceptionRecord],
) -> None:
    raw_resources = raw_payload.get("resources", [])
    if raw_resources is None or not isinstance(raw_resources, list):
        return

    seen_resource_external_ids: Dict[str, bool] = {}
    for raw_resource in _sorted_records(raw_resources):
        if not isinstance(raw_resource, dict):
            continue

        resource_external_id = raw_resource.get("external_id")
        if not isinstance(resource_external_id, str) or not resource_external_id.strip():
            continue
        if resource_external_id in seen_resource_external_ids:
            continue
        seen_resource_external_ids[resource_external_id] = True

        resource_id = _stable_id("resource", source_system, resource_external_id)
        display_name = raw_resource.get("display_name")
        if display_name is not None and not isinstance(display_name, str):
            display_name = None

        calendar = raw_resource.get("calendar", {})
        if not isinstance(calendar, dict):
            calendar = {}
        availability = raw_resource.get("availability", {})
        if not isinstance(availability, dict):
            availability = {}

        calendar_name = calendar.get("name")
        if calendar_name is not None and not isinstance(calendar_name, str):
            calendar_name = None

        default_daily_capacity_hours = _normalize_optional_positive_float(
            calendar.get("daily_capacity_hours")
        )
        working_days = _normalize_working_days(calendar.get("working_days"))
        availability_ratio = _normalize_optional_ratio(
            availability.get("fte_ratio")
        )

        resource_mapping_index[resource_external_id] = SourceMapping(
            mapping_id=_stable_id("resource-mapping", source_system, resource_external_id),
            external_id=resource_external_id,
            scope_external_id=None,
            internal_id=resource_id,
            source_system=source_system,
            display_name=display_name,
        )
        normalized_resources.append(
            NormalizedResourceRecord(
                resource_id=resource_id,
                source_snapshot_id=snapshot_id,
                source_system=source_system,
                external_resource_id=resource_external_id,
                display_name=display_name,
                calendar_id=_stable_id(
                    "calendar",
                    source_system,
                    resource_external_id,
                    calendar_name or "default",
                ),
                calendar_name=calendar_name,
                default_daily_capacity_hours=default_daily_capacity_hours,
                working_days=working_days,
                availability_ratio=availability_ratio,
            )
        )

        raw_exceptions = raw_resource.get("exceptions", [])
        if raw_exceptions is None or not isinstance(raw_exceptions, list):
            continue
        for raw_exception in _sorted_records(raw_exceptions):
            exception_record = _normalize_resource_exception(
                raw_exception=raw_exception,
                snapshot_id=snapshot_id,
                source_system=source_system,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
            )
            if exception_record is not None:
                normalized_resource_exceptions.append(exception_record)


def _normalize_task(
    raw_task: Any,
    snapshot_id: str,
    source_system: str,
    project_id: str,
    project_external_id: str,
    task_lookup: Dict[Tuple[str, str], NormalizedTaskRecord],
    task_mapping_index: Dict[Tuple[str, str], SourceMapping],
    resource_mapping_index: Dict[str, SourceMapping],
    normalized_tasks: List[NormalizedTaskRecord],
    normalized_resource_assignments: List[NormalizedResourceAssignmentRecord],
    issue_facts: List[SourceSetupIssueFact],
    pending_dependencies: List[DependencyRef],
    parent_task_id: Optional[str],
    hierarchy_path: List[str],
) -> None:
    if not isinstance(raw_task, dict):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_task_record",
                message="Each task record must be an object.",
                entity_type="task",
                entity_external_id=None,
                field="tasks[]",
            )
        )
        return

    task_external_id = raw_task.get("external_id")
    if not isinstance(task_external_id, str) or not task_external_id.strip():
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="missing_task_external_id",
                message="Task external_id is required.",
                entity_type="task",
                entity_external_id=None,
                field="external_id",
            )
        )
        return

    task_id = _stable_id("task", source_system, project_external_id, task_external_id)
    if (project_external_id, task_external_id) in task_lookup:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="duplicate_task_external_id",
                message="Duplicate task external_id encountered within the same project.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="external_id",
            )
        )
        return

    task_name = raw_task.get("name")
    if not isinstance(task_name, str) or not task_name.strip():
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="missing_task_name",
                message="Task name is required.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="name",
            )
        )
        return

    effort_hours = _normalize_effort(
        raw_task=raw_task,
        snapshot_id=snapshot_id,
        source_system=source_system,
        task_external_id=task_external_id,
        issue_facts=issue_facts,
    )
    start_date, due_date = _normalize_dates(
        raw_task=raw_task,
        snapshot_id=snapshot_id,
        source_system=source_system,
        task_external_id=task_external_id,
        issue_facts=issue_facts,
    )
    task_hierarchy_path = hierarchy_path + [task_id]
    task_record = NormalizedTaskRecord(
        task_id=task_id,
        source_snapshot_id=snapshot_id,
        source_system=source_system,
        external_task_id=task_external_id,
        project_id=project_id,
        project_external_id=project_external_id,
        parent_task_id=parent_task_id,
        name=task_name.strip(),
        hierarchy_path=task_hierarchy_path,
        hierarchy_depth=len(task_hierarchy_path) - 1,
        effort_hours=effort_hours,
        start_date=start_date,
        due_date=due_date,
    )
    normalized_tasks.append(task_record)
    task_lookup[(project_external_id, task_external_id)] = task_record
    task_mapping_index[(project_external_id, task_external_id)] = SourceMapping(
        mapping_id=_stable_id(
            "task-mapping", source_system, project_external_id, task_external_id
        ),
        external_id=task_external_id,
        scope_external_id=project_external_id,
        internal_id=task_id,
        source_system=source_system,
        display_name=task_name.strip(),
    )

    _normalize_assignments(
        raw_task=raw_task,
        snapshot_id=snapshot_id,
        source_system=source_system,
        task_record=task_record,
        resource_mapping_index=resource_mapping_index,
        normalized_resource_assignments=normalized_resource_assignments,
        issue_facts=issue_facts,
    )

    depends_on = raw_task.get("depends_on_external_ids", [])
    if depends_on is None:
        depends_on = []
    if not isinstance(depends_on, list):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_dependency_collection",
                message="depends_on_external_ids must be a list.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="depends_on_external_ids",
            )
        )
    else:
        for dependency_ref in depends_on:
            pending_dependencies.append(
                (project_external_id, task_external_id, dependency_ref)
            )

    subtasks = raw_task.get("subtasks", [])
    if subtasks is None:
        subtasks = []
    if not isinstance(subtasks, list):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_subtask_collection",
                message="subtasks must be provided as a list.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="subtasks",
            )
        )
        return

    for raw_subtask in _sorted_records(subtasks):
        _normalize_task(
            raw_task=raw_subtask,
            snapshot_id=snapshot_id,
            source_system=source_system,
            project_id=project_id,
            project_external_id=project_external_id,
            task_lookup=task_lookup,
            task_mapping_index=task_mapping_index,
            resource_mapping_index=resource_mapping_index,
            normalized_tasks=normalized_tasks,
            normalized_resource_assignments=normalized_resource_assignments,
            issue_facts=issue_facts,
            pending_dependencies=pending_dependencies,
            parent_task_id=task_id,
            hierarchy_path=task_hierarchy_path,
        )


def _normalize_assignments(
    raw_task: Dict[str, Any],
    snapshot_id: str,
    source_system: str,
    task_record: NormalizedTaskRecord,
    resource_mapping_index: Dict[str, SourceMapping],
    normalized_resource_assignments: List[NormalizedResourceAssignmentRecord],
    issue_facts: List[SourceSetupIssueFact],
) -> None:
    raw_assignees = raw_task.get("assignees", [])
    if raw_assignees is None:
        raw_assignees = []
    if not isinstance(raw_assignees, list):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_assignee_collection",
                message="assignees must be provided as a list.",
                entity_type="task",
                entity_external_id=task_record.external_task_id,
                field="assignees",
            )
        )
        return

    seen_assignments: Dict[str, bool] = {}
    for raw_assignee in _sorted_records(raw_assignees):
        if not isinstance(raw_assignee, dict):
            issue_facts.append(
                _build_issue(
                    snapshot_id=snapshot_id,
                    source_system=source_system,
                    severity="blocking",
                    code="invalid_assignee_record",
                    message="Each assignee record must be an object.",
                    entity_type="assignment",
                    entity_external_id=task_record.external_task_id,
                    field="assignees[]",
                )
            )
            continue

        resource_external_id = raw_assignee.get("external_id")
        if not isinstance(resource_external_id, str) or not resource_external_id.strip():
            issue_facts.append(
                _build_issue(
                    snapshot_id=snapshot_id,
                    source_system=source_system,
                    severity="blocking",
                    code="missing_resource_external_id",
                    message="Assignee external_id is required for resource mapping.",
                    entity_type="assignment",
                    entity_external_id=task_record.external_task_id,
                    field="assignees[].external_id",
                )
            )
            continue

        resource_id = _stable_id("resource", source_system, resource_external_id)
        display_name = raw_assignee.get("display_name")
        if display_name is not None and not isinstance(display_name, str):
            display_name = None

        resource_mapping_index[resource_external_id] = SourceMapping(
            mapping_id=_stable_id("resource-mapping", source_system, resource_external_id),
            external_id=resource_external_id,
            scope_external_id=None,
            internal_id=resource_id,
            source_system=source_system,
            display_name=display_name,
        )

        allocation_percent = raw_assignee.get("allocation_percent")
        if allocation_percent is not None:
            if not isinstance(allocation_percent, (int, float)):
                issue_facts.append(
                    _build_issue(
                        snapshot_id=snapshot_id,
                        source_system=source_system,
                        severity="blocking",
                        code="invalid_allocation_percent",
                        message="allocation_percent must be numeric when provided.",
                        entity_type="assignment",
                        entity_external_id=resource_external_id,
                        field="allocation_percent",
                    )
                )
                continue
            allocation_percent = int(allocation_percent)
            if allocation_percent <= 0 or allocation_percent > 100:
                issue_facts.append(
                    _build_issue(
                        snapshot_id=snapshot_id,
                        source_system=source_system,
                        severity="blocking",
                        code="invalid_allocation_range",
                        message="allocation_percent must be between 1 and 100.",
                        entity_type="assignment",
                        entity_external_id=resource_external_id,
                        field="allocation_percent",
                    )
                )
                continue

        assignment_key = "%s::%s" % (task_record.external_task_id, resource_external_id)
        if assignment_key in seen_assignments:
            issue_facts.append(
                _build_issue(
                    snapshot_id=snapshot_id,
                    source_system=source_system,
                    severity="blocking",
                    code="duplicate_assignment",
                    message="Duplicate assignment encountered for the same task/resource pair.",
                    entity_type="assignment",
                    entity_external_id=resource_external_id,
                    field="assignees",
                )
            )
            continue
        seen_assignments[assignment_key] = True

        normalized_resource_assignments.append(
            NormalizedResourceAssignmentRecord(
                assignment_id=_stable_id(
                    "assignment", task_record.task_id, resource_external_id
                ),
                source_snapshot_id=snapshot_id,
                source_system=source_system,
                task_id=task_record.task_id,
                task_external_id=task_record.external_task_id,
                resource_id=resource_id,
                resource_external_id=resource_external_id,
                allocation_percent=allocation_percent,
            )
        )


def _resolve_dependency(
    dependency_ref: Any,
    snapshot_id: str,
    source_system: str,
    project_external_id: str,
    successor_external_id: str,
    task_lookup: Dict[Tuple[str, str], NormalizedTaskRecord],
    normalized_dependencies: List[NormalizedDependencyRecord],
    issue_facts: List[SourceSetupIssueFact],
) -> None:
    predecessor_project_external_id = project_external_id
    predecessor_external_id = None

    if isinstance(dependency_ref, str):
        predecessor_external_id = dependency_ref
    elif isinstance(dependency_ref, dict):
        predecessor_external_id = dependency_ref.get("task_external_id")
        predecessor_project_external_id = dependency_ref.get(
            "project_external_id", project_external_id
        )
    else:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_dependency_reference",
                message="Dependency reference must be a task external_id or mapping object.",
                entity_type="dependency",
                entity_external_id=successor_external_id,
                field="depends_on_external_ids[]",
            )
        )
        return

    successor_task = task_lookup.get((project_external_id, successor_external_id))
    predecessor_task = task_lookup.get(
        (predecessor_project_external_id, predecessor_external_id)
    )

    if successor_task is None or predecessor_task is None:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="dependency_target_not_found",
                message="Dependency target must reference an existing normalized task.",
                entity_type="dependency",
                entity_external_id=successor_external_id,
                field="depends_on_external_ids",
            )
        )
        return

    normalized_dependencies.append(
        NormalizedDependencyRecord(
            dependency_id=_stable_id(
                "dependency",
                predecessor_task.task_id,
                successor_task.task_id,
            ),
            source_snapshot_id=snapshot_id,
            source_system=source_system,
            predecessor_task_id=predecessor_task.task_id,
            successor_task_id=successor_task.task_id,
            predecessor_external_task_id=predecessor_task.external_task_id,
            successor_external_task_id=successor_task.external_task_id,
        )
    )


def _normalize_effort(
    raw_task: Dict[str, Any],
    snapshot_id: str,
    source_system: str,
    task_external_id: str,
    issue_facts: List[SourceSetupIssueFact],
) -> Optional[float]:
    raw_effort = raw_task.get("effort")
    if raw_effort is None:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="missing_effort",
                message="effort is required for normalized planning inputs.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="effort",
            )
        )
        return None
    if not isinstance(raw_effort, dict):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_effort",
                message="effort must be an object with value and unit.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="effort",
            )
        )
        return None

    value = raw_effort.get("value")
    unit = raw_effort.get("unit")
    if not isinstance(value, (int, float)) or value <= 0:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_effort_value",
                message="effort.value must be a positive number.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="effort.value",
            )
        )
        return None
    if unit not in ("hours", "minutes"):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_effort_unit",
                message="effort.unit must be hours or minutes.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="effort.unit",
            )
        )
        return None

    if unit == "hours":
        return round(float(value), 4)
    return round(float(value) / 60.0, 4)


def _normalize_dates(
    raw_task: Dict[str, Any],
    snapshot_id: str,
    source_system: str,
    task_external_id: str,
    issue_facts: List[SourceSetupIssueFact],
) -> Tuple[Optional[str], Optional[str]]:
    raw_dates = raw_task.get("dates")
    if raw_dates is None:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="advisory",
                code="missing_date_window",
                message="No date window was provided for this task.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="dates",
            )
        )
        return None, None
    if not isinstance(raw_dates, dict):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_date_window",
                message="dates must be an object with start and due fields.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="dates",
            )
        )
        return None, None

    start_value = raw_dates.get("start")
    due_value = raw_dates.get("due")
    if start_value is None and due_value is None:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="advisory",
                code="missing_date_window",
                message="No date window was provided for this task.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="dates",
            )
        )
        return None, None

    if bool(start_value) != bool(due_value):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="advisory",
                code="incomplete_date_window",
                message="Both start and due dates should be present together.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="dates",
            )
        )

    normalized_start = _validate_date_value(
        snapshot_id=snapshot_id,
        source_system=source_system,
        task_external_id=task_external_id,
        field="dates.start",
        value=start_value,
        issue_facts=issue_facts,
    )
    normalized_due = _validate_date_value(
        snapshot_id=snapshot_id,
        source_system=source_system,
        task_external_id=task_external_id,
        field="dates.due",
        value=due_value,
        issue_facts=issue_facts,
    )

    if normalized_start and normalized_due and normalized_start > normalized_due:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_date_order",
                message="dates.start must be on or before dates.due.",
                entity_type="task",
                entity_external_id=task_external_id,
                field="dates",
            )
        )

    return normalized_start, normalized_due


def _validate_date_value(
    snapshot_id: str,
    source_system: str,
    task_external_id: str,
    field: str,
    value: Any,
    issue_facts: List[SourceSetupIssueFact],
) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_date_value",
                message="%s must be a YYYY-MM-DD string." % field,
                entity_type="task",
                entity_external_id=task_external_id,
                field=field,
            )
        )
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        issue_facts.append(
            _build_issue(
                snapshot_id=snapshot_id,
                source_system=source_system,
                severity="blocking",
                code="invalid_date_value",
                message="%s must be a valid YYYY-MM-DD date." % field,
                entity_type="task",
                entity_external_id=task_external_id,
                field=field,
            )
        )
        return None


def _normalize_resource_exception(
    raw_exception: Any,
    snapshot_id: str,
    source_system: str,
    resource_id: str,
    resource_external_id: str,
) -> Optional[NormalizedResourceExceptionRecord]:
    if not isinstance(raw_exception, dict):
        return None

    exception_date = raw_exception.get("date")
    if not isinstance(exception_date, str):
        return None
    try:
        normalized_date = date.fromisoformat(exception_date).isoformat()
    except ValueError:
        return None

    available_capacity_hours = _normalize_optional_non_negative_float(
        raw_exception.get("available_capacity_hours")
    )
    if available_capacity_hours is None:
        return None

    reason = raw_exception.get("reason")
    if reason is not None and not isinstance(reason, str):
        reason = None

    return NormalizedResourceExceptionRecord(
        exception_id=_stable_id(
            "resource-exception",
            resource_id,
            normalized_date,
        ),
        source_snapshot_id=snapshot_id,
        source_system=source_system,
        resource_id=resource_id,
        resource_external_id=resource_external_id,
        date=normalized_date,
        available_capacity_hours=available_capacity_hours,
        reason=reason,
    )


def _normalize_working_days(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []

    normalized_days: List[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized_item = item.strip().lower()
        if normalized_item in VALID_WORKING_DAYS and normalized_item not in normalized_days:
            normalized_days.append(normalized_item)
    return normalized_days


def _normalize_optional_positive_float(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)):
        return None
    normalized_value = round(float(value), 4)
    if normalized_value <= 0:
        return None
    return normalized_value


def _normalize_optional_non_negative_float(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)):
        return None
    normalized_value = round(float(value), 4)
    if normalized_value < 0:
        return None
    return normalized_value


def _normalize_optional_ratio(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)):
        return None
    normalized_value = round(float(value), 4)
    if normalized_value <= 0 or normalized_value > 1:
        return None
    return normalized_value


def _build_readiness(issue_facts: List[SourceSetupIssueFact]) -> SourceReadiness:
    blocking_issue_count = len(
        [issue for issue in issue_facts if issue.severity == "blocking"]
    )
    advisory_issue_count = len(
        [issue for issue in issue_facts if issue.severity == "advisory"]
    )
    if blocking_issue_count:
        state = "blocked"
        runnable = False
    elif advisory_issue_count:
        state = "ready_with_advisories"
        runnable = True
    else:
        state = "ready"
        runnable = True

    return SourceReadiness(
        state=state,
        runnable=runnable,
        blocking_issue_count=blocking_issue_count,
        advisory_issue_count=advisory_issue_count,
        total_issue_count=len(issue_facts),
    )


def _build_issue(
    snapshot_id: str,
    source_system: str,
    severity: str,
    code: str,
    message: str,
    entity_type: str,
    entity_external_id: Optional[str],
    field: Optional[str],
) -> SourceSetupIssueFact:
    issue_id = _stable_id(
        "issue",
        snapshot_id,
        severity,
        code,
        entity_type,
        entity_external_id or "none",
        field or "none",
    )
    return SourceSetupIssueFact(
        issue_id=issue_id,
        source_snapshot_id=snapshot_id,
        source_system=source_system,
        severity=severity,
        code=code,
        message=message,
        entity_type=entity_type,
        entity_external_id=entity_external_id,
        field=field,
    )


def _sort_mappings(mappings: Any) -> List[SourceMapping]:
    return sorted(
        mappings,
        key=lambda mapping: (
            mapping.scope_external_id or "",
            mapping.external_id,
            mapping.internal_id,
        ),
    )


def _sorted_records(records: List[Any]) -> List[Any]:
    return sorted(
        records,
        key=lambda record: (
            1 if not isinstance(record, dict) else 0,
            ""
            if not isinstance(record, dict)
            else str(record.get("external_id", "")),
        ),
    )


def _canonical_json(raw_payload: Dict[str, Any]) -> str:
    return json.dumps(raw_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _stable_id(prefix: str, *parts: str) -> str:
    joined = "::".join(str(part) for part in parts)
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
    return "%s_%s" % (prefix, digest)
