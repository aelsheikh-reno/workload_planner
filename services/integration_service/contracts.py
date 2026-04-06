"""Explicit Integration Service contracts for normalized source intake."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SourceArtifact:
    artifact_id: str
    external_artifact_id: str
    source_system: str
    captured_at: str
    payload_digest: str
    raw_payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceSnapshot:
    snapshot_id: str
    artifact_id: str
    source_system: str
    captured_at: str
    project_count: int
    task_count: int
    dependency_count: int
    assignment_count: int
    issue_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceMapping:
    mapping_id: str
    external_id: str
    scope_external_id: Optional[str]
    internal_id: str
    source_system: str
    display_name: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedTaskRecord:
    task_id: str
    source_snapshot_id: str
    source_system: str
    external_task_id: str
    project_id: str
    project_external_id: str
    parent_task_id: Optional[str]
    name: str
    hierarchy_path: List[str]
    hierarchy_depth: int
    effort_hours: Optional[float]
    start_date: Optional[str]
    due_date: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedDependencyRecord:
    dependency_id: str
    source_snapshot_id: str
    source_system: str
    predecessor_task_id: str
    successor_task_id: str
    predecessor_external_task_id: str
    successor_external_task_id: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedResourceAssignmentRecord:
    assignment_id: str
    source_snapshot_id: str
    source_system: str
    task_id: str
    task_external_id: str
    resource_id: str
    resource_external_id: str
    allocation_percent: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedResourceRecord:
    resource_id: str
    source_snapshot_id: str
    source_system: str
    external_resource_id: str
    display_name: Optional[str]
    calendar_id: str
    calendar_name: Optional[str]
    default_daily_capacity_hours: Optional[float]
    working_days: List[str]
    availability_ratio: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedResourceExceptionRecord:
    exception_id: str
    source_snapshot_id: str
    source_system: str
    resource_id: str
    resource_external_id: str
    date: str
    available_capacity_hours: float
    reason: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceSetupIssueFact:
    issue_id: str
    source_snapshot_id: str
    source_system: str
    severity: str
    code: str
    message: str
    entity_type: str
    entity_external_id: Optional[str]
    field: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceReadiness:
    state: str
    runnable: bool
    blocking_issue_count: int
    advisory_issue_count: int
    total_issue_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NormalizedSourceBundle:
    artifact: SourceArtifact
    snapshot: SourceSnapshot
    project_mappings: List[SourceMapping]
    task_mappings: List[SourceMapping]
    resource_mappings: List[SourceMapping]
    tasks: List[NormalizedTaskRecord]
    dependencies: List[NormalizedDependencyRecord]
    resource_assignments: List[NormalizedResourceAssignmentRecord]
    resources: List[NormalizedResourceRecord]
    resource_exceptions: List[NormalizedResourceExceptionRecord]
    issue_facts: List[SourceSetupIssueFact]
    source_readiness: SourceReadiness

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "snapshot": self.snapshot.to_dict(),
            "project_mappings": [mapping.to_dict() for mapping in self.project_mappings],
            "task_mappings": [mapping.to_dict() for mapping in self.task_mappings],
            "resource_mappings": [
                mapping.to_dict() for mapping in self.resource_mappings
            ],
            "tasks": [task.to_dict() for task in self.tasks],
            "dependencies": [
                dependency.to_dict() for dependency in self.dependencies
            ],
            "resource_assignments": [
                assignment.to_dict() for assignment in self.resource_assignments
            ],
            "resources": [resource.to_dict() for resource in self.resources],
            "resource_exceptions": [
                exception.to_dict() for exception in self.resource_exceptions
            ],
            "issue_facts": [issue.to_dict() for issue in self.issue_facts],
            "source_readiness": self.source_readiness.to_dict(),
        }
