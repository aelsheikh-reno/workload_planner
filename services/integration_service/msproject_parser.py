"""Parse MS Project XML exports (.xml) into NormalizedSourceBundle.

MS Project XML structure (Microsoft Project namespace):
  <Project xmlns="http://schemas.microsoft.com/project">
    <Tasks>
      <Task>
        <UID>1</UID>
        <Name>Task A</Name>
        <Work>PT40H0M0S</Work>         <!-- effort in ISO 8601 duration -->
        <Start>2026-04-06T08:00:00</Start>
        <Finish>2026-04-10T17:00:00</Finish>
        <Summary>0</Summary>           <!-- 1 = summary/parent task -->
        <PredecessorLink>
          <PredecessorUID>2</PredecessorUID>
          <Type>1</Type>               <!-- 0=FF, 1=FS, 2=SF, 3=SS -->
          <LinkLag>0</LinkLag>
        </PredecessorLink>
      </Task>
    </Tasks>
    <Resources>
      <Resource>
        <UID>1</UID>
        <Name>Alice</Name>
        <MaxUnits>1</MaxUnits>         <!-- 1.0 = 100% = 1 FTE -->
        <StandardRate>0</StandardRate>
      </Resource>
    </Resources>
    <Assignments>
      <Assignment>
        <TaskUID>1</TaskUID>
        <ResourceUID>1</ResourceUID>
        <Work>PT40H0M0S</Work>
      </Assignment>
    </Assignments>
  </Project>

Dependency type mapping (MS Project <Type> value):
  0 → FF (Finish-to-Finish)
  1 → FS (Finish-to-Start)   ← most common
  2 → SF (Start-to-Finish)
  3 → SS (Start-to-Start)

Only FS and FF are respected by the planning engine; SS/SF are stored but ignored.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from .contracts import (
    NormalizedDependencyRecord,
    NormalizedResourceAssignmentRecord,
    NormalizedResourceExceptionRecord,
    NormalizedResourceRecord,
    NormalizedSourceBundle,
    NormalizedTaskRecord,
    SourceArtifact,
    SourceMapping,
    SourceReadiness,
    SourceSnapshot,
    SourceSetupIssueFact,
)

_SOURCE_SYSTEM = "msproject"
_NS = "http://schemas.microsoft.com/project"  # default namespace

# MS Project <Type> → our dependency_type string
_DEP_TYPE_MAP = {
    "0": "FF",
    "1": "FS",
    "2": "SF",
    "3": "SS",
}


def _tag(local: str) -> str:
    """Return fully-qualified XML tag with MS Project namespace."""
    return "{%s}%s" % (_NS, local)


def _text(element: ET.Element, local: str, default: str = "") -> str:
    """Get text of a child element, or default if missing."""
    child = element.find(_tag(local))
    return (child.text or "").strip() if child is not None else default


def _parse_pt_duration(s: str) -> Optional[float]:
    """Convert ISO 8601 duration 'PT40H30M0S' → 40.5 hours.

    MS Project uses format: PT<H>H<M>M<S>S
    Falls back to parsing just hours if minutes/seconds are omitted.
    """
    if not s:
        return None
    s = s.strip()
    if not s.startswith("PT"):
        return None
    # Remove PT prefix
    s = s[2:]
    hours = 0.0
    minutes = 0.0
    seconds = 0.0
    m = re.match(r"(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?", s)
    if m:
        hours = float(m.group(1) or 0)
        minutes = float(m.group(2) or 0)
        seconds = float(m.group(3) or 0)
    return hours + minutes / 60.0 + seconds / 3600.0


def _iso_date(s: str) -> Optional[str]:
    """Extract YYYY-MM-DD from an ISO datetime string."""
    if not s:
        return None
    return s[:10] if len(s) >= 10 else None


class MSProjectXMLParser:
    """Parses an MS Project XML export into a NormalizedSourceBundle."""

    def parse(self, xml_bytes: bytes) -> NormalizedSourceBundle:
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as exc:
            raise ValueError("Invalid MS Project XML: %s" % exc)

        # Strip namespace from root if needed (some exports omit it)
        if root.tag == "Project":
            # No namespace — wrap helpers to work without namespace
            return self._parse_no_ns(root, xml_bytes)

        snapshot_id = hashlib.sha1(xml_bytes).hexdigest()[:24]
        artifact_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # ── Parse resources ───────────────────────────────────────────────────
        resources: List[NormalizedResourceRecord] = []
        resource_mappings: List[SourceMapping] = []
        uid_to_resource_id: Dict[str, str] = {}

        for res_el in root.findall(".//%s" % _tag("Resource")):
            uid = _text(res_el, "UID")
            if uid in ("0", ""):  # UID 0 is the "unassigned" pseudo-resource
                continue
            name = _text(res_el, "Name") or "Resource_%s" % uid
            max_units_s = _text(res_el, "MaxUnits", "1")
            try:
                max_units = float(max_units_s)
            except ValueError:
                max_units = 1.0

            resource_id = "res-%s-%s" % (snapshot_id, uid)
            uid_to_resource_id[uid] = resource_id

            resources.append(NormalizedResourceRecord(
                resource_id=resource_id,
                source_snapshot_id=snapshot_id,
                source_system=_SOURCE_SYSTEM,
                external_resource_id="msproject-res-%s" % uid,
                display_name=name,
                calendar_id="default",
                calendar_name="Standard",
                default_daily_capacity_hours=8.0 * max_units,
                working_days=["Sun", "Mon", "Tue", "Wed", "Thu"],
                availability_ratio=max_units,
            ))
            resource_mappings.append(SourceMapping(
                mapping_id="rm-%s-%s" % (snapshot_id, uid),
                external_id="msproject-res-%s" % uid,
                scope_external_id=None,
                internal_id=resource_id,
                source_system=_SOURCE_SYSTEM,
                display_name=name,
            ))

        # ── Parse tasks ───────────────────────────────────────────────────────
        tasks: List[NormalizedTaskRecord] = []
        task_mappings: List[SourceMapping] = []
        dependencies: List[NormalizedDependencyRecord] = []
        uid_to_task_id: Dict[str, str] = {}
        # For dependency resolution after all tasks are parsed
        pending_deps: List[Tuple[str, str, str]] = []  # (successor_uid, predecessor_uid, dep_type)

        # Extract project name from XML
        project_name = _text(root, "Name") or _text(root, "Title") or "Imported Project"

        # Determine project external_id from file content hash
        project_ext_id = "msproject-%s" % snapshot_id[:12]
        project_id = "proj-%s" % snapshot_id[:12]

        # First pass: collect raw task data in document order (needed for hierarchy)
        tasks_raw: List[Tuple[str, int, str]] = []  # (uid, outline_level, name)
        task_raw_data: Dict[str, dict] = {}  # uid → {work_s, start_date, due_date, is_summary, pred_links}

        for task_el in root.findall(".//%s" % _tag("Task")):
            uid = _text(task_el, "UID")
            if uid in ("0", ""):
                continue
            name = _text(task_el, "Name")
            if not name:
                continue

            summary = _text(task_el, "Summary", "0")
            is_summary = summary == "1"

            outline_level_el = task_el.find(_tag("OutlineLevel"))
            outline_level = int(outline_level_el.text) if outline_level_el is not None else 0

            work_s = _text(task_el, "Work")
            start_date = _iso_date(_text(task_el, "Start"))
            due_date = _iso_date(_text(task_el, "Finish"))

            pred_links = []
            for pred_el in task_el.findall(_tag("PredecessorLink")):
                pred_uid = _text(pred_el, "PredecessorUID")
                dep_type_code = _text(pred_el, "Type", "1")
                dep_type = _DEP_TYPE_MAP.get(dep_type_code, "FS")
                if pred_uid:
                    pred_links.append((pred_uid, dep_type))

            tasks_raw.append((uid, outline_level, name))
            task_raw_data[uid] = {
                "work_s": work_s,
                "start_date": start_date,
                "due_date": due_date,
                "is_summary": is_summary,
                "pred_links": pred_links,
            }

        # Resolve parent-child hierarchy using OutlineLevel (stack algorithm)
        # Parent of a task at level N is the most-recently-seen task at level N-1
        uid_to_parent_uid: Dict[str, Optional[str]] = {}
        parent_stack: Dict[int, str] = {}  # outline_level → uid
        for uid, level, _ in tasks_raw:
            uid_to_parent_uid[uid] = parent_stack.get(level - 1)
            parent_stack[level] = uid
            # Invalidate any deeper levels to prevent stale parents
            for k in [k for k in list(parent_stack) if k > level]:
                del parent_stack[k]

        # Second pass: build NormalizedTaskRecord list using resolved hierarchy
        for uid, outline_level, name in tasks_raw:
            raw = task_raw_data[uid]
            task_id = "task-%s-%s" % (snapshot_id, uid)
            uid_to_task_id[uid] = task_id

            parent_uid = uid_to_parent_uid.get(uid)
            parent_task_ext_id = "msproject-task-%s" % parent_uid if parent_uid else None
            effort_hours = _parse_pt_duration(raw["work_s"])

            tasks.append(NormalizedTaskRecord(
                task_id=task_id,
                source_snapshot_id=snapshot_id,
                source_system=_SOURCE_SYSTEM,
                external_task_id="msproject-task-%s" % uid,
                project_id=project_id,
                project_external_id=project_ext_id,
                parent_task_id=parent_task_ext_id,
                name=name,
                hierarchy_path=[name],
                hierarchy_depth=outline_level,
                effort_hours=effort_hours if not raw["is_summary"] else None,
                start_date=raw["start_date"],
                due_date=raw["due_date"],
            ))
            task_mappings.append(SourceMapping(
                mapping_id="tm-%s-%s" % (snapshot_id, uid),
                external_id="msproject-task-%s" % uid,
                scope_external_id=project_ext_id,
                internal_id=task_id,
                source_system=_SOURCE_SYSTEM,
                display_name=name,
            ))

            for pred_uid, dep_type in raw["pred_links"]:
                pending_deps.append((uid, pred_uid, dep_type))

        # Resolve pending dependencies now that all task UIDs are known
        for idx, (suc_uid, pred_uid, dep_type) in enumerate(pending_deps):
            suc_task_id = uid_to_task_id.get(suc_uid)
            pred_task_id = uid_to_task_id.get(pred_uid)
            if suc_task_id is None or pred_task_id is None:
                continue
            dependencies.append(NormalizedDependencyRecord(
                dependency_id="dep-%s-%d" % (snapshot_id, idx),
                source_snapshot_id=snapshot_id,
                source_system=_SOURCE_SYSTEM,
                predecessor_task_id=pred_task_id,
                successor_task_id=suc_task_id,
                predecessor_external_task_id="msproject-task-%s" % pred_uid,
                successor_external_task_id="msproject-task-%s" % suc_uid,
                dependency_type=dep_type,
            ))

        # ── Parse assignments ─────────────────────────────────────────────────
        resource_assignments: List[NormalizedResourceAssignmentRecord] = []

        for idx, assign_el in enumerate(root.findall(".//%s" % _tag("Assignment"))):
            task_uid = _text(assign_el, "TaskUID")
            res_uid = _text(assign_el, "ResourceUID")
            if res_uid in ("0", "") or task_uid in ("0", ""):
                continue
            task_id = uid_to_task_id.get(task_uid)
            resource_id = uid_to_resource_id.get(res_uid)
            if task_id is None or resource_id is None:
                continue

            resource_assignments.append(NormalizedResourceAssignmentRecord(
                assignment_id="assign-%s-%d" % (snapshot_id, idx),
                source_snapshot_id=snapshot_id,
                source_system=_SOURCE_SYSTEM,
                task_id=task_id,
                task_external_id="msproject-task-%s" % task_uid,
                resource_id=resource_id,
                resource_external_id="msproject-res-%s" % res_uid,
                allocation_percent=100,
            ))

        # ── Build snapshot and readiness ──────────────────────────────────────
        issue_facts: List[SourceSetupIssueFact] = []
        if not tasks:
            issue_facts.append(SourceSetupIssueFact(
                issue_id="iss-no-tasks",
                source_snapshot_id=snapshot_id,
                source_system=_SOURCE_SYSTEM,
                severity="blocking",
                code="no_tasks",
                message="No tasks found in the MS Project XML file.",
                entity_type="project",
                entity_external_id=project_ext_id,
                field=None,
            ))
        if not resources:
            issue_facts.append(SourceSetupIssueFact(
                issue_id="iss-no-resources",
                source_snapshot_id=snapshot_id,
                source_system=_SOURCE_SYSTEM,
                severity="advisory",
                code="no_resources",
                message="No resources found in the MS Project XML file. Add team members in the app.",
                entity_type="project",
                entity_external_id=project_ext_id,
                field=None,
            ))

        blocking = sum(1 for i in issue_facts if i.severity == "blocking")
        advisory = sum(1 for i in issue_facts if i.severity == "advisory")

        snapshot = SourceSnapshot(
            snapshot_id=snapshot_id,
            artifact_id=artifact_id,
            source_system=_SOURCE_SYSTEM,
            captured_at=now,
            project_count=1,
            task_count=len(tasks),
            dependency_count=len(dependencies),
            assignment_count=len(resource_assignments),
            issue_count=len(issue_facts),
        )
        artifact = SourceArtifact(
            artifact_id=artifact_id,
            external_artifact_id="msproject-file-%s" % snapshot_id[:12],
            source_system=_SOURCE_SYSTEM,
            captured_at=now,
            payload_digest=snapshot_id,
            raw_payload={},
        )
        source_readiness = SourceReadiness(
            state="blocked" if blocking else "ready",
            runnable=blocking == 0,
            blocking_issue_count=blocking,
            advisory_issue_count=advisory,
            total_issue_count=len(issue_facts),
        )

        return NormalizedSourceBundle(
            artifact=artifact,
            snapshot=snapshot,
            project_mappings=[SourceMapping(
                mapping_id="pm-%s" % snapshot_id[:12],
                external_id=project_ext_id,
                scope_external_id=None,
                internal_id=project_id,
                source_system=_SOURCE_SYSTEM,
                display_name=project_name,
            )],
            task_mappings=task_mappings,
            resource_mappings=resource_mappings,
            tasks=tasks,
            dependencies=dependencies,
            resource_assignments=resource_assignments,
            resources=resources,
            resource_exceptions=[],
            issue_facts=issue_facts,
            source_readiness=source_readiness,
        )

    def _parse_no_ns(self, root: ET.Element, xml_bytes: bytes) -> "NormalizedSourceBundle":
        """Fallback: parse XML without namespace prefix."""
        # Re-parse with namespace stripped from all tags
        xml_str = xml_bytes.decode("utf-8", errors="replace")
        # Inject namespace so _tag() lookups work
        if 'xmlns=' not in xml_str and 'xmlns:' not in xml_str:
            xml_str = xml_str.replace("<Project", '<Project xmlns="%s"' % _NS, 1)
            return self.parse(xml_str.encode("utf-8"))
        return self.parse(xml_bytes)
