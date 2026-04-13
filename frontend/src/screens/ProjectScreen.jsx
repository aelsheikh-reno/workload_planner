import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { requestJson } from "../api";

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtDate(d) {
  return d ? d.slice(0, 10) : "—";
}

function addDays(dateStr, n) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function weekStart(dateStr) {
  const d = new Date(dateStr);
  const day = d.getDay();
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}

function weeksInRange(start, end) {
  const weeks = [];
  let cur = weekStart(start);
  const last = weekStart(end);
  while (cur <= last) {
    weeks.push(cur);
    cur = addDays(cur, 7);
  }
  return weeks;
}

// ── Tabs ───────────────────────────────────────────────────────────────────────

function Tab({ label, active, onClick }) {
  return (
    <button
      type="button"
      className={`tab-button${active ? " tab-button--active" : ""}`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

// ── Tasks Tab ──────────────────────────────────────────────────────────────────

function TasksTab({ tasks, dependencies, onUpdate, collapsedIds, setCollapsedIds, projectId }) {
  const [editing, setEditing] = useState(null);      // "buffer-{id}" or "effort-{id}"
  const [editVal, setEditVal] = useState("");
  const [expandedTaskId, setExpandedTaskId] = useState(null);
  const [taskAllocs, setTaskAllocs] = useState([]);

  useEffect(() => {
    if (!projectId) return;
    requestJson("/api/schedule/calendar", {
      query: { start: "2020-01-01", end: "2030-12-31", projectId: String(projectId) },
    })
      .then((d) => setTaskAllocs(d.day_allocations || []))
      .catch(() => {});
  }, [projectId, tasks]);

  async function saveField(taskId, field) {
    const hours = parseFloat(editVal);
    if (isNaN(hours)) { setEditing(null); return; }
    await requestJson(`/api/float/tasks/${taskId}`, {
      method: "PATCH",
      body: { [field]: hours },
    });
    setEditing(null);
    onUpdate();
  }

  function toggleCollapse(taskId) {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId); else next.add(taskId);
      return next;
    });
  }

  // Build lookup maps for tree rendering
  const taskById = Object.fromEntries(tasks.map((t) => [t.id, t]));

  // depsFor[successorId] = [{predecessor_id, dependency_type}]
  const depsFor = {};
  (dependencies || []).forEach((d) => {
    if (!depsFor[d.successor_id]) depsFor[d.successor_id] = [];
    depsFor[d.successor_id].push(d);
  });

  // Build parent → children map and DFS-ordered flat list
  const childrenOf = {};
  tasks.forEach((t) => {
    const pid = t.parent_id ?? null;
    if (!childrenOf[pid]) childrenOf[pid] = [];
    childrenOf[pid].push(t);
  });

  // All parent IDs for Collapse All/Expand All
  const allParentIds = tasks.filter((t) => !!childrenOf[t.id]).map((t) => t.id);

  function flattenTree(parentId) {
    return (childrenOf[parentId] || []).flatMap((t) => [
      t,
      ...(collapsedIds.has(t.id) ? [] : flattenTree(t.id)),
    ]);
  }
  const ordered = flattenTree(null);

  return (
    <div className="tab-content">
      {allParentIds.length > 0 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 8, fontSize: ".78rem" }}>
          <button type="button" className="ghost-button ghost-button--inline" onClick={() => setCollapsedIds(new Set(allParentIds))} title="Collapse All">
            &#8863; Collapse All
          </button>
          <button type="button" className="ghost-button ghost-button--inline" onClick={() => setCollapsedIds(new Set())} title="Expand All">
            &#8862; Expand All
          </button>
        </div>
      )}
      <table className="data-table">
        <thead>
          <tr>
            <th>Task</th>
            <th>Assignee</th>
            <th>Effort (h)</th>
            <th>Buffer (h)</th>
            <th>Start</th>
            <th>End</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((t) => {
            const depth = t.hierarchy_depth || 0;
            const isParent = !!childrenOf[t.id];
            const isCollapsed = collapsedIds.has(t.id);
            const childCount = (childrenOf[t.id] || []).length;
            const taskDeps = depsFor[t.id] || [];
            const chunks = expandedTaskId === t.id
              ? taskAllocs.filter((a) => a.task_id === t.id).sort((a, b) => a.date.localeCompare(b.date))
              : [];
            const isCompleted = t.status === "completed";
            return (
              <React.Fragment key={t.id}>
              <tr
                style={{
                  ...(depth === 0 && isParent ? { background: "var(--color-surface-2, #f5f7fa)" } : {}),
                  ...(isCompleted ? { opacity: 0.5, background: "#f9fafb" } : {}),
                  cursor: "pointer",
                }}
                onClick={() => setExpandedTaskId(expandedTaskId === t.id ? null : t.id)}
              >
                <td>
                  <div style={{ paddingLeft: depth * 20, display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontWeight: depth === 0 && isParent ? 600 : 400, display: "flex", alignItems: "center", gap: 4 }}>
                      {isParent ? (
                        <span
                          onClick={(e) => { e.stopPropagation(); toggleCollapse(t.id); }}
                          style={{ cursor: "pointer", display: "inline-block", width: 16, textAlign: "center", color: "var(--muted)", userSelect: "none", fontSize: ".82rem" }}
                          title={isCollapsed ? "Expand children" : "Collapse children"}
                        >
                          {isCollapsed ? "\u25B8" : "\u25BE"}
                        </span>
                      ) : (
                        <span style={{ display: "inline-block", width: 16 }} />
                      )}
                      {depth > 0 && <span className="muted" style={{ marginRight: 4 }}>↳</span>}
                      {t.name}
                      {isParent && isCollapsed && <span className="muted" style={{ marginLeft: 6, fontSize: ".72rem", fontWeight: 400 }}>({childCount} subtask{childCount !== 1 ? "s" : ""})</span>}
                      {expandedTaskId === t.id && <span className="muted" style={{ marginLeft: 6, fontSize: ".68rem" }}>(chunks)</span>}
                    </span>
                    {taskDeps.length > 0 && (
                      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {taskDeps.map((d) => (
                          <span
                            key={d.predecessor_id}
                            className="dep-badge"
                            title={"%s dependency on: %s".replace("%s", d.dependency_type).replace("%s", taskById[d.predecessor_id]?.name ?? d.predecessor_id)}
                          >
                            {d.dependency_type} ← {taskById[d.predecessor_id]?.name ?? ("task #" + d.predecessor_id)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </td>
                <td>
                  {(t.assignees || []).length > 0 ? (
                    <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                      {t.assignees.map((a) => (
                        <span
                          key={a.id}
                          title={a.display_name}
                          style={{
                            width: 22, height: 22, borderRadius: "50%",
                            background: a.avatar_color || "#4A90D9",
                            display: "inline-flex", alignItems: "center", justifyContent: "center",
                            color: "#fff", fontSize: ".6rem", fontWeight: 700,
                          }}
                        >
                          {(a.display_name || "?")[0]}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="muted" style={{ fontSize: ".78rem" }}>—</span>
                  )}
                </td>
                <td>
                  {isCompleted ? (
                    <span className="muted">{t.estimated_hours ?? "—"}</span>
                  ) : editing === `effort-${t.id}` ? (
                    <span style={{ display: "flex", gap: 4 }}>
                      <input
                        type="number"
                        min="0"
                        step="0.5"
                        value={editVal}
                        onChange={(e) => setEditVal(e.target.value)}
                        style={{ width: 64 }}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveField(t.id, "estimated_hours");
                          if (e.key === "Escape") setEditing(null);
                        }}
                      />
                      <button type="button" className="mini-button" onClick={() => saveField(t.id, "estimated_hours")}>✓</button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="ghost-button ghost-button--inline"
                      onClick={() => { setEditing(`effort-${t.id}`); setEditVal(t.estimated_hours ?? ""); }}
                      title="Click to set effort hours"
                    >
                      {t.estimated_hours != null ? t.estimated_hours : <span className="muted">+add</span>}
                    </button>
                  )}
                </td>
                <td>
                  {isCompleted ? (
                    <span className="muted">{t.buffer_hours ?? "—"}</span>
                  ) : editing === `buffer-${t.id}` ? (
                    <span style={{ display: "flex", gap: 4 }}>
                      <input
                        type="number"
                        min="0"
                        step="0.5"
                        value={editVal}
                        onChange={(e) => setEditVal(e.target.value)}
                        style={{ width: 64 }}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveField(t.id, "buffer_hours");
                          if (e.key === "Escape") setEditing(null);
                        }}
                      />
                      <button type="button" className="mini-button" onClick={() => saveField(t.id, "buffer_hours")}>✓</button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="ghost-button ghost-button--inline"
                      onClick={() => { setEditing(`buffer-${t.id}`); setEditVal(t.buffer_hours ?? ""); }}
                      title="Click to set buffer hours"
                    >
                      {t.buffer_hours != null ? t.buffer_hours : <span className="muted">+add</span>}
                    </button>
                  )}
                </td>
                <td>{fmtDate(t.scheduled_start_date)}</td>
                <td>{fmtDate(t.scheduled_end_date)}</td>
                <td>
                  <span className={`status-badge status-badge--${t.status}`}>{t.status}</span>
                </td>
              </tr>
              {chunks.length > 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: 0 }}>
                    <div style={{ background: "var(--panel-alt)", padding: "8px 12px 8px 40px", borderBottom: "2px solid var(--line-strong)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: ".72rem", fontWeight: 600, color: "var(--muted)" }}>
                          SCHEDULE CHUNKS — {chunks.reduce((s, c) => s + c.hours, 0)}h across {chunks.length} day{chunks.length !== 1 ? "s" : ""}
                        </span>
                        <span style={{ flex: 1 }} />
                        <button
                          type="button"
                          className="ghost-button"
                          style={{ fontSize: ".68rem", padding: "1px 6px" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            requestJson("/api/schedule/pin-task", {
                              method: "POST",
                              body: { task_id: t.id, pinned: true },
                            }).then(() => { setTaskAllocs([...taskAllocs]); onUpdate(); }).catch(() => {});
                          }}
                        >
                          Pin All
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          style={{ fontSize: ".68rem", padding: "1px 6px" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            requestJson("/api/schedule/pin-task", {
                              method: "POST",
                              body: { task_id: t.id, pinned: false },
                            }).then(() => { setTaskAllocs([...taskAllocs]); onUpdate(); }).catch(() => {});
                          }}
                        >
                          Unpin All
                        </button>
                      </div>
                      <table style={{ width: "100%", fontSize: ".8rem", borderCollapse: "collapse" }}>
                        <thead>
                          <tr style={{ color: "var(--muted)", fontSize: ".72rem" }}>
                            <th style={{ textAlign: "left", padding: "2px 8px", fontWeight: 600 }}>Date</th>
                            <th style={{ textAlign: "left", padding: "2px 8px", fontWeight: 600 }}>Member</th>
                            <th style={{ textAlign: "right", padding: "2px 8px", fontWeight: 600 }}>Hours</th>
                            <th style={{ textAlign: "left", padding: "2px 8px", fontWeight: 600 }}>Source</th>
                            <th style={{ textAlign: "center", padding: "2px 8px", fontWeight: 600 }}>Pin</th>
                          </tr>
                        </thead>
                        <tbody>
                          {chunks.map((c, i) => (
                            <tr key={i} style={{ borderTop: "1px solid var(--line)" }}>
                              <td style={{ padding: "3px 8px" }}>{c.date}</td>
                              <td style={{ padding: "3px 8px" }}>
                                <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                  <span style={{
                                    width: 16, height: 16, borderRadius: "50%",
                                    background: "#4A90D9", display: "inline-flex",
                                    alignItems: "center", justifyContent: "center",
                                    color: "#fff", fontSize: ".5rem", fontWeight: 700,
                                  }}>{(c.member_name || "?")[0]}</span>
                                  {c.member_name}
                                </span>
                              </td>
                              <td style={{ padding: "3px 8px", textAlign: "right", fontWeight: 600 }}>{c.hours}h</td>
                              <td style={{ padding: "3px 8px" }}>
                                <span style={{ fontSize: ".68rem", color: c.source === "manual" ? "#d97706" : "var(--muted)" }}>
                                  {c.source}{c.pinned ? " \uD83D\uDCCC" : ""}
                                </span>
                              </td>
                              <td style={{ padding: "3px 8px", textAlign: "center" }}>
                                <button
                                  type="button"
                                  className="ghost-button ghost-button--inline"
                                  style={{ fontSize: ".68rem", color: c.pinned ? "#ca8a04" : "var(--muted)" }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    requestJson("/api/schedule/pin", {
                                      method: "POST",
                                      body: { task_id: c.task_id, member_id: c.member_id, date: c.date, pinned: !c.pinned },
                                    }).then(() => {
                                      // Reload allocs to reflect pin state
                                      requestJson("/api/schedule/calendar", {
                                        query: { start: "2020-01-01", end: "2030-12-31", projectId: String(projectId) },
                                      }).then((d) => setTaskAllocs(d.day_allocations || [])).catch(() => {});
                                    }).catch(() => {});
                                  }}
                                >
                                  {c.pinned ? "Unpin" : "Pin"}
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </td>
                </tr>
              )}
              </React.Fragment>
            );
          })}
          {tasks.length === 0 && (
            <tr><td colSpan={7} className="muted" style={{ textAlign: "center", padding: "2rem" }}>No tasks</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Schedule Tab ───────────────────────────────────────────────────────────────

function ScheduleTab({ projectId, projectMembers, allMembers, onTeamChange, tasks: propTasks, dependencies, collapsedIds, setCollapsedIds }) {
  const today = new Date().toISOString().slice(0, 10);
  const [startDate, setStartDate] = useState(addDays(today, -14));
  const [endDate, setEndDate] = useState(addDays(today, 42));
  const [allocs, setAllocs] = useState([]);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState(null);
  const [showTeamPopover, setShowTeamPopover] = useState(false);
  const [detailTask, setDetailTask] = useState(null);
  const [dragData, setDragData] = useState(null);
  const [dropTarget, setDropTarget] = useState(null);
  const [dropPrompt, setDropPrompt] = useState(null);
  const [dropMode, setDropMode] = useState("single");
  const [reassignChunk, setReassignChunk] = useState(null);
  const [reassignToMember, setReassignToMember] = useState("");
  const [reassignMode, setReassignMode] = useState("single");
  const [removalInfo, setRemovalInfo] = useState(null); // {memberId, affectedTasks, reassignMap}
  const [depWarning, setDepWarning] = useState(null);
  const [utilMode, setUtilMode] = useState("hours"); // "hours" | "pct"
  const [utilDetail, setUtilDetail] = useState(null); // {member, date, dayInfo, x, y}
  const [depArrowTaskIds, setDepArrowTaskIds] = useState(new Set()); // task IDs with arrows visible
  const [depArrows, setDepArrows] = useState([]); // [{x1,y1,x2,y2,type}]
  const [showTodayLine, setShowTodayLine] = useState(false);
  const [showRunDialog, setShowRunDialog] = useState(false);
  const [runDialogTaskIds, setRunDialogTaskIds] = useState(new Set());
  const [runDialogStartDate, setRunDialogStartDate] = useState(today);
  const [runDialogDistMode, setRunDialogDistMode] = useState("engine");
  const [runDialogChunkHours, setRunDialogChunkHours] = useState(4);
  const [runDialogRespectDates, setRunDialogRespectDates] = useState(false);
  const [runDialogDebug, setRunDialogDebug] = useState(false);
  const ganttContainerRef = useRef(null);
  const headerScrollRef = useRef(null);
  const ganttScrollRef = useRef(null);
  const utilScrollRef = useRef(null);
  const [highlightedTaskId, setHighlightedTaskId] = useState(null);

  const projectMemberIds = new Set((projectMembers || []).map((m) => m.id));
  const [selectedMemberIds, setSelectedMemberIds] = useState(new Set(projectMemberIds));

  // Sync selectedMemberIds when projectMembers changes (e.g. after save)
  const projectMemberKey = (projectMembers || []).map((m) => m.id).sort().join(",");
  useEffect(() => {
    setSelectedMemberIds(new Set((projectMembers || []).map((m) => m.id)));
  }, [projectMemberKey]);

  function toggleMember(id) {
    setSelectedMemberIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function saveTeamMembers() {
    const toAdd = [...selectedMemberIds].filter((id) => !projectMemberIds.has(id));
    const toRemove = [...projectMemberIds].filter((id) => !selectedMemberIds.has(id));

    try {
      if (toAdd.length > 0) {
        await requestJson(`/api/float/projects/${projectId}/members`, {
          method: "POST",
          body: { member_ids: toAdd },
        });
      }
      for (const mid of toRemove) {
        try {
          await requestJson(`/api/float/projects/${projectId}/members/${mid}`, { method: "DELETE" });
        } catch (err) {
          // 409 means member has allocated tasks — show reassignment UI
          if (err.status === 409 || (err.message && err.message.includes("Reassign"))) {
            const resp = JSON.parse(err.body || "{}");
            if (resp.affected_tasks) {
              setRemovalInfo({
                memberId: mid,
                memberName: (allMembers || []).find((m) => m.id === mid)?.display_name || "Member",
                affectedTasks: resp.affected_tasks,
                reassignMap: {},
              });
              return; // Stop — user needs to reassign first
            }
          }
          throw err;
        }
      }
    } catch (err) {
      alert("Failed to update team: " + (err.message || err));
      return;
    }
    setShowTeamPopover(false);
    setRemovalInfo(null);
    if (onTeamChange) onTeamChange();
  }

  async function executeRemovalReassign() {
    if (!removalInfo) return;
    const { memberId, affectedTasks, reassignMap } = removalInfo;
    const memberExtId = (allMembers || []).find((m) => m.id === memberId)?.external_id;
    if (!memberExtId) return;

    try {
      for (const task of affectedTasks) {
        const toExtId = reassignMap[task.id];
        if (!toExtId) continue;
        await requestJson("/api/schedule/reassign-chunk", {
          method: "POST",
          body: {
            task_external_id: task.external_id,
            from_date: "1900-01-01", // earliest possible — move all
            from_member_external_id: memberExtId,
            to_member_external_id: toExtId,
            to_date: "1900-01-01",
            mode: "remaining",
          },
        });
      }
      // Now remove the member
      await requestJson(`/api/float/projects/${projectId}/members/${memberId}`, {
        method: "DELETE",
        body: { force: true },
      });
      setRemovalInfo(null);
      setShowTeamPopover(false);
      if (onTeamChange) onTeamChange();
      loadAllocs();
    } catch (err) {
      alert("Reassignment failed: " + (err.message || err));
    }
  }

  const [memberUtil, setMemberUtil] = useState([]);

  function loadAllocs() {
    requestJson("/api/schedule/calendar", {
      query: { start: startDate, end: endDate, projectId: String(projectId) },
    })
      .then((d) => {
        setAllocs(d.day_allocations || []);
        setMemberUtil(d.member_utilization || []);
      })

      .catch(() => {});
  }

  useEffect(() => { loadAllocs(); }, [startDate, endDate, projectId]);

  function toggleDepArrows(taskId) {
    setDepArrowTaskIds((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId); else next.add(taskId);
      return next;
    });
  }

  function recomputeDepArrows() {
    if (depArrowTaskIds.size === 0 || !ganttContainerRef.current) {
      setDepArrows([]);
      return;
    }
    const container = ganttContainerRef.current;
    const containerRect = container.getBoundingClientRect();
    const arrows = [];

    for (const taskId of depArrowTaskIds) {
      const relatedDeps = (dependencies || []).filter(
        (d) => d.predecessor_id === taskId || d.successor_id === taskId
      );
      for (const dep of relatedDeps) {
        const predAllocs = allocs.filter((a) => a.task_id === dep.predecessor_id).sort((a, b) => a.date.localeCompare(b.date));
        const succAllocs = allocs.filter((a) => a.task_id === dep.successor_id).sort((a, b) => a.date.localeCompare(b.date));
        if (!predAllocs.length || !succAllocs.length) continue;

        const depType = dep.dependency_type || "FS";
        let sourceEl, targetEl;
        if (depType === "FS" || depType === "FF") {
          sourceEl = container.querySelector(`[data-alloc-key="${dep.predecessor_id}__${predAllocs[predAllocs.length - 1].date}"]`);
        } else {
          sourceEl = container.querySelector(`[data-alloc-key="${dep.predecessor_id}__${predAllocs[0].date}"]`);
        }
        if (depType === "FF") {
          targetEl = container.querySelector(`[data-alloc-key="${dep.successor_id}__${succAllocs[succAllocs.length - 1].date}"]`);
        } else {
          targetEl = container.querySelector(`[data-alloc-key="${dep.successor_id}__${succAllocs[0].date}"]`);
        }
        if (!sourceEl || !targetEl) continue;
        const srcRect = sourceEl.getBoundingClientRect();
        const tgtRect = targetEl.getBoundingClientRect();
        arrows.push({
          x1: srcRect.right - containerRect.left,
          y1: srcRect.top + srcRect.height / 2 - containerRect.top,
          x2: tgtRect.left - containerRect.left,
          y2: tgtRect.top + tgtRect.height / 2 - containerRect.top,
          type: depType,
        });
      }
    }
    setDepArrows(arrows);
  }

  // Recompute on toggle, allocs change, or scroll
  useEffect(() => {
    const timer = setTimeout(recomputeDepArrows, 100);
    return () => clearTimeout(timer);
  }, [depArrowTaskIds, allocs, dependencies]);

  // Recompute on horizontal scroll
  useEffect(() => {
    const gantt = ganttScrollRef.current;
    if (!gantt || depArrowTaskIds.size === 0) return;
    const handler = () => recomputeDepArrows();
    gantt.addEventListener("scroll", handler);
    window.addEventListener("scroll", handler);
    return () => {
      gantt.removeEventListener("scroll", handler);
      window.removeEventListener("scroll", handler);
    };
  }, [depArrowTaskIds, allocs, dependencies]);

  function openRunDialog() {
    // Pre-select all leaf tasks (non-parent tasks)
    const parentIds = new Set(propTasks.filter((t) => t.parent_id).map((t) => t.parent_id));
    const leafIds = new Set(propTasks.filter((t) => !parentIds.has(t.id) && t.status !== "completed").map((t) => t.id));
    setRunDialogTaskIds(leafIds);
    setRunDialogStartDate(today);
    setRunDialogDistMode("engine");
    setRunDialogChunkHours(4);
    setRunDialogRespectDates(false);
    setShowRunDialog(true);
  }

  // ── Wave computation for engine mode ────────────────────────────────────
  function computeWaves(selectedIds) {
    if (!selectedIds || selectedIds.size === 0) return [];
    const selected = new Set(selectedIds);
    // Build predecessor map: taskId -> [predecessor task ids that are in selection]
    const predMap = {};
    for (const tid of selected) {
      predMap[tid] = [];
    }
    for (const d of (dependencies || [])) {
      if (selected.has(d.successor_id) && selected.has(d.predecessor_id)) {
        predMap[d.successor_id] = predMap[d.successor_id] || [];
        predMap[d.successor_id].push(d.predecessor_id);
      }
    }

    const waves = [];
    const scheduled = new Set();
    const remaining = new Set(selected);
    let safety = remaining.size + 1;

    while (remaining.size > 0 && safety-- > 0) {
      const wave = [];
      for (const tid of remaining) {
        const preds = predMap[tid] || [];
        // All predecessors in selection must be in earlier waves
        if (preds.every((p) => scheduled.has(p))) {
          wave.push(tid);
        }
      }
      if (wave.length === 0) {
        // Circular dependency or all remaining have unresolved deps — force them into a wave
        wave.push(...remaining);
      }
      waves.push(wave);
      for (const tid of wave) {
        scheduled.add(tid);
        remaining.delete(tid);
      }
    }
    return waves;
  }

  // ── Ownership conflict state ──────────────────────────────────────────
  const [ownershipConflicts, setOwnershipConflicts] = useState(null);
  const [conflictResolutions, setConflictResolutions] = useState({});
  const [pendingScheduleParams, setPendingScheduleParams] = useState(null);

  function resolveConflict(taskId, option) {
    setConflictResolutions((prev) => ({ ...prev, [taskId]: option }));
  }

  async function executeScheduleWithResolutions() {
    const params = pendingScheduleParams;
    if (!params) return;
    setOwnershipConflicts(null);
    setPendingScheduleParams(null);
    setRunning(true);
    try {
      await _doSchedule(params.waves, params.distMode, params.startDate,
                        params.chunkHours, params.respectDates, conflictResolutions);
      loadAllocs();
      if (onTeamChange) onTeamChange();
    } catch (e) {
      setRunResult({ error: e.message });
    } finally {
      setRunning(false);
      setConflictResolutions({});
    }
  }

  function cancelConflictResolution() {
    setOwnershipConflicts(null);
    setPendingScheduleParams(null);
    setConflictResolutions({});
  }

  async function _doSchedule(waves, distMode, startDate, chunkHours, respectDates, resolutions) {
    if (distMode === "even") {
      const body = {
        project_id: parseInt(projectId, 10),
        distribution_mode: "even",
        chunk_hours: chunkHours,
        member_ids: [...selectedMemberIds],
        ownership_resolutions: resolutions || {},
      };
      if (runDialogTaskIds.size > 0) body.task_ids = [...runDialogTaskIds];
      if (startDate) body.schedule_start_date = startDate;
      if (respectDates) body.respect_dates = true;
      if (runDialogDebug) body.debug = true;
      const res = await requestJson("/api/schedule/run", { method: "POST", body });
      setRunResult(res);
    } else {
      let combinedResult = { assignments_written: 0, ghost_tasks: [], engine_log: [], overscheduled_tasks: [] };
      let lastStatus = "scheduled";
      for (let i = 0; i < waves.length; i++) {
        const waveTaskIds = waves[i];
        const body = {
          project_id: parseInt(projectId, 10),
          task_ids: waveTaskIds,
          member_ids: [...selectedMemberIds],
          ownership_resolutions: resolutions || {},
        };
        if (i === 0 && startDate) body.schedule_start_date = startDate;
        if (runDialogDebug) body.debug = true;
        const res = await requestJson("/api/schedule/run", { method: "POST", body });
        combinedResult.assignments_written += (res.assignments_written || 0);
        combinedResult.ghost_tasks.push(...(res.ghost_tasks || []));
        combinedResult.engine_log.push(`── Wave ${i + 1} (${waveTaskIds.length} tasks) ──`);
        combinedResult.engine_log.push(...(res.engine_log || []));
        combinedResult.overscheduled_tasks.push(...(res.overscheduled_tasks || []));
        lastStatus = res.status || lastStatus;
      }
      combinedResult.status = lastStatus;
      setRunResult(combinedResult);
    }
  }

  async function runSchedule() {
    if (selectedMemberIds.size === 0) return;
    setShowRunDialog(false);
    setRunning(true);
    try {
      const waves = runDialogDistMode === "engine" ? computeWaves(runDialogTaskIds) : [];

      // ── Preflight: detect ownership conflicts ──────────────────────
      const preflightBody = {
        project_id: parseInt(projectId, 10),
        member_ids: [...selectedMemberIds],
        preflight: true,
      };
      if (runDialogTaskIds.size > 0) preflightBody.task_ids = [...runDialogTaskIds];
      const preflight = await requestJson("/api/schedule/run", { method: "POST", body: preflightBody });
      const conflicts = preflight.ownership_conflicts || [];

      if (conflicts.length > 0) {
        // Show conflict resolution popup — don't schedule yet
        setOwnershipConflicts(conflicts);
        // Pre-select recommendations
        const defaultResolutions = {};
        for (const c of conflicts) {
          const rec = c.options.find((o) =>
            c.recommendation === "keep" ? o.action === "keep" :
            o.action === "reassign" && o.target_member_id === c.recommended_member_id
          );
          if (rec) defaultResolutions[c.task_id] = rec;
        }
        setConflictResolutions(defaultResolutions);
        setPendingScheduleParams({
          waves, distMode: runDialogDistMode, startDate: runDialogStartDate,
          chunkHours: runDialogChunkHours, respectDates: runDialogRespectDates,
        });
        setRunning(false);
        return;
      }

      // No conflicts — schedule directly
      await _doSchedule(waves, runDialogDistMode, runDialogStartDate,
                        runDialogChunkHours, runDialogRespectDates, {});
      loadAllocs();
      if (onTeamChange) onTeamChange();
    } catch (e) {
      // Check for parent_task_dependencies blocking error
      if (e.payload?.code === "parent_task_dependencies") {
        setRunResult({
          error: e.payload.message,
          parent_task_dependencies: e.payload.parent_task_dependencies,
        });
      } else {
        setRunResult({ error: e.message });
      }
    } finally {
      setRunning(false);
    }
  }

  async function rescheduleAll() {
    if (!confirm("This will clear ALL allocations (including manual reassignments) and recalculate from scratch. Only pinned assignments will be preserved. Continue?")) return;
    setRunning(true);
    try {
      await requestJson("/api/schedule/clear", {
        method: "POST",
        body: { project_id: parseInt(projectId, 10) },
      });
      const rescheduleBody = { project_id: parseInt(projectId, 10) };
      if (selectedMemberIds.size > 0) rescheduleBody.member_ids = [...selectedMemberIds];
      const res = await requestJson("/api/schedule/run", {
        method: "POST",
        body: rescheduleBody,
      });
      setRunResult(res);
      loadAllocs();
      if (onTeamChange) onTeamChange(); // refresh task dates + assignees
    } catch (e) {
      if (e.payload?.code === "parent_task_dependencies") {
        setRunResult({
          error: e.payload.message,
          parent_task_dependencies: e.payload.parent_task_dependencies,
        });
      } else {
        setRunResult({ error: e.message });
      }
    } finally {
      setRunning(false);
    }
  }

  const [resetPinnedInfo, setResetPinnedInfo] = useState(null);

  async function resetToImport() {
    setRunning(true);
    try {
      // Step 1: Preflight — check for pinned allocations
      const preflight = await requestJson("/api/schedule/reset", {
        method: "POST",
        body: { project_id: parseInt(projectId, 10), preflight: true },
      });

      if (preflight.has_pinned) {
        // Show confirmation dialog with pinned details
        setResetPinnedInfo(preflight);
        setRunning(false);
        return;
      }

      // No pinned — confirm and proceed
      if (!confirm("This will reset all allocations, assignments, and task dates to their original imported values.\n\nThis cannot be undone. Continue?")) {
        setRunning(false);
        return;
      }

      await _executeReset(false);
    } catch (e) {
      setRunResult({ error: e.message });
      setRunning(false);
    }
  }

  async function _executeReset(includePinned) {
    setResetPinnedInfo(null);
    setRunning(true);
    try {
      const res = await requestJson("/api/schedule/reset", {
        method: "POST",
        body: { project_id: parseInt(projectId, 10), include_pinned: includePinned },
      });
      setRunResult({
        reset: true,
        allocations_deleted: res.allocations_deleted,
        assignments_deleted: res.assignments_deleted,
        assignments_restored: res.assignments_restored,
        pinned_kept: res.pinned_kept,
      });
      loadAllocs();
      if (onTeamChange) onTeamChange();
    } catch (e) {
      setRunResult({ error: e.message });
    } finally {
      setRunning(false);
    }
  }

  // ── Navigate to task (scroll + highlight) ────────────────────────────────

  function navigateToTask(taskId) {
    setDetailTask(null); // close detail panel
    setHighlightedTaskId(taskId);

    // Scroll the left task list vertically to the target task row
    setTimeout(() => {
      const container = ganttContainerRef.current;
      if (!container) return;
      const row = container.querySelector(`[data-task-row="${taskId}"]`);
      if (row) {
        row.scrollIntoView({ behavior: "smooth", block: "center" });
      }

      // Scroll the gantt horizontally to the first allocation of this task
      const firstChunkEl = container.querySelector(`[data-alloc-key^="${taskId}__"]`);
      if (firstChunkEl && ganttScrollRef.current) {
        const gantt = ganttScrollRef.current;
        const colLeft = firstChunkEl.offsetLeft;
        const colWidth = firstChunkEl.offsetWidth;
        const containerWidth = gantt.clientWidth;
        gantt.scrollLeft = colLeft - (containerWidth / 2) + (colWidth / 2);
        if (headerScrollRef.current) headerScrollRef.current.scrollLeft = gantt.scrollLeft;
      }

      // Clear highlight after a few seconds
      setTimeout(() => setHighlightedTaskId(null), 3000);
    }, 100);
  }

  // ── Dependency validation ────────────────────────────────────────────────

  function validateDrop(dragAlloc, dropDate) {
    const taskId = dragAlloc.task_id;
    // Check FS predecessors
    const preds = (dependencies || []).filter((d) => d.successor_id === taskId);
    for (const dep of preds) {
      if (dep.dependency_type === "FS") {
        const predChunks = allocs.filter((a) => a.task_id === dep.predecessor_id);
        if (predChunks.length) {
          const lastDate = predChunks.sort((a, b) => b.date.localeCompare(a.date))[0].date;
          if (dropDate <= lastDate) {
            return "Can't move before " + (taskById[dep.predecessor_id]?.name || "predecessor") + " finishes (" + lastDate + ")";
          }
        }
      }
    }
    // Check FS successors
    const succs = (dependencies || []).filter((d) => d.predecessor_id === taskId);
    for (const dep of succs) {
      if (dep.dependency_type === "FS") {
        const succChunks = allocs.filter((a) => a.task_id === dep.successor_id);
        if (succChunks.length) {
          const firstDate = succChunks.sort((a, b) => a.date.localeCompare(b.date))[0].date;
          if (dropDate >= firstDate) {
            return "Can't move after " + (taskById[dep.successor_id]?.name || "successor") + " starts (" + firstDate + ")";
          }
        }
      }
    }
    return null;
  }

  // ── Drag & Drop ──────────────────────────────────────────────────────────

  function handleDragStart(e, alloc) {
    setDragData(alloc);
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", alloc.task_name); } catch (_) {}
  }
  function handleDragOver(e) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }
  function handleDragEnter(taskId, date) { setDropTarget({ task_id: taskId, date }); }
  function handleDragLeave() { setDropTarget(null); }
  function handleDrop(e, taskId, date) {
    e.preventDefault();
    setDropTarget(null);
    if (!dragData) return;
    if (dragData.task_id === taskId && dragData.date === date) { setDragData(null); return; }
    // Validate dependencies
    const warning = validateDrop(dragData, date);
    if (warning) {
      setDepWarning(warning);
      setDragData(null);
      setTimeout(() => setDepWarning(null), 4000);
      return;
    }
    setDropPrompt({ drag: dragData, drop: { task_id: taskId, date } });
    setDropMode("single");
    setDragData(null);
  }

  async function executeReassign() {
    if (!dropPrompt) return;
    const { drag, drop } = dropPrompt;
    try {
      await requestJson("/api/schedule/reassign-chunk", {
        method: "POST",
        body: {
          task_external_id: drag.task_external_id,
          from_date: drag.date,
          from_member_external_id: drag.member_external_id,
          to_member_external_id: drag.member_external_id, // same member, different date
          to_date: drop.date,
          mode: dropMode,
        },
      });
      setDropPrompt(null);
      loadAllocs();
    } catch (err) {
      alert("Reassign failed: " + err.message);
    }
  }

  // ── Build task tree (DFS order) ──────────────────────────────────────────

  const tasks = propTasks || [];

  const taskById = {};
  tasks.forEach((t) => { taskById[t.id] = t; });

  // Derive non-working day indices from member working_days
  // JS getDay(): 0=Sun,1=Mon,2=Tue,3=Wed,4=Thu,5=Fri,6=Sat
  const dayNameToIndex = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  const workingDaySet = new Set();
  (allMembers || []).filter((m) => selectedMemberIds.has(m.id)).forEach((m) => {
    (m.working_days || ["Sun","Mon","Tue","Wed","Thu"]).forEach((d) => {
      if (dayNameToIndex[d] !== undefined) workingDaySet.add(dayNameToIndex[d]);
    });
  });
  function isNonWorkingDay(dateStr) {
    return !workingDaySet.has(new Date(dateStr).getDay());
  }

  const depsFor = {};
  (dependencies || []).forEach((d) => {
    if (!depsFor[d.successor_id]) depsFor[d.successor_id] = [];
    depsFor[d.successor_id].push(d);
  });

  const childrenOf = {};
  tasks.forEach((t) => {
    const pid = t.parent_id ?? null;
    if (!childrenOf[pid]) childrenOf[pid] = [];
    childrenOf[pid].push(t);
  });
  function flattenTree(parentId) {
    return (childrenOf[parentId] || []).flatMap((t) => [
      t,
      ...(collapsedIds.has(t.id) ? [] : flattenTree(t.id)),
    ]);
  }
  const orderedTasks = flattenTree(null);

  function toggleCollapse(taskId) {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId); else next.add(taskId);
      return next;
    });
  }

  // ── Build allocation lookup by task ──────────────────────────────────────

  const allocsByTask = {};
  const memberLookup = {};
  for (const a of allocs) {
    if (!allocsByTask[a.task_id]) allocsByTask[a.task_id] = {};
    if (!allocsByTask[a.task_id][a.date]) allocsByTask[a.task_id][a.date] = [];
    allocsByTask[a.task_id][a.date].push(a);
    memberLookup[a.member_id] = { name: a.member_name, ext_id: a.member_external_id };
  }

  // Build member color lookup
  const memberColorMap = {};
  (allMembers || []).forEach((m) => { memberColorMap[m.id] = m.avatar_color || "#4A90D9"; });

  // Generate week-based date structure (not daily — avoids DOM explosion)
  const weeks = weeksInRange(startDate, endDate);
  const DAY_OFFSETS = [0, 1, 2, 3, 4, 5, 6];
  const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  // Only show tasks that are in the date range or have allocations
  const visibleTasks = orderedTasks.filter((t) => {
    if (allocsByTask[t.id]) return true;
    if (!t.scheduled_start_date || !t.scheduled_end_date) return true;
    return t.scheduled_end_date >= startDate && t.scheduled_start_date <= endDate;
  });

  const inProject = (allMembers || []).filter((m) => projectMemberIds.has(m.id));
  // Filter utilization rows to only selected members
  const visibleMemberUtil = memberUtil.filter((mu) => selectedMemberIds.has(mu.member_id));

  // Capacity calculation per member
  const memberTotalHours = {};
  allocs.forEach((a) => { memberTotalHours[a.member_id] = (memberTotalHours[a.member_id] || 0) + a.hours; });
  // Weeks in date range for capacity denominator
  const totalWeeks = Math.max(1, Math.ceil(((new Date(endDate)) - (new Date(startDate))) / (7 * 86400000)));
  function memberUtilColor(memberId) {
    const m = (allMembers || []).find((x) => x.id === memberId);
    if (!m) return "transparent";
    const totalCap = (m.weekly_capacity_hours || 40) * totalWeeks;
    const used = memberTotalHours[memberId] || 0;
    const pct = totalCap > 0 ? used / totalCap : 0;
    if (pct > 1) return "#ef4444"; // red
    if (pct > 0.8) return "#f59e0b"; // yellow
    return "#22c55e"; // green
  }

  // Task scheduling status
  function taskAllocStatus(t) {
    const totalEffort = (t.estimated_hours || 0) + (t.buffer_hours || 0);
    const allocated = allocs.filter((a) => a.task_id === t.id).reduce((s, a) => s + a.hours, 0);
    if (totalEffort <= 0) return "none";
    if (allocated > totalEffort) return "over";
    if (allocated >= totalEffort) return "full";
    if (allocated > 0) return "partial";
    return "unscheduled";
  }

  return (
    <div className="tab-content" style={{ padding: ".75rem 0" }}>
      {/* ── Toolbar: team + dates + run ──────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: ".75rem", flexWrap: "wrap", marginBottom: ".75rem", position: "relative" }}>
        {/* Team avatars with capacity color */}
        {inProject.map((m) => {
          const used = memberTotalHours[m.id] || 0;
          const cap = (m.weekly_capacity_hours || 40) * totalWeeks;
          const pct = cap > 0 ? Math.round(used / cap * 100) : 0;
          return (
            <div
              key={m.id}
              className={`team-avatar${selectedMemberIds.has(m.id) ? " team-avatar--selected" : ""}`}
              style={{ background: m.avatar_color || "#4A90D9", width: 28, height: 28, fontSize: ".65rem", borderColor: memberUtilColor(m.id) }}
              onClick={() => toggleMember(m.id)}
            >
              {(m.display_name || "?")[0]}
              <span className="team-avatar__tooltip">{m.display_name} — {used}h / {cap}h ({pct}%)</span>
            </div>
          );
        })}
        <button
          type="button"
          className="ghost-button"
          style={{ fontSize: ".78rem", padding: "3px 8px", border: "1px dashed var(--line-strong)", borderRadius: 4 }}
          onClick={() => setShowTeamPopover((v) => !v)}
        >
          {inProject.length === 0 ? "+ Add members" : showTeamPopover ? "Done" : "+ Edit"}
        </button>

        <span style={{ borderLeft: "1px solid var(--line)", height: 20 }} />

        <label style={{ fontSize: ".82rem", display: "flex", alignItems: "center", gap: 4 }}>
          From <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} style={{ fontSize: ".82rem", padding: "2px 4px" }} />
        </label>
        <label style={{ fontSize: ".82rem", display: "flex", alignItems: "center", gap: 4 }}>
          To <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} style={{ fontSize: ".82rem", padding: "2px 4px" }} />
        </label>

        <button
          type="button"
          className="ghost-button"
          style={{ fontSize: ".78rem", padding: "4px 10px" }}
          onClick={() => {
            setShowTodayLine(true);
            // Scroll to center today's column
            setTimeout(() => {
              if (ganttScrollRef.current) {
                const todayCol = ganttScrollRef.current.querySelector(`[data-gantt-date="${today}"]`);
                if (todayCol) {
                  const container = ganttScrollRef.current;
                  const colLeft = todayCol.offsetLeft;
                  const colWidth = todayCol.offsetWidth;
                  const containerWidth = container.clientWidth;
                  container.scrollLeft = colLeft - (containerWidth / 2) + (colWidth / 2);
                }
              }
            }, 50);
          }}
        >
          Today
        </button>

        <span style={{ flex: 1 }} />

        {/* Utilization display toggle */}
        <div style={{ display: "inline-flex", border: "1px solid var(--line)", borderRadius: 4, overflow: "hidden", fontSize: ".75rem", marginRight: 8 }}>
          <button
            type="button"
            onClick={() => setUtilMode("pct")}
            style={{
              padding: "3px 10px", border: "none", cursor: "pointer",
              background: utilMode === "pct" ? "var(--accent)" : "transparent",
              color: utilMode === "pct" ? "#fff" : "var(--text)",
              fontWeight: utilMode === "pct" ? 600 : 400,
            }}
          >
            %
          </button>
          <button
            type="button"
            onClick={() => setUtilMode("hours")}
            style={{
              padding: "3px 10px", border: "none", borderLeft: "1px solid var(--line)", cursor: "pointer",
              background: utilMode === "hours" ? "var(--accent)" : "transparent",
              color: utilMode === "hours" ? "#fff" : "var(--text)",
              fontWeight: utilMode === "hours" ? 600 : 400,
            }}
          >
            Hours
          </button>
        </div>

        <button
          type="button"
          className="primary-button"
          style={{ fontSize: ".82rem", padding: "5px 14px" }}
          onClick={openRunDialog}
          disabled={running}
        >
          {running ? "Running..." : "Run Schedule"}
        </button>
        <button
          type="button"
          className="ghost-button"
          style={{ fontSize: ".78rem" }}
          onClick={rescheduleAll}
          disabled={running}
        >
          Reschedule All
        </button>
        <button
          type="button"
          className="ghost-button ghost-button--danger"
          style={{ fontSize: ".78rem" }}
          onClick={resetToImport}
          disabled={running}
          title="Remove all allocations, assignments, and team members. Restore task dates to their original imported values."
        >
          Reset to Import
        </button>

        {/* Team popover */}
        {showTeamPopover && (
          <div className="team-popover" style={{ top: "110%", left: 0 }}>
            {(allMembers || []).map((m) => (
              <label key={m.id} style={{ display: "flex", alignItems: "center", gap: ".5rem", padding: ".3rem 0", cursor: "pointer", fontSize: ".85rem" }}>
                <input type="checkbox" checked={selectedMemberIds.has(m.id)} onChange={() => toggleMember(m.id)} />
                <span style={{ width: 18, height: 18, borderRadius: "50%", background: m.avatar_color || "#4A90D9", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: ".55rem", fontWeight: 600, flexShrink: 0 }}>
                  {(m.display_name || "?")[0]}
                </span>
                {m.display_name}
                {projectMemberIds.has(m.id) && <span className="muted" style={{ fontSize: ".7rem", marginLeft: "auto" }}>in project</span>}
              </label>
            ))}
            <div style={{ borderTop: "1px solid var(--line)", marginTop: ".5rem", paddingTop: ".5rem", display: "flex", gap: ".5rem" }}>
              <button type="button" className="primary-button" style={{ fontSize: ".78rem", padding: "3px 10px" }} onClick={saveTeamMembers}>Save</button>
              <button type="button" className="ghost-button" style={{ fontSize: ".78rem" }} onClick={() => { setSelectedMemberIds(new Set(projectMemberIds)); setShowTeamPopover(false); }}>Cancel</button>
            </div>
          </div>
        )}
      </div>

      {depWarning && (
        <div className="banner banner--warn" style={{ marginBottom: ".75rem" }}>{depWarning}</div>
      )}

      {removalInfo && (
        <div className="card" style={{ marginBottom: ".75rem", border: "1px solid var(--warn-border)", background: "var(--warn-bg)" }}>
          <h4 style={{ margin: "0 0 .5rem" }}>Reassign {removalInfo.memberName}'s tasks before removing</h4>
          {removalInfo.affectedTasks.map((t) => (
            <div key={t.id} style={{ display: "flex", alignItems: "center", gap: ".5rem", marginBottom: ".4rem", fontSize: ".85rem" }}>
              <span style={{ flex: 1 }}>{t.name} ({t.hours}h)</span>
              <select
                value={removalInfo.reassignMap[t.id] || ""}
                onChange={(e) => setRemovalInfo((prev) => ({
                  ...prev,
                  reassignMap: { ...prev.reassignMap, [t.id]: e.target.value },
                }))}
                style={{ fontSize: ".82rem", padding: "2px 6px", minWidth: 160 }}
              >
                <option value="">-- Reassign to --</option>
                {(allMembers || []).filter((m) => m.id !== removalInfo.memberId).map((m) => (
                  <option key={m.id} value={m.external_id}>{m.display_name}</option>
                ))}
              </select>
            </div>
          ))}
          <div style={{ display: "flex", gap: ".5rem", marginTop: ".75rem" }}>
            <button
              type="button"
              className="primary-button"
              style={{ fontSize: ".78rem", padding: "4px 12px" }}
              onClick={executeRemovalReassign}
              disabled={removalInfo.affectedTasks.some((t) => !removalInfo.reassignMap[t.id])}
            >
              Reassign & Remove
            </button>
            <button type="button" className="ghost-button" style={{ fontSize: ".78rem" }} onClick={() => setRemovalInfo(null)}>Cancel</button>
          </div>
        </div>
      )}

      {/* ── Run Schedule Dialog ──────────────────────────────────────── */}
      {showRunDialog && (
        <div className="modal-backdrop" onClick={() => setShowRunDialog(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560, maxHeight: "80vh", overflow: "auto" }}>
            <h3 style={{ margin: "0 0 .75rem" }}>Run Schedule</h3>

            {/* Member selection (mandatory) */}
            <div style={{ marginBottom: ".75rem" }}>
              <label className="field-label" style={{ display: "block", marginBottom: 4, fontSize: ".82rem", fontWeight: 600 }}>
                Team Members <span style={{ color: "var(--warn)", fontWeight: 400 }}>*</span>
              </label>
              <div className="muted" style={{ fontSize: ".72rem", marginBottom: 6 }}>
                Select which members to use for task assignment. Tasks owned by unselected members will be flagged for your review.
              </div>
              <div style={{ maxHeight: 140, overflowY: "auto", border: "1px solid var(--line)", borderRadius: 4, padding: 4 }}>
                {(allMembers || []).filter((m) => projectMemberIds.has(m.id)).map((m) => (
                  <label key={m.id} style={{ display: "flex", alignItems: "center", gap: ".5rem", padding: "3px 6px", cursor: "pointer", fontSize: ".82rem" }}>
                    <input
                      type="checkbox"
                      checked={selectedMemberIds.has(m.id)}
                      onChange={() => toggleMember(m.id)}
                    />
                    <span style={{
                      width: 20, height: 20, borderRadius: "50%", display: "inline-flex",
                      alignItems: "center", justifyContent: "center", fontSize: ".65rem",
                      fontWeight: 600, color: "#fff", background: m.avatar_color || "#4A90D9",
                      flexShrink: 0,
                    }}>
                      {(m.display_name || "?").charAt(0).toUpperCase()}
                    </span>
                    <span style={{ flex: 1 }}>{m.display_name}</span>
                  </label>
                ))}
              </div>
              {selectedMemberIds.size === 0 && (
                <div style={{ color: "var(--warn)", fontSize: ".75rem", marginTop: 4 }}>
                  Please select at least one member
                </div>
              )}
            </div>

            {/* Start date */}
            <div style={{ marginBottom: ".75rem" }}>
              <label className="field-label" style={{ display: "block", marginBottom: 4, fontSize: ".82rem", fontWeight: 600 }}>
                Start Date
              </label>
              <input
                type="date"
                value={runDialogStartDate}
                onChange={(e) => setRunDialogStartDate(e.target.value)}
                style={{ fontSize: ".85rem", padding: "4px 8px", width: "100%" }}
              />
              <div className="muted" style={{ fontSize: ".72rem", marginTop: 2 }}>
                The scheduler will start allocating from this date
              </div>
            </div>

            {/* Distribution mode */}
            <div style={{ marginBottom: ".75rem" }}>
              <label className="field-label" style={{ display: "block", marginBottom: 4, fontSize: ".82rem", fontWeight: 600 }}>
                Distribution Mode
              </label>
              <div style={{ display: "flex", flexDirection: "column", gap: ".4rem" }}>
                <label style={{ display: "flex", alignItems: "center", gap: ".5rem", cursor: "pointer", fontSize: ".85rem" }}>
                  <input type="radio" name="distMode" value="engine" checked={runDialogDistMode === "engine"} onChange={() => setRunDialogDistMode("engine")} />
                  Capacity-based (fills available capacity per member)
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: ".5rem", cursor: "pointer", fontSize: ".85rem" }}>
                  <input type="radio" name="distMode" value="even" checked={runDialogDistMode === "even"} onChange={() => setRunDialogDistMode("even")} />
                  Even distribution (fixed hours/day per task)
                </label>
              </div>
            </div>

            {/* Chunk hours (only for even mode) */}
            {runDialogDistMode === "even" && (
              <div style={{ marginBottom: ".75rem" }}>
                <label className="field-label" style={{ display: "block", marginBottom: 4, fontSize: ".82rem", fontWeight: 600 }}>
                  Hours per day (chunk size)
                </label>
                <input
                  type="number"
                  min={0.5}
                  step={0.5}
                  value={runDialogChunkHours}
                  onChange={(e) => setRunDialogChunkHours(parseFloat(e.target.value) || 4)}
                  style={{ fontSize: ".85rem", padding: "4px 8px", width: 100 }}
                />
                <div className="muted" style={{ fontSize: ".72rem", marginTop: 2 }}>
                  Each task gets this many hours allocated per working day
                </div>
              </div>
            )}

            {/* Respect original dates (even mode only) */}
            {runDialogDistMode === "even" && (
              <div style={{ marginBottom: ".75rem" }}>
                <label style={{ display: "flex", alignItems: "flex-start", gap: ".5rem", cursor: "pointer", fontSize: ".85rem" }}>
                  <input
                    type="checkbox"
                    checked={runDialogRespectDates}
                    onChange={(e) => setRunDialogRespectDates(e.target.checked)}
                    style={{ marginTop: 3 }}
                  />
                  <div>
                    <div>Respect original task dates</div>
                    <div className="muted" style={{ fontSize: ".72rem", marginTop: 1 }}>
                      Each task is scheduled within its own imported start/end dates. May overload resources if tasks overlap.
                    </div>
                  </div>
                </label>
              </div>
            )}

            {/* Debug mode */}
            <div style={{ marginBottom: ".75rem" }}>
              <label style={{ display: "flex", alignItems: "center", gap: ".5rem", cursor: "pointer", fontSize: ".85rem" }}>
                <input type="checkbox" checked={runDialogDebug} onChange={(e) => setRunDialogDebug(e.target.checked)} />
                <div>
                  <div>Debug mode</div>
                  <div className="muted" style={{ fontSize: ".72rem", marginTop: 1 }}>
                    Include bundle and engine traces in the run log for troubleshooting
                  </div>
                </div>
              </label>
            </div>

            {/* Task selection */}
            <div style={{ marginBottom: ".75rem" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <label className="field-label" style={{ fontSize: ".82rem", fontWeight: 600, margin: 0 }}>
                  Tasks to include ({runDialogTaskIds.size} selected)
                </label>
                <div style={{ display: "flex", gap: ".4rem" }}>
                  <button
                    type="button"
                    className="ghost-button"
                    style={{ fontSize: ".7rem", padding: "2px 6px" }}
                    onClick={() => {
                      const parentIds = new Set(propTasks.filter((t) => t.parent_id).map((t) => t.parent_id));
                      setRunDialogTaskIds(new Set(propTasks.filter((t) => !parentIds.has(t.id) && t.status !== "completed").map((t) => t.id)));
                    }}
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    style={{ fontSize: ".7rem", padding: "2px 6px" }}
                    onClick={() => setRunDialogTaskIds(new Set())}
                  >
                    Clear
                  </button>
                </div>
              </div>
              <div style={{ maxHeight: 200, overflowY: "auto", border: "1px solid var(--line)", borderRadius: 4, padding: 4 }}>
                {(() => {
                  const parentIds = new Set(propTasks.filter((t) => t.parent_id).map((t) => t.parent_id));
                  const leafTasks = propTasks.filter((t) => !parentIds.has(t.id) && t.status !== "completed");
                  if (leafTasks.length === 0) return <p className="muted" style={{ fontSize: ".82rem", padding: 8 }}>No tasks available</p>;
                  return leafTasks.map((t) => (
                    <label key={t.id} style={{ display: "flex", alignItems: "center", gap: ".5rem", padding: "3px 6px", cursor: "pointer", fontSize: ".82rem" }}>
                      <input
                        type="checkbox"
                        checked={runDialogTaskIds.has(t.id)}
                        onChange={() => setRunDialogTaskIds((prev) => {
                          const next = new Set(prev);
                          if (next.has(t.id)) next.delete(t.id); else next.add(t.id);
                          return next;
                        })}
                      />
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.name}</span>
                      <span className="muted" style={{ fontSize: ".72rem", flexShrink: 0 }}>
                        {((t.estimated_hours || 0) + (t.buffer_hours || 0)) || "?"}h
                      </span>
                    </label>
                  ));
                })()}
              </div>
            </div>

            {/* Wave preview (engine mode only) */}
            {runDialogDistMode === "engine" && runDialogTaskIds.size > 0 && (() => {
              const waves = computeWaves(runDialogTaskIds);
              if (waves.length <= 1) return null;
              return (
                <div style={{ marginBottom: ".75rem", border: "1px solid var(--accent)", borderRadius: 4, padding: "8px 12px", background: "#f0f7ff" }}>
                  <div style={{ fontSize: ".82rem", fontWeight: 600, marginBottom: 6, color: "var(--accent)" }}>
                    Dependency Waves ({waves.length} waves)
                  </div>
                  <div className="muted" style={{ fontSize: ".72rem", marginBottom: 8 }}>
                    Tasks will be scheduled in waves to respect dependencies. Each wave starts after its predecessors finish.
                  </div>
                  {waves.map((waveIds, i) => (
                    <div key={i} style={{ marginBottom: i < waves.length - 1 ? 8 : 0 }}>
                      <div style={{ fontSize: ".78rem", fontWeight: 600, marginBottom: 2 }}>Wave {i + 1}</div>
                      {waveIds.map((tid) => {
                        const t = taskById[tid];
                        return t ? (
                          <div key={tid} style={{ fontSize: ".78rem", paddingLeft: 12, color: "var(--text)" }}>
                            {t.name} <span className="muted">({((t.estimated_hours || 0) + (t.buffer_hours || 0)) || "?"}h)</span>
                          </div>
                        ) : null;
                      })}
                    </div>
                  ))}
                </div>
              );
            })()}

            {/* Actions */}
            <div className="modal-actions" style={{ display: "flex", gap: ".5rem", justifyContent: "flex-end" }}>
              <button type="button" className="secondary-button" onClick={() => setShowRunDialog(false)}>Cancel</button>
              <button
                type="button"
                className="primary-button"
                onClick={runSchedule}
                disabled={runDialogTaskIds.size === 0 || selectedMemberIds.size === 0}
              >
                {(() => {
                  if (runDialogDistMode === "engine" && runDialogTaskIds.size > 0) {
                    const waves = computeWaves(runDialogTaskIds);
                    if (waves.length > 1) return `Run All ${waves.length} Waves`;
                  }
                  return "Run Schedule";
                })()}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Ownership Conflict Resolution Popup ───────────────────── */}
      {ownershipConflicts && ownershipConflicts.length > 0 && (
        <div className="modal-backdrop" onClick={cancelConflictResolution}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 620, maxHeight: "80vh", overflow: "auto" }}>
            <h3 style={{ margin: "0 0 .5rem", display: "flex", alignItems: "center", gap: ".5rem" }}>
              <span style={{ color: "var(--warn)" }}>&#9888;</span> Ownership Conflicts Found
            </h3>
            <p className="muted" style={{ fontSize: ".82rem", margin: "0 0 1rem" }}>
              Some tasks have assignment issues. Please choose how to handle each one before scheduling.
            </p>

            {ownershipConflicts.map((conflict) => {
              const selected = conflictResolutions[conflict.task_id];
              const issueLabel = conflict.issue === "owner_not_in_scope"
                ? `Current owner ${conflict.current_owner_name} is not in selected members`
                : conflict.issue === "no_owner"
                ? "No current owner \u2014 assignment needed"
                : `${conflict.current_owner_name} has limited capacity (extends beyond original end)`;

              return (
                <div key={conflict.task_id} style={{
                  border: "1px solid var(--line)", borderRadius: 6, padding: "12px 14px",
                  marginBottom: ".75rem", background: "var(--bg-surface)",
                }}>
                  <div style={{ fontWeight: 600, fontSize: ".88rem", marginBottom: 2 }}>
                    {conflict.task_name}
                    <span className="muted" style={{ fontWeight: 400, marginLeft: 8 }}>
                      {conflict.effort_hours}h
                    </span>
                  </div>
                  <div style={{ fontSize: ".78rem", color: "var(--warn)", marginBottom: 4 }}>
                    {issueLabel}
                  </div>
                  <div className="muted" style={{ fontSize: ".75rem", marginBottom: 8 }}>
                    Original dates: {conflict.original_start || "—"} to {conflict.original_end || "—"}
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: ".4rem" }}>
                    {conflict.options.map((option, idx) => {
                      const isSelected = selected && selected.action === option.action &&
                        (option.action === "keep" || selected.target_member_id === option.target_member_id);
                      const isRecommended =
                        (conflict.recommendation === "keep" && option.action === "keep") ||
                        (conflict.recommendation === "reassign" && option.action === "reassign" &&
                         option.target_member_id === conflict.recommended_member_id);

                      return (
                        <label key={idx} style={{
                          display: "flex", alignItems: "center", gap: ".5rem", padding: "6px 10px",
                          border: `1px solid ${isSelected ? "var(--accent)" : "var(--line)"}`,
                          borderRadius: 4, cursor: "pointer", fontSize: ".82rem",
                          background: isSelected ? "#f0f7ff" : "transparent",
                        }}>
                          <input
                            type="radio"
                            name={`conflict-${conflict.task_id}`}
                            checked={isSelected}
                            onChange={() => resolveConflict(conflict.task_id, option)}
                          />
                          <span style={{ flex: 1 }}>{option.label}</span>
                          {isRecommended && (
                            <span style={{
                              fontSize: ".68rem", padding: "1px 6px", borderRadius: 3,
                              background: "var(--accent)", color: "#fff", fontWeight: 600,
                            }}>
                              Recommended
                            </span>
                          )}
                        </label>
                      );
                    })}
                  </div>
                </div>
              );
            })}

            <div className="modal-actions" style={{ display: "flex", gap: ".5rem", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button type="button" className="secondary-button" onClick={cancelConflictResolution}>
                Cancel
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={executeScheduleWithResolutions}
                disabled={ownershipConflicts.some((c) => !conflictResolutions[c.task_id])}
              >
                Apply & Schedule
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Reset Pinned Confirmation Dialog ─────────────────────── */}
      {resetPinnedInfo && (
        <div className="modal-backdrop" onClick={() => setResetPinnedInfo(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560, maxHeight: "80vh", overflow: "auto" }}>
            <h3 style={{ margin: "0 0 .5rem", display: "flex", alignItems: "center", gap: ".5rem" }}>
              <span style={{ color: "var(--warn)" }}>&#9888;</span> Pinned Allocations Found
            </h3>
            <p style={{ fontSize: ".85rem", margin: "0 0 1rem", color: "var(--text)" }}>
              This project has <strong>{resetPinnedInfo.pinned_count} task{resetPinnedInfo.pinned_count !== 1 ? "s" : ""}</strong> with
              manually pinned allocations. These represent work you intentionally placed.
            </p>

            <div style={{ border: "1px solid var(--line)", borderRadius: 6, padding: "8px 12px", marginBottom: "1rem", background: "var(--bg-surface)" }}>
              {resetPinnedInfo.pinned_details.map((p) => (
                <div key={p.task_id} style={{ padding: "6px 0", borderBottom: "1px solid var(--line)", fontSize: ".82rem" }}>
                  <div style={{ fontWeight: 600 }}>{p.task_name}</div>
                  <div className="muted">
                    {p.member_name} &middot; {p.pinned_hours}h pinned across {p.pinned_days} day{p.pinned_days !== 1 ? "s" : ""}
                  </div>
                </div>
              ))}
            </div>

            <div className="modal-actions" style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
              <button
                type="button"
                className="primary-button"
                style={{ width: "100%", textAlign: "left", padding: "10px 14px" }}
                onClick={() => _executeReset(false)}
              >
                <div style={{ fontWeight: 600 }}>Preserve pinned allocations</div>
                <div style={{ fontSize: ".75rem", fontWeight: 400, opacity: 0.8, marginTop: 2 }}>
                  Reset unpinned tasks to import state. Pinned work stays as-is.
                </div>
              </button>
              <button
                type="button"
                className="secondary-button"
                style={{ width: "100%", textAlign: "left", padding: "10px 14px", borderColor: "var(--warn)" }}
                onClick={() => _executeReset(true)}
              >
                <div style={{ fontWeight: 600, color: "var(--warn)" }}>Reset everything including pinned</div>
                <div style={{ fontSize: ".75rem", fontWeight: 400, opacity: 0.8, marginTop: 2 }}>
                  All manual placements will be lost. Full reset to import state.
                </div>
              </button>
              <button
                type="button"
                className="ghost-button"
                style={{ width: "100%", padding: "8px 14px" }}
                onClick={() => setResetPinnedInfo(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {runResult && (
        <div style={{ marginBottom: ".75rem" }}>
          <div className={`banner banner--${runResult.error ? "warn" : "ok"}`}>
            {runResult.parent_task_dependencies ? (
              <div>
                <div style={{ marginBottom: 8 }}>
                  <strong>Cannot schedule: dependencies on parent/summary tasks detected</strong>
                </div>
                <div style={{ fontSize: ".8rem", marginBottom: 8 }}>
                  Parent tasks are containers for reporting only — their dates span all children and cannot
                  be used as scheduling constraints. Please move these dependencies to leaf tasks or remove
                  them before scheduling.
                </div>
                <div style={{ fontSize: ".75rem", background: "rgba(0,0,0,0.1)", padding: "6px 10px", borderRadius: 4, maxHeight: 150, overflowY: "auto" }}>
                  {runResult.parent_task_dependencies.map((dep, i) => (
                    <div key={i} style={{ marginBottom: 2 }}>
                      <span style={{ opacity: dep.is_predecessor_parent ? 0.6 : 1, fontStyle: dep.is_predecessor_parent ? "italic" : "normal" }}>
                        {dep.predecessor_name}
                      </span>
                      {" "}&rarr;{" "}
                      <span style={{ opacity: dep.is_successor_parent ? 0.6 : 1, fontStyle: dep.is_successor_parent ? "italic" : "normal" }}>
                        {dep.successor_name}
                      </span>
                      <span style={{ opacity: 0.5, marginLeft: 6 }}>({dep.dependency_type})</span>
                      {dep.is_predecessor_parent && <span style={{ marginLeft: 6, fontSize: ".7rem", color: "var(--warn)" }}>(predecessor is parent)</span>}
                      {dep.is_successor_parent && <span style={{ marginLeft: 6, fontSize: ".7rem", color: "var(--warn)" }}>(successor is parent)</span>}
                    </div>
                  ))}
                </div>
              </div>
            ) : runResult.error ? (
              <span>Error: {runResult.error}</span>
            ) : runResult.reset ? (
              <span>
                Reset to import state: {runResult.allocations_deleted} allocation(s) cleared, {runResult.assignments_restored || 0} import assignment(s) restored.
              </span>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span>
                  <strong>{runResult.assignments_written ?? 0}</strong> allocations scheduled
                  {(runResult.ghost_tasks?.length ?? 0) > 0 && <> &nbsp;·&nbsp; {runResult.ghost_tasks.length} unscheduled</>}
                  {(runResult.overscheduled_tasks?.length ?? 0) > 0 && (
                    <> &nbsp;·&nbsp; <span style={{ color: "var(--warn)" }}>{runResult.overscheduled_tasks.length} overscheduled</span></>
                  )}
                </span>
                {runResult.engine_log?.length > 0 && (<>
                  <button
                    type="button"
                    className="ghost-button"
                    style={{ fontSize: ".72rem", padding: "2px 8px" }}
                    onClick={() => setRunResult({ ...runResult, _showLog: !runResult._showLog })}
                  >
                    {runResult._showLog ? "Hide Log" : "Show Log"}
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    style={{ fontSize: ".72rem", padding: "2px 8px" }}
                    title="Copy log to clipboard"
                    onClick={() => {
                      navigator.clipboard.writeText(runResult.engine_log.join("\n"));
                      setRunResult({ ...runResult, _copied: true });
                      setTimeout(() => setRunResult((prev) => prev ? { ...prev, _copied: false } : prev), 1500);
                    }}
                  >
                    {runResult._copied ? "Copied!" : "Copy Log"}
                  </button>
                </>)}
              </div>
            )}
          </div>
          {runResult._showLog && runResult.engine_log?.length > 0 && (
            <pre style={{
              background: "#1e1e1e", color: "#d4d4d4", fontSize: ".72rem",
              padding: "8px 12px", borderRadius: 4, marginTop: 4,
              maxHeight: 200, overflowY: "auto", whiteSpace: "pre-wrap",
            }}>
              {runResult.engine_log.join("\n")}
            </pre>
          )}
        </div>
      )}

      {/* ── Gantt grid: task rows × week columns ────────────────────────── */}
      <div ref={ganttContainerRef} style={{ display: "flex", marginTop: "1rem", position: "relative" }}>
        {/* SVG arrow overlay for dependency visualization */}
        {depArrows.length > 0 && (
          <svg style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 10 }}>
            <defs>
              <marker id="dep-arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#3b82f6" />
              </marker>
            </defs>
            {depArrows.map((arrow, i) => {
              const midX = (arrow.x1 + arrow.x2) / 2;
              const path = `M${arrow.x1},${arrow.y1} C${midX},${arrow.y1} ${midX},${arrow.y2} ${arrow.x2},${arrow.y2}`;
              return (
                <g key={i}>
                  <path d={path} fill="none" stroke="#3b82f6" strokeWidth="2" markerEnd="url(#dep-arrowhead)" strokeDasharray="8,4" className="dep-arrow-path" />
                  <path d={path} fill="none" stroke="#3b82f680" strokeWidth="6" />
                </g>
              );
            })}
          </svg>
        )}
        {/* Left: task list (sticky) */}
        <div style={{ minWidth: 280, maxWidth: 360, flexShrink: 0, borderRight: "2px solid var(--line-strong)", zIndex: 2 }}>
          <div style={{ position: "sticky", top: 0, zIndex: 5, background: "var(--bg)" }}>
            <div style={{ height: 56, background: "var(--panel-alt)", borderBottom: "1px solid var(--line)", padding: "4px 8px", fontSize: ".85rem", fontWeight: 600, color: "var(--muted)", display: "flex", alignItems: "flex-end" }}>
              Task ({visibleTasks.length})
            </div>
            {visibleMemberUtil.map((mu) => (
              <div key={mu.member_id} style={{ height: 24, display: "flex", alignItems: "center", gap: 4, padding: "0 6px", borderBottom: "1px solid var(--line)", fontSize: ".7rem", background: "var(--panel-alt)" }}>
                <span style={{ width: 14, height: 14, borderRadius: "50%", background: mu.avatar_color || "#4A90D9", display: "inline-flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: ".45rem", fontWeight: 700, flexShrink: 0 }}>
                  {(mu.display_name || "?")[0]}
                </span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{mu.display_name}</span>
                <span className="muted" style={{ marginLeft: "auto", fontSize: ".6rem" }}>{mu.daily_capacity}h</span>
              </div>
            ))}
          </div>
          {visibleTasks.map((t) => {
            const depth = t.hierarchy_depth || 0;
            const hasAllocs = !!allocsByTask[t.id];
            const taskDeps = depsFor[t.id] || [];
            const isParent = !!childrenOf[t.id];
            const isCollapsed = collapsedIds.has(t.id);
            const childCount = (childrenOf[t.id] || []).length;
            return (
              <div
                key={t.id}
                data-task-row={t.id}
                onClick={() => setDetailTask(t)}
                style={{
                  height: 56,
                  display: "flex",
                  alignItems: "center",
                  padding: "0 8px",
                  paddingLeft: depth * 16 + 8,
                  borderBottom: isParent && isCollapsed ? "2px solid var(--line-strong)" : "1px solid var(--line)",
                  fontSize: ".78rem",
                  cursor: "pointer",
                  opacity: hasAllocs || isParent ? 1 : 0.4,
                  background: highlightedTaskId === t.id ? "#dbeafe" : hasAllocs ? "transparent" : "var(--panel-alt)",
                  transition: "background 0.3s ease",
                }}
                title={taskDeps.length ? `Depends on: ${taskDeps.map((d) => taskById[d.predecessor_id]?.name || d.predecessor_id).join(", ")}` : undefined}
              >
                {isParent ? (
                  <span
                    onClick={(e) => { e.stopPropagation(); toggleCollapse(t.id); }}
                    style={{ cursor: "pointer", width: 14, textAlign: "center", color: "var(--muted)", userSelect: "none", fontSize: ".72rem", flexShrink: 0 }}
                    title={isCollapsed ? "Expand" : "Collapse"}
                  >
                    {isCollapsed ? "\u25B8" : "\u25BE"}
                  </span>
                ) : (
                  <span style={{ width: 14, flexShrink: 0 }} />
                )}
                {depth > 0 && <span className="muted" style={{ marginRight: 3, fontSize: ".65rem" }}>↳</span>}
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1, fontWeight: depth === 0 ? 600 : 400 }}>
                  {t.name}
                  {isParent && isCollapsed && <span className="muted" style={{ marginLeft: 4, fontSize: ".65rem", fontWeight: 400 }}>({childCount})</span>}
                </span>
                {taskDeps.length > 0 && <span className="dep-badge" style={{ marginLeft: 3, fontSize: ".6rem" }}>{taskDeps.length}</span>}
                {taskDeps.length > 0 && (
                  <button
                    type="button"
                    title={depArrowTaskIds.has(t.id) ? "Hide dependency arrows" : "Show dependency arrows"}
                    onClick={(e) => { e.stopPropagation(); toggleDepArrows(t.id); }}
                    style={{
                      marginLeft: 4, fontSize: ".65rem", cursor: "pointer", userSelect: "none",
                      background: depArrowTaskIds.has(t.id) ? "#3b82f6" : "transparent",
                      color: depArrowTaskIds.has(t.id) ? "#fff" : "#3b82f6",
                      border: "1px solid #3b82f6",
                      borderRadius: 3, padding: "1px 4px", lineHeight: 1,
                      flexShrink: 0,
                    }}
                  >
                    &#8693;
                  </button>
                )}
                {(() => {
                  const st = taskAllocStatus(t);
                  if (st === "over") return <span title="Overscheduled" style={{ color: "#f59e0b", fontWeight: 700, fontSize: ".7rem", marginLeft: 3 }}>!</span>;
                  if (st === "full") return <span title="Fully scheduled" style={{ color: "#22c55e", fontSize: ".65rem", marginLeft: 3 }}>&#10003;</span>;
                  if (st === "partial") return <span title="Partially scheduled" style={{ color: "#3b82f6", fontSize: ".55rem", marginLeft: 3 }}>&#9679;</span>;
                  return null;
                })()}
              </div>
            );
          })}
        </div>

        {/* Right: weekly date grid */}
        {/* Column: date header (sticky) + task grid (scrollable) */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          {/* Date header — sticky, scroll-synced */}
          <div
            ref={headerScrollRef}
            style={{ overflowX: "hidden", position: "sticky", top: 0, zIndex: 4, background: "var(--bg)" }}
          >
            <div style={{ display: "flex", minWidth: "fit-content" }}>
              {weeks.map((weekDate) => (
                <div key={weekDate} style={{ display: "flex", borderRight: "1px solid var(--line-strong)", flexShrink: 0 }}>
                  {DAY_OFFSETS.map((offset) => {
                    const dayDate = addDays(weekDate, offset);
                    const isWeekend = isNonWorkingDay(dayDate);
                    const isToday = dayDate === today;
                    return (
                      <div key={offset} style={{
                        width: 96, textAlign: "center", fontSize: ".75rem",
                        color: isToday && showTodayLine ? "#1d4ed8" : "var(--muted)",
                        fontWeight: isToday && showTodayLine ? 700 : undefined,
                        background: isToday && showTodayLine ? "#dbeafe" : isWeekend ? "#f8f0f0" : "var(--panel-alt)",
                        borderBottom: "1px solid var(--line)", borderRight: "1px solid var(--line)",
                        borderLeft: isToday && showTodayLine ? "3px solid #3b82f6" : "none",
                        padding: "4px 0", lineHeight: 1.3, height: 56, display: "flex", flexDirection: "column", justifyContent: "center",
                      }}>
                        {isToday && showTodayLine && <div style={{ fontSize: ".6rem", fontWeight: 700, color: "#1d4ed8", letterSpacing: ".5px" }}>TODAY</div>}
                        <div style={{ fontWeight: 600 }}>{DAY_NAMES[offset]}</div>
                        <div>{dayDate.slice(5)}</div>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
            {/* Utilization rows inside sticky header */}
            {visibleMemberUtil.length > 0 && (
              <div style={{ display: "flex", minWidth: "fit-content" }}>
                {weeks.map((weekDate) => (
                  <div key={weekDate} style={{ display: "flex", borderRight: "1px solid var(--line-strong)", flexShrink: 0 }}>
                    {DAY_OFFSETS.map((offset) => {
                      const dayDate = addDays(weekDate, offset);
                      const isWeekend = isNonWorkingDay(dayDate);
                      const isToday = dayDate === today && showTodayLine;
                      return (
                        <div key={offset} style={{ width: 96, display: "flex", flexDirection: "column", borderRight: "1px solid var(--line)", borderLeft: isToday ? "3px solid #3b82f6" : "none" }}>
                          {visibleMemberUtil.map((mu) => {
                            const dayInfo = mu.days[dayDate];
                            const allocated = dayInfo ? dayInfo.allocated : 0;
                            const cap = mu.daily_capacity;
                            const pct = cap > 0 ? Math.round((allocated / cap) * 100) : 0;
                            const isTimeOff = dayInfo?.time_off;
                            let bg = "transparent";
                            let color = "var(--muted)";
                            let cellText = "";
                            if (isWeekend) { bg = "#fcf5f5"; }
                            else if (isToday) { bg = "#eff6ff"; }
                            else if (isTimeOff) { bg = "#fef3c7"; color = "#92400e"; cellText = isTimeOff.replace("_"," ").slice(0,5); }
                            else if (allocated > 0 && pct > 100) { bg = "#fef2f2"; color = "#dc2626"; }
                            else if (allocated > 0 && pct >= 80) { bg = "#fffbf0"; color = "#d97706"; }
                            else if (allocated > 0) { bg = "#f0fdf4"; color = "#16a34a"; }
                            else { bg = "#f0f9ff"; color = "#0284c7"; }
                            if (!isWeekend && !isTimeOff) {
                              cellText = allocated > 0
                                ? (utilMode === "pct" ? `${pct}%` : `${allocated}/${cap}`)
                                : (utilMode === "pct" ? "0%" : `0/${cap}`);
                            }
                            const isOver = allocated > 0 && pct > 100;
                            return (
                              <div
                                key={mu.member_id}
                                title={`${mu.display_name}: ${allocated}h / ${cap}h`}
                                onClick={(allocated > 0 || isTimeOff) ? (e) => {
                                  const rect = e.currentTarget.getBoundingClientRect();
                                  setUtilDetail({ member: mu.display_name, memberColor: mu.avatar_color, date: dayDate, dayInfo: dayInfo || { allocated: 0, capacity: cap, tasks: [], time_off: null }, x: rect.left, y: rect.bottom + 4 });
                                } : undefined}
                                style={{
                                  height: 24, display: "flex", alignItems: "center", justifyContent: "center",
                                  fontSize: ".65rem", fontWeight: allocated > 0 ? 600 : 400,
                                  background: bg, color: color,
                                  borderBottom: "1px solid var(--line)",
                                  cursor: (allocated > 0 || isTimeOff) ? "pointer" : "default",
                                  position: "relative",
                                }}
                              >
                                {isOver && <span style={{ position: "absolute", top: -1, right: 1, fontSize: ".5rem" }}>&#9888;</span>}
                                {cellText}
                              </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            )}
          </div>
          {/* Task allocation rows — horizontally scrollable */}
          <div
            ref={ganttScrollRef}
            style={{ flex: 1, overflowX: "auto" }}
            onScroll={() => {
              if (ganttScrollRef.current) {
                if (headerScrollRef.current) headerScrollRef.current.scrollLeft = ganttScrollRef.current.scrollLeft;
                if (utilScrollRef.current) utilScrollRef.current.scrollLeft = ganttScrollRef.current.scrollLeft;
              }
            }}
          >
          {/* Task allocation rows */}
          <div style={{ display: "flex", minWidth: "fit-content" }}>
            {weeks.map((weekDate) => (
              <div key={weekDate} style={{ borderRight: "1px solid var(--line-strong)", flexShrink: 0 }}>
                {visibleTasks.map((t) => (
                  <div key={t.id} style={{ display: "flex" }}>
                    {DAY_OFFSETS.map((offset) => {
                      const dayDate = addDays(weekDate, offset);
                      const dayAllocs = (allocsByTask[t.id] || {})[dayDate] || [];
                      const d = new Date(dayDate);
                      const isWeekend = isNonWorkingDay(dayDate);
                      const isTarget = dropTarget && dropTarget.task_id === t.id && dropTarget.date === dayDate;
                      const isToday = dayDate === today;
                      return (
                        <div
                          key={offset}
                          data-gantt-date={dayDate}
                          style={{
                            width: 96, height: 56,
                            borderBottom: "1px solid var(--line)",
                            borderRight: "1px solid var(--line)",
                            padding: "4px 4px",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            background: isTarget ? "var(--accent-light)" : isToday && showTodayLine ? "#eff6ff" : (isWeekend ? "#fcf5f5" : "transparent"),
                            borderLeft: isToday && showTodayLine ? "3px solid #3b82f6" : "none",
                            outline: isTarget ? "2px dashed var(--accent)" : "none",
                            outlineOffset: isTarget ? "-2px" : 0,
                          }}
                          onDragOver={handleDragOver}
                          onDragEnter={() => handleDragEnter(t.id, dayDate)}
                          onDragLeave={handleDragLeave}
                          onDrop={(e) => handleDrop(e, t.id, dayDate)}
                        >
                          {dayAllocs.map((a) => {
                            const isCompletedTask = t.status === "completed";
                            return (
                            <div
                              key={a.id}
                              data-alloc-key={`${a.task_id}__${a.date}`}
                              className={`day-chip${isCompletedTask ? " day-chip--completed" : ""}${!isCompletedTask && a.source === "manual" ? " day-chip--manual" : ""}${!isCompletedTask && a.pinned ? " day-chip--pinned" : ""}`}
                              style={{ flexDirection: "row", gap: 4, padding: "4px 6px", fontSize: ".85rem", width: "100%", position: "relative" }}
                              title={`${a.member_name} — ${a.hours}h${isCompletedTask ? " (completed)" : ""}${a.pinned ? " (pinned)" : ""}${a.source === "manual" ? "\nRight-click to pin/unpin" : ""}`}
                              draggable={!isCompletedTask}
                              onDragStart={(e) => handleDragStart(e, a)}
                              onClick={(e) => { e.stopPropagation(); setDetailTask(t); }}
                              onContextMenu={a.source === "manual" ? (e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                requestJson("/api/schedule/pin", {
                                  method: "POST",
                                  body: { task_id: a.task_id, member_id: a.member_id, date: a.date, pinned: !a.pinned },
                                }).then(() => loadAllocs()).catch(() => {});
                              } : undefined}
                            >
                              <span
                                style={{
                                  width: 22, height: 22, borderRadius: "50%",
                                  background: memberColorMap[a.member_id] || "#4A90D9",
                                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                                  color: "#fff", fontSize: ".6rem", fontWeight: 700, flexShrink: 0,
                                }}
                                title={a.member_name}
                              >
                                {(a.member_name || "?")[0]}
                              </span>
                              <span style={{ fontWeight: 600 }}>{a.hours}h</span>
                            </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
        </div>{/* close column wrapper */}
      </div>

      {/* ── Utilization day detail popover ──────────────────────────────── */}
      {utilDetail && (
        <div
          className="modal-backdrop"
          style={{ background: "transparent" }}
          onClick={() => setUtilDetail(null)}
        >
          <div
            className="card"
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "fixed",
              left: Math.min(utilDetail.x, window.innerWidth - 320),
              top: Math.min(utilDetail.y, window.innerHeight - 300),
              width: 300,
              zIndex: 100,
              boxShadow: "0 4px 24px rgba(0,0,0,.18)",
              padding: "12px 16px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span
                style={{
                  width: 22, height: 22, borderRadius: "50%",
                  background: utilDetail.memberColor || "#4A90D9",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  color: "#fff", fontSize: ".65rem", fontWeight: 700,
                }}
              >
                {(utilDetail.member || "?")[0]}
              </span>
              <strong style={{ fontSize: ".9rem" }}>{utilDetail.member}</strong>
              <span className="muted" style={{ marginLeft: "auto", fontSize: ".78rem" }}>{utilDetail.date}</span>
            </div>
            <div style={{ fontSize: ".78rem", color: "var(--muted)", marginBottom: 8 }}>
              {utilDetail.dayInfo.allocated}h / {utilDetail.dayInfo.capacity}h allocated
              ({utilDetail.dayInfo.capacity > 0 ? Math.round((utilDetail.dayInfo.allocated / utilDetail.dayInfo.capacity) * 100) : 0}%)
            </div>
            {(utilDetail.dayInfo.tasks || []).length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {utilDetail.dayInfo.tasks.map((t, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: ".82rem" }}>
                    <span style={{ width: 4, height: 20, borderRadius: 2, background: t.project_color || "#999", flexShrink: 0 }} />
                    <div style={{ flex: 1, overflow: "hidden" }}>
                      <div style={{ fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.task_name}</div>
                      <div className="muted" style={{ fontSize: ".72rem" }}>{t.project_name}</div>
                    </div>
                    <span style={{ fontWeight: 600, flexShrink: 0 }}>{t.hours}h</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted" style={{ fontSize: ".78rem" }}>No task details available</p>
            )}
            <div style={{ textAlign: "right", marginTop: 8 }}>
              <button type="button" className="ghost-button" style={{ fontSize: ".75rem" }} onClick={() => setUtilDetail(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Drop prompt ─────────────────────────────────────────────────── */}
      {dropPrompt && (
        <div className="modal-backdrop" onClick={() => setDropPrompt(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Move Allocation</h3>
            <p style={{ margin: ".5rem 0" }}>
              <strong>{dropPrompt.drag.task_name}</strong> ({dropPrompt.drag.hours}h)
              <br />
              from {dropPrompt.drag.date} &rarr; {dropPrompt.drop.date}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: ".5rem", margin: "1rem 0" }}>
              <label style={{ display: "flex", alignItems: "center", gap: ".5rem", cursor: "pointer" }}>
                <input type="radio" name="dropMode" value="single" checked={dropMode === "single"} onChange={() => setDropMode("single")} />
                Move just this day
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: ".5rem", cursor: "pointer" }}>
                <input type="radio" name="dropMode" value="remaining" checked={dropMode === "remaining"} onChange={() => setDropMode("remaining")} />
                Move this day + all remaining chunks
              </label>
            </div>
            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={() => setDropPrompt(null)}>Cancel</button>
              <button type="button" className="primary-button" onClick={executeReassign}>Apply</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Task detail side panel ───────────────────────────────────────── */}
      {detailTask && (
        <>
          <div className="detail-panel-backdrop" onClick={() => setDetailTask(null)} />
          <div className="detail-panel">
            <div className="detail-panel__header">
              <div>
                {detailTask.parent_id && taskById[detailTask.parent_id] && (
                  <div className="muted" style={{ fontSize: ".75rem", marginBottom: 4 }}>
                    {taskById[detailTask.parent_id].name} &rsaquo;
                  </div>
                )}
                <h3>{detailTask.name}</h3>
              </div>
              <button className="detail-panel__close" onClick={() => setDetailTask(null)}>✕</button>
            </div>

            <div className="detail-panel__section">
              <h4>Task Info</h4>
              <div style={{ fontSize: ".9rem", lineHeight: 1.8 }}>
                <div>Status: <span className={`status-badge status-badge--${detailTask.status}`}>{detailTask.status}</span></div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  Effort:
                  <input
                    type="number" min={0} step={0.5}
                    defaultValue={detailTask.estimated_hours || 0}
                    style={{ width: 56, fontSize: ".85rem", padding: "1px 4px", fontWeight: 600 }}
                    onBlur={async (e) => {
                      const v = parseFloat(e.target.value);
                      if (isNaN(v) || v === (detailTask.estimated_hours || 0)) return;
                      await requestJson(`/api/float/tasks/${detailTask.id}`, { method: "PATCH", body: { estimated_hours: v } });
                      if (onTeamChange) onTeamChange();
                    }}
                    onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); }}
                  />
                  <span>h &nbsp;+</span>
                  <input
                    type="number" min={0} step={0.5}
                    defaultValue={detailTask.buffer_hours || 0}
                    style={{ width: 56, fontSize: ".85rem", padding: "1px 4px", fontWeight: 600 }}
                    onBlur={async (e) => {
                      const v = parseFloat(e.target.value);
                      if (isNaN(v) || v === (detailTask.buffer_hours || 0)) return;
                      await requestJson(`/api/float/tasks/${detailTask.id}`, { method: "PATCH", body: { buffer_hours: v } });
                      if (onTeamChange) onTeamChange();
                    }}
                    onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); }}
                  />
                  <span>h buffer</span>
                </div>
                <div>Dates: <strong>{fmtDate(detailTask.scheduled_start_date)}</strong> &rarr; <strong>{fmtDate(detailTask.scheduled_end_date)}</strong></div>
                <div style={{ marginTop: 8 }}>
                  <button
                    type="button"
                    className="primary-button"
                    style={{ fontSize: ".78rem", padding: "4px 12px" }}
                    disabled={running}
                    onClick={() => {
                      // Check if predecessors are scheduled
                      const taskDeps = depsFor[detailTask.id] || [];
                      const unscheduledPreds = taskDeps
                        .map((d) => taskById[d.predecessor_id])
                        .filter((t) => {
                          if (!t) return false;
                          const taskAllocs = allocs.filter((a) => a.task_id === t.id);
                          return taskAllocs.length === 0;
                        });
                      if (unscheduledPreds.length > 0) {
                        alert("Cannot schedule this task. The following predecessor tasks are not scheduled yet:\n\n" + unscheduledPreds.map((t) => "• " + t.name).join("\n") + "\n\nPlease schedule them first.");
                        return;
                      }
                      // Open Run Schedule dialog with this task pre-selected
                      setRunDialogTaskIds(new Set([detailTask.id]));
                      setRunDialogStartDate(today);
                      setRunDialogDistMode("engine");
                      setRunDialogChunkHours(4);
                      setRunDialogRespectDates(false);
                      setShowRunDialog(true);
                      setDetailTask(null);
                    }}
                  >
                    Run Schedule for this task
                  </button>
                </div>
              </div>
            </div>

            {(depsFor[detailTask.id] || []).length > 0 && (
              <div className="detail-panel__section">
                <h4>Dependencies</h4>
                {(depsFor[detailTask.id] || []).map((d) => (
                  <div key={d.predecessor_id} style={{ fontSize: ".85rem", marginBottom: 4 }}>
                    <span className="dep-badge">{d.dependency_type}</span>{" "}
                    <a
                      href="#"
                      onClick={(e) => { e.preventDefault(); navigateToTask(d.predecessor_id); }}
                      style={{ color: "var(--accent)", textDecoration: "none", cursor: "pointer" }}
                      onMouseEnter={(e) => { e.target.style.textDecoration = "underline"; }}
                      onMouseLeave={(e) => { e.target.style.textDecoration = "none"; }}
                    >
                      {taskById[d.predecessor_id]?.name || `Task #${d.predecessor_id}`}
                    </a>
                  </div>
                ))}
              </div>
            )}

            <div className="detail-panel__section">
              <h4>Schedule Chunks</h4>
              {(() => {
                const chunks = allocs.filter((a) => a.task_id === detailTask.id).sort((a, b) => a.date.localeCompare(b.date));
                if (chunks.length === 0) return <p className="muted" style={{ fontSize: ".85rem" }}>No allocations yet. Run the schedule engine.</p>;
                const totalHours = chunks.reduce((s, c) => s + c.hours, 0);

                async function doChunkReassign() {
                  if (!reassignChunk || !reassignToMember) return;
                  try {
                    await requestJson("/api/schedule/reassign-chunk", {
                      method: "POST",
                      body: {
                        task_external_id: reassignChunk.task_external_id,
                        from_date: reassignChunk.date,
                        from_member_external_id: reassignChunk.member_external_id,
                        to_member_external_id: reassignToMember,
                        to_date: reassignChunk.date,
                        mode: reassignMode,
                      },
                    });
                    setReassignChunk(null);
                    setReassignToMember("");
                    loadAllocs();
                  } catch (err) {
                    alert("Reassign failed: " + err.message);
                  }
                }

                return (
                  <>
                    <p className="muted" style={{ fontSize: ".82rem", margin: "0 0 .5rem" }}>
                      {totalHours}h across {chunks.length} day{chunks.length !== 1 ? "s" : ""}
                    </p>
                    <table className="data-table" style={{ fontSize: ".82rem" }}>
                      <thead><tr><th>Date</th><th>Member</th><th>Hours</th><th></th></tr></thead>
                      <tbody>
                        {chunks.map((c) => (
                          <tr key={`${c.date}-${c.member_id}`}>
                            <td>{c.date.slice(5)}</td>
                            <td>
                              <span style={{ display: "inline-block", width: 14, height: 14, borderRadius: "50%", background: memberColorMap[c.member_id] || "#4A90D9", marginRight: 4, verticalAlign: "middle" }} />
                              {c.member_name}
                            </td>
                            <td>{c.hours}h</td>
                            <td>
                              <button
                                type="button"
                                className="ghost-button"
                                style={{ fontSize: ".7rem", padding: "1px 4px" }}
                                onClick={() => { setReassignChunk(c); setReassignToMember(""); setReassignMode("single"); }}
                              >
                                Reassign
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    {reassignChunk && (
                      <div style={{ marginTop: ".75rem", padding: ".75rem", background: "var(--panel-alt)", borderRadius: "var(--radius-sm)", border: "1px solid var(--line)" }}>
                        <p style={{ fontSize: ".82rem", margin: "0 0 .5rem" }}>
                          Reassign <strong>{reassignChunk.date}</strong> ({reassignChunk.hours}h) from {reassignChunk.member_name}:
                        </p>
                        <select
                          value={reassignToMember}
                          onChange={(e) => setReassignToMember(e.target.value)}
                          style={{ width: "100%", fontSize: ".85rem", padding: "4px 6px", marginBottom: ".5rem" }}
                        >
                          <option value="">-- Select member --</option>
                          {(allMembers || [])
                            .filter((m) => m.external_id !== reassignChunk.member_external_id)
                            .map((m) => (
                              <option key={m.id} value={m.external_id}>{m.display_name}</option>
                            ))}
                        </select>
                        <div style={{ display: "flex", flexDirection: "column", gap: ".3rem", marginBottom: ".5rem", fontSize: ".82rem" }}>
                          <label style={{ display: "flex", alignItems: "center", gap: ".4rem", cursor: "pointer" }}>
                            <input type="radio" checked={reassignMode === "single"} onChange={() => setReassignMode("single")} />
                            This day only
                          </label>
                          <label style={{ display: "flex", alignItems: "center", gap: ".4rem", cursor: "pointer" }}>
                            <input type="radio" checked={reassignMode === "remaining"} onChange={() => setReassignMode("remaining")} />
                            This day + all remaining
                          </label>
                        </div>
                        <div style={{ display: "flex", gap: ".5rem" }}>
                          <button type="button" className="primary-button" style={{ fontSize: ".78rem", padding: "3px 10px" }} onClick={doChunkReassign} disabled={!reassignToMember}>
                            Apply
                          </button>
                          <button type="button" className="ghost-button" style={{ fontSize: ".78rem" }} onClick={() => setReassignChunk(null)}>
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Team Tab ───────────────────────────────────────────────────────────────────

function TeamTab({ members }) {
  return (
    <div className="tab-content">
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Weekly Capacity</th>
            <th>Working Days</th>
            <th>Role</th>
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.id}>
              <td>
                <span className="avatar-dot" style={{ background: m.avatar_color || "#4A90D9" }} />
                {m.display_name}
              </td>
              <td>{m.weekly_capacity_hours}h</td>
              <td>{(m.working_days || []).join(", ")}</td>
              <td>{m.role}</td>
            </tr>
          ))}
          {members.length === 0 && (
            <tr><td colSpan={4} className="muted" style={{ textAlign: "center", padding: "2rem" }}>No team members assigned</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Sync Tab (Asana) ───────────────────────────────────────────────────────────

function SyncTab({ projectId, asanaProjectGid }) {
  const [delta, setDelta] = useState(null);
  const [selected, setSelected] = useState({});
  const [loading, setLoading] = useState(false);
  const [pushResult, setPushResult] = useState(null);
  const [applyResult, setApplyResult] = useState(null);

  async function pullPreview() {
    setLoading(true);
    setDelta(null);
    try {
      const res = await requestJson("/api/asana/pull-preview");
      setDelta(res.delta || []);
      const sel = {};
      (res.delta || []).forEach((item, i) => { sel[i] = true; });
      setSelected(sel);
    } catch (e) {
      setDelta([]);
      alert("Pull failed: " + e.message);
    } finally {
      setLoading(false);
    }
  }

  async function applySelected() {
    const items = delta
      .filter((_, i) => selected[i])
      .map((item) => ({ gid: item.gid, field: item.field, asana_value: item.asana_value }));
    try {
      const res = await requestJson("/api/asana/pull-apply", { method: "POST", body: { items } });
      setApplyResult(res);
      setDelta(null);
    } catch (e) {
      alert("Apply failed: " + e.message);
    }
  }

  async function pushToAsana() {
    setPushResult(null);
    try {
      const res = await requestJson(`/api/float/projects/${projectId}/push-asana`, { method: "POST", body: {} });
      setPushResult(res);
    } catch (e) {
      alert("Push failed: " + e.message);
    }
  }

  return (
    <div className="tab-content">
      {!asanaProjectGid && (
        <div className="banner banner--warn" style={{ marginBottom: "1rem" }}>
          This project is not linked to an Asana project. Use the "Link to Asana" button in the project header above.
        </div>
      )}

      <div style={{ display: "flex", gap: 12, marginBottom: "1.5rem" }}>
        <button type="button" className="secondary-button" onClick={pullPreview} disabled={loading}>
          {loading ? "Pulling…" : "Pull from Asana"}
        </button>
        <button type="button" className="primary-button" onClick={pushToAsana} disabled={!asanaProjectGid}>
          Push to Asana
        </button>
      </div>

      {applyResult && (
        <div className="banner banner--ok">Applied {applyResult.applied} changes from Asana.</div>
      )}
      {pushResult && (
        <div className={`banner banner--${pushResult.errors?.length ? "warn" : "ok"}`}>
          {pushResult.created} created, {pushResult.updated} updated, {pushResult.deps_set} dependencies set.
          {pushResult.errors?.length ? ` ${pushResult.errors.length} error(s).` : ""}
        </div>
      )}

      {delta !== null && (
        <>
          {delta.length === 0 ? (
            <div className="banner banner--ok">No differences found — Asana and local schedule are in sync.</div>
          ) : (
            <>
              <h4 style={{ margin: "0 0 .75rem" }}>{delta.length} difference{delta.length !== 1 ? "s" : ""} found</h4>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: 32 }}></th>
                    <th>Task</th>
                    <th>Field</th>
                    <th>Asana value</th>
                    <th>Local value</th>
                  </tr>
                </thead>
                <tbody>
                  {delta.map((item, i) => (
                    <tr key={i}>
                      <td>
                        <input
                          type="checkbox"
                          checked={!!selected[i]}
                          onChange={(e) => setSelected((s) => ({ ...s, [i]: e.target.checked }))}
                        />
                      </td>
                      <td>{item.name}</td>
                      <td>{item.field || item.action}</td>
                      <td>{item.asana_value ?? "—"}</td>
                      <td>{item.local_value ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button
                type="button"
                className="primary-button"
                onClick={applySelected}
                style={{ marginTop: "1rem" }}
                disabled={!Object.values(selected).some(Boolean)}
              >
                Apply Selected
              </button>
            </>
          )}
        </>
      )}
    </div>
  );
}

// ── Asana Link Section ────────────────────────────────────────────────────────

function AsanaLinkSection({ projectId, asanaProjectGid, onUpdate }) {
  const [editing, setEditing] = useState(false);
  const [asanaProjects, setAsanaProjects] = useState(null);
  const [selectedGid, setSelectedGid] = useState(asanaProjectGid || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (editing && asanaProjects === null) {
      requestJson("/api/asana/projects")
        .then((d) => setAsanaProjects(d.projects || []))
        .catch(() => setAsanaProjects([]));
    }
  }, [editing, asanaProjects]);

  async function handleLink() {
    setSaving(true);
    try {
      await requestJson(`/api/float/projects/${projectId}`, {
        method: "PATCH",
        body: { asana_project_gid: selectedGid || null },
      });
      onUpdate();
      setEditing(false);
    } catch (e) {
      alert("Failed: " + e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleUnlink() {
    setSaving(true);
    try {
      await requestJson(`/api/float/projects/${projectId}`, {
        method: "PATCH",
        body: { asana_project_gid: null },
      });
      onUpdate();
    } catch (e) {
      alert("Failed: " + e.message);
    } finally {
      setSaving(false);
    }
  }

  // ── Linked state ──────────────────────────────────────────────────────────
  if (asanaProjectGid && !editing) {
    return (
      <div style={{ display: "inline-flex", alignItems: "center", gap: ".5rem" }}>
        <span className="status-pill status-pill--good">
          <span style={{ fontSize: ".6rem" }}>●</span> Asana linked
        </span>
        <button
          type="button"
          className="secondary-button"
          style={{ fontSize: ".75rem", padding: "3px 10px" }}
          onClick={() => setEditing(true)}
        >
          Change
        </button>
        <button
          type="button"
          className="ghost-button"
          style={{ fontSize: ".75rem" }}
          onClick={handleUnlink}
          disabled={saving}
        >
          Unlink
        </button>
      </div>
    );
  }

  // ── Editing / picker state ────────────────────────────────────────────────
  if (editing) {
    return (
      <div style={{
        display: "inline-flex",
        gap: ".5rem",
        alignItems: "center",
        flexWrap: "wrap",
        background: "var(--panel-alt)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius-sm)",
        padding: ".4rem .75rem",
      }}>
        {asanaProjects === null ? (
          <span className="muted" style={{ fontSize: ".85rem" }}>Loading Asana projects...</span>
        ) : asanaProjects.length === 0 ? (
          <>
            <span className="muted" style={{ fontSize: ".85rem" }}>
              No Asana projects found. Configure PAT in <a href="/settings">Settings</a>.
            </span>
            <button type="button" className="ghost-button" style={{ fontSize: ".8rem" }} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </>
        ) : (
          <>
            <select
              className="text-input"
              value={selectedGid}
              onChange={(e) => setSelectedGid(e.target.value)}
              style={{ fontSize: ".85rem", padding: "4px 8px", minWidth: 200, maxWidth: 300 }}
            >
              <option value="">-- Select Asana project --</option>
              {asanaProjects.map((p) => (
                <option key={p.gid} value={p.gid}>{p.name}</option>
              ))}
            </select>
            <button
              type="button"
              className="primary-button"
              style={{ fontSize: ".8rem", padding: "4px 12px" }}
              onClick={handleLink}
              disabled={saving || !selectedGid}
            >
              {saving ? "Saving..." : "Link"}
            </button>
            <button
              type="button"
              className="ghost-button"
              style={{ fontSize: ".8rem" }}
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </>
        )}
      </div>
    );
  }

  // ── Unlinked state ────────────────────────────────────────────────────────
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: ".5rem" }}>
      <span className="status-pill status-pill--muted">
        <span style={{ fontSize: ".6rem" }}>○</span> Asana not linked
      </span>
      <button
        type="button"
        className="secondary-button"
        style={{ fontSize: ".75rem", padding: "3px 10px" }}
        onClick={() => setEditing(true)}
      >
        Link to Asana
      </button>
    </div>
  );
}

// ── Main ProjectScreen ─────────────────────────────────────────────────────────

export function ProjectScreen() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [allMembers, setAllMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("tasks");
  const [collapsedIds, setCollapsedIds] = useState(new Set());
  const [showCompleted, setShowCompleted] = useState(true);

  function loadProject() {
    Promise.all([
      requestJson(`/api/float/projects/${id}`),
      requestJson("/api/float/members"),
    ])
      .then(([projData, memberData]) => {
        setData(projData);
        setAllMembers(memberData.members || []);
      })
      .catch(() => navigate("/"))
      .finally(() => setLoading(false));
  }

  useEffect(() => { loadProject(); }, [id]);

  if (loading) return <div className="screen-loading">Loading project…</div>;
  if (!data) return null;

  const { project, tasks, members, dependencies } = data;

  return (
    <div className="screen">
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: ".75rem", flexWrap: "wrap" }}>
        <button type="button" className="ghost-button" onClick={() => navigate("/")} style={{ fontSize: ".82rem" }}>
          ← Projects
        </button>
        <h2 style={{ borderLeft: `4px solid ${project.color}`, paddingLeft: 10, margin: 0, fontSize: "1.25rem" }}>
          {project.name}
        </h2>
        <span className="muted" style={{ fontSize: ".82rem" }}>
          {tasks.length} tasks &nbsp;·&nbsp; {members.length} members
          {project.start_date ? ` · ${fmtDate(project.start_date)} → ${fmtDate(project.end_date)}` : ""}
        </span>
        <span style={{ flex: 1 }} />
        <AsanaLinkSection projectId={id} asanaProjectGid={project.asana_project_gid} onUpdate={loadProject} />
      </div>

      <div className="tab-bar" style={{ display: "flex", alignItems: "center" }}>
        {[
          { key: "tasks",    label: "Tasks" },
          { key: "schedule", label: "Schedule" },
          { key: "team",     label: "Team" },
          { key: "sync",     label: "Asana Sync" },
        ].map((t) => (
          <Tab key={t.key} label={t.label} active={tab === t.key} onClick={() => setTab(t.key)} />
        ))}
        <span style={{ flex: 1 }} />
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: ".78rem", cursor: "pointer", color: "var(--muted)" }}>
          <input type="checkbox" checked={showCompleted} onChange={() => setShowCompleted(!showCompleted)} />
          Show completed
        </label>
      </div>

      {tab === "tasks"    && <TasksTab tasks={showCompleted ? tasks : tasks.filter((t) => t.status !== "completed")} dependencies={dependencies || []} onUpdate={loadProject} collapsedIds={collapsedIds} setCollapsedIds={setCollapsedIds} projectId={id} />}
      {tab === "schedule" && (
        <ScheduleTab
          projectId={id}
          projectMembers={members}
          allMembers={allMembers}
          onTeamChange={loadProject}
          tasks={showCompleted ? tasks : tasks.filter((t) => t.status !== "completed")}
          dependencies={dependencies || []}
          collapsedIds={collapsedIds}
          setCollapsedIds={setCollapsedIds}
        />
      )}
      {tab === "team"     && <TeamTab members={members} />}
      {tab === "sync"     && <SyncTab projectId={id} asanaProjectGid={project.asana_project_gid} />}
    </div>
  );
}
