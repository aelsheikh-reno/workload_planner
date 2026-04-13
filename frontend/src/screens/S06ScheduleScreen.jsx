import { useState, useCallback } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  closestCenter,
} from "@dnd-kit/core";
import { useDraggable, useDroppable } from "@dnd-kit/core";

import { requestJson } from "../api";
import { ErrorCard, LoadingSkeleton, ScreenHeader, Toast } from "../components/ScreenPrimitives";
import { useRouteData } from "../useRouteData";

// ── Helpers ────────────────────────────────────────────────────────────────────

function addDays(dateStr, days) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function formatDateDisplay(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

function toneClass(tone) {
  if (tone === "red") return "cell--overloaded";
  if (tone === "amber") return "cell--heavy";
  return "";
}

// ── Assignment chip (draggable) ────────────────────────────────────────────────

function AssignmentChip({ assignment, onClick }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: String(assignment.id),
    data: { assignment },
  });

  return (
    <div
      ref={setNodeRef}
      className={`assignment-chip${isDragging ? " assignment-chip--dragging" : ""}`}
      style={{ borderLeftColor: assignment.project_color }}
      onClick={(e) => { e.stopPropagation(); onClick?.(assignment); }}
      {...listeners}
      {...attributes}
    >
      <span className="assignment-chip__name">{assignment.task_name}</span>
      <span className="assignment-chip__hours">{assignment.hours_per_day}h</span>
    </div>
  );
}

// ── Drop cell ──────────────────────────────────────────────────────────────────

function CalendarCell({ date, memberId, children, tone }) {
  const { setNodeRef, isOver } = useDroppable({
    id: `${memberId}__${date}`,
    data: { date, memberId },
  });

  return (
    <td
      ref={setNodeRef}
      className={`calendar-cell ${toneClass(tone)}${isOver ? " calendar-cell--drop-target" : ""}`}
    >
      {children}
    </td>
  );
}

// ── Assignment detail panel ────────────────────────────────────────────────────

function AssignmentPanel({ assignment, members, tasks, onClose, onSave, onDelete }) {
  const [hours, setHours] = useState(assignment.allocated_hours);
  const [startDate, setStartDate] = useState(assignment.start_date);
  const [endDate, setEndDate] = useState(assignment.end_date);
  const [memberId, setMemberId] = useState(assignment.member_id);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await onSave(assignment.id, {
        allocated_hours: Number(hours),
        start_date: startDate,
        end_date: endDate,
        member_id: Number(memberId),
      });
      onClose();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Remove this assignment?")) return;
    setDeleting(true);
    try {
      await onDelete(assignment.id);
      onClose();
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="slide-panel">
      <div className="slide-panel__header">
        <div>
          <strong>{assignment.task_name}</strong>
          <p className="supporting-text">{assignment.project_name}</p>
        </div>
        <button className="ghost-button" onClick={onClose} type="button">✕</button>
      </div>
      <div className="slide-panel__body">
        <div className="field-group">
          <label className="field-label">Assigned to</label>
          <select className="field-input" value={memberId}
            onChange={(e) => setMemberId(e.target.value)}>
            {members.map((m) => <option key={m.id} value={m.id}>{m.display_name}</option>)}
          </select>
        </div>
        <div className="field-group">
          <label className="field-label">Start date</label>
          <input className="field-input" type="date" value={startDate}
            onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div className="field-group">
          <label className="field-label">End date</label>
          <input className="field-input" type="date" value={endDate}
            onChange={(e) => setEndDate(e.target.value)} />
        </div>
        <div className="field-group">
          <label className="field-label">Total allocated hours</label>
          <input className="field-input" type="number" min={0.5} step={0.5} value={hours}
            onChange={(e) => setHours(e.target.value)} />
        </div>
      </div>
      <div className="slide-panel__footer">
        <button className="primary-button" onClick={handleSave} disabled={saving} type="button">
          {saving ? "Saving…" : "Save changes"}
        </button>
        <button className="ghost-button ghost-button--danger" onClick={handleDelete} disabled={deleting} type="button">
          {deleting ? "Removing…" : "Remove"}
        </button>
      </div>
    </div>
  );
}

// ── New assignment form ────────────────────────────────────────────────────────

function NewAssignmentForm({ members, tasks, onSave, onClose }) {
  const [form, setForm] = useState({
    task_id: tasks[0]?.id || "",
    member_id: members[0]?.id || "",
    start_date: "",
    end_date: "",
    allocated_hours: 8,
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({ ...form, task_id: Number(form.task_id), member_id: Number(form.member_id), allocated_hours: Number(form.allocated_hours) });
      onClose();
    } catch (err) {
      alert(err.message || "Failed to create assignment.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="slide-panel">
      <div className="slide-panel__header">
        <strong>New Assignment</strong>
        <button className="ghost-button" onClick={onClose} type="button">✕</button>
      </div>
      <form className="slide-panel__body" onSubmit={handleSubmit}>
        <div className="field-group">
          <label className="field-label">Task *</label>
          <select className="field-input" required value={form.task_id}
            onChange={(e) => setForm((p) => ({ ...p, task_id: e.target.value }))}>
            <option value="">Select a task…</option>
            {tasks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>
        <div className="field-group">
          <label className="field-label">Team member *</label>
          <select className="field-input" required value={form.member_id}
            onChange={(e) => setForm((p) => ({ ...p, member_id: e.target.value }))}>
            {members.map((m) => <option key={m.id} value={m.id}>{m.display_name}</option>)}
          </select>
        </div>
        <div className="field-group">
          <label className="field-label">Start date *</label>
          <input className="field-input" type="date" required value={form.start_date}
            onChange={(e) => setForm((p) => ({ ...p, start_date: e.target.value }))} />
        </div>
        <div className="field-group">
          <label className="field-label">End date *</label>
          <input className="field-input" type="date" required value={form.end_date}
            onChange={(e) => setForm((p) => ({ ...p, end_date: e.target.value }))} />
        </div>
        <div className="field-group">
          <label className="field-label">Total allocated hours</label>
          <input className="field-input" type="number" min={1} value={form.allocated_hours}
            onChange={(e) => setForm((p) => ({ ...p, allocated_hours: e.target.value }))} />
        </div>
        <div className="slide-panel__footer">
          <button className="primary-button" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Create Assignment"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ── Main screen ────────────────────────────────────────────────────────────────

export function S06ScheduleScreen({ shellState }) {
  const [view, setView] = useState("week");
  const [anchorDate, setAnchorDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [selectedAssignment, setSelectedAssignment] = useState(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [draggingChip, setDraggingChip] = useState(null);
  const [toast, setToast] = useState(null);
  const [engineRunning, setEngineRunning] = useState(false);
  const [previewResult, setPreviewResult] = useState(null); // dry_run result
  const [engineResult, setEngineResult] = useState(null);  // last apply result

  const token = localStorage.getItem("float_token");

  async function handleRunSchedule(dryRun) {
    setEngineRunning(true);
    setPreviewResult(null);
    try {
      const result = await requestJson("/api/schedule/run", {
        method: "POST",
        body: { dry_run: dryRun },
        token,
      });
      if (dryRun) {
        setPreviewResult(result);
        setToast({ message: "Preview ready — review proposed changes below.", tone: "good" });
      } else {
        setEngineResult(result);
        schedule.reload();
        setToast({
          message: `Schedule applied — ${result.assignments_written} assignment(s) written.${result.ghost_tasks?.length ? ` ${result.ghost_tasks.length} task(s) could not be fully placed.` : ""}`,
          tone: result.ghost_tasks?.length ? "amber" : "good",
        });
      }
    } catch (err) {
      if (err.payload?.code === "parent_task_dependencies") {
        const deps = err.payload.parent_task_dependencies || [];
        const depNames = deps.map(d => `${d.predecessor_name} → ${d.successor_name}`).join(", ");
        setToast({
          message: `Cannot schedule: dependencies on parent/summary tasks detected. ${depNames}. Please move these to leaf tasks or remove them.`,
          tone: "bad",
        });
      } else {
        setToast({ message: err.message || "Engine run failed.", tone: "bad" });
      }
    } finally {
      setEngineRunning(false);
    }
  }

  function handleApplyWithConfirm() {
    if (previewResult?.proposed_reassignments?.length > 0) {
      if (!confirm(`${previewResult.proposed_reassignments.length} task(s) have proposed reassignments. Apply schedule anyway?`)) return;
    }
    handleRunSchedule(false);
    setPreviewResult(null);
  }

  const schedule = useRouteData("/api/float/schedule", {
    query: { view, date: anchorDate },
    enabled: true,
  });
  const members = useRouteData("/api/float/members", { enabled: true });
  const tasks = useRouteData("/api/float/tasks", { enabled: true });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  function navigatePrev() {
    setAnchorDate((d) => addDays(d, view === "week" ? -7 : -30));
  }
  function navigateNext() {
    setAnchorDate((d) => addDays(d, view === "week" ? 7 : 30));
  }
  function navigateToday() {
    setAnchorDate(new Date().toISOString().slice(0, 10));
  }

  async function handleDragEnd(event) {
    const { active, over } = event;
    setDraggingChip(null);
    if (!over) return;

    const [newMemberId, newDate] = over.id.split("__");
    const assignment = active.data.current?.assignment;
    if (!assignment) return;
    if (String(assignment.member_id) === newMemberId && assignment.start_date === newDate) return;

    // Calculate new end date based on same duration
    const duration =
      (new Date(assignment.end_date) - new Date(assignment.start_date)) / 86400000;
    const newEndDate = addDays(newDate, duration);

    try {
      await requestJson(`/api/float/schedule/assignments/${assignment.id}/move`, {
        method: "POST",
        body: {
          new_start_date: newDate,
          new_end_date: newEndDate,
          new_member_id: Number(newMemberId),
        },
        token,
      });
      schedule.reload();
      setToast({ message: "Assignment moved.", tone: "good" });
    } catch (err) {
      setToast({ message: err.message || "Failed to move assignment.", tone: "bad" });
    }
  }

  async function handleSaveAssignment(id, data) {
    await requestJson(`/api/float/schedule/assignments/${id}`, {
      method: "PATCH",
      body: data,
      token,
    });
    schedule.reload();
    setToast({ message: "Assignment updated.", tone: "good" });
  }

  async function handleDeleteAssignment(id) {
    await requestJson(`/api/float/schedule/assignments/${id}`, { method: "DELETE", token });
    schedule.reload();
    setToast({ message: "Assignment removed.", tone: "good" });
  }

  async function handleCreateAssignment(data) {
    await requestJson("/api/float/schedule/assignments", {
      method: "POST",
      body: data,
      token,
    });
    schedule.reload();
    setToast({ message: "Assignment created.", tone: "good" });
  }

  const allMembers = members.data?.members || [];
  const allTasks = tasks.data?.tasks || [];
  const columns = schedule.data?.columns || [];
  const rows = schedule.data?.rows || [];
  const viewConfig = schedule.data?.view_config || {};
  const ghostTasks = engineResult?.ghost_tasks || previewResult?.ghost_tasks || [];
  const reassignments = previewResult?.proposed_reassignments || engineResult?.proposed_reassignments || [];

  return (
    <div className="screen-stack">
      {toast ? <Toast message={toast.message} tone={toast.tone} onDismiss={() => setToast(null)} /> : null}

      <ScreenHeader
        eyebrow="Schedule"
        title="Team Schedule"
        description="Visual overview of team assignments. Drag chips to reschedule."
        actions={
          <>
            <button className="secondary-button" onClick={schedule.reload} type="button" disabled={engineRunning}>Refresh</button>
            <button className="secondary-button" onClick={() => handleRunSchedule(true)} type="button" disabled={engineRunning}>
              {engineRunning ? "Running…" : "Preview Schedule"}
            </button>
            <button className="primary-button" onClick={handleApplyWithConfirm} type="button" disabled={engineRunning}>
              Apply Schedule
            </button>
            <button className="secondary-button" onClick={() => setShowNewForm(true)} type="button">
              + Assign
            </button>
          </>
        }
      />

      {/* Ghost load badge */}
      {ghostTasks.length > 0 ? (
        <div className="banner banner--warn">
          <strong>Ghost load:</strong> {ghostTasks.length} task(s) could not be fully placed within capacity.
          <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.25rem" }}>
            {ghostTasks.map((t) => (
              <li key={t.task_external_id}>{t.task_name} — {t.unscheduled_hours}h unplaced</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Proposed reassignment banner */}
      {reassignments.length > 0 ? (
        <div className="banner banner--info">
          <strong>{reassignments.length} reassignment suggestion(s)</strong> — the engine proposes moving some tasks to available team members.
        </div>
      ) : null}

      {/* Preview panel */}
      {previewResult ? (
        <div className="section-card" style={{ borderLeft: "3px solid var(--blue-500)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <div>
              <strong>Preview: Proposed Schedule Changes</strong>
              <p className="supporting-text">Status: {previewResult.status} — Review before applying.</p>
            </div>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button className="primary-button" onClick={handleApplyWithConfirm} disabled={engineRunning} type="button">
                Apply Now
              </button>
              <button className="ghost-button" onClick={() => setPreviewResult(null)} type="button">
                Dismiss
              </button>
            </div>
          </div>
          {previewResult.preview_rows?.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Member</th>
                  <th>Start</th>
                  <th>End</th>
                  <th>Hours</th>
                </tr>
              </thead>
              <tbody>
                {previewResult.preview_rows.map((row, i) => (
                  <tr key={i}>
                    <td>{allTasks.find((t) => t.id === row.task_id)?.name || `Task #${row.task_id}`}</td>
                    <td>{allMembers.find((m) => m.id === row.member_id)?.display_name || `Member #${row.member_id}`}</td>
                    <td>{row.start_date}</td>
                    <td>{row.end_date}</td>
                    <td>{row.allocated_hours}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="supporting-text">No assignments would be written.</p>
          )}
        </div>
      ) : null}

      {/* Calendar controls */}
      <div className="calendar-toolbar">
        <div className="calendar-toolbar__nav">
          <button className="secondary-button" onClick={navigatePrev} type="button">←</button>
          <button className="secondary-button" onClick={navigateToday} type="button">Today</button>
          <button className="secondary-button" onClick={navigateNext} type="button">→</button>
          <span className="calendar-toolbar__range">
            {viewConfig.start_date && `${formatDateDisplay(viewConfig.start_date)} – ${formatDateDisplay(viewConfig.end_date)}`}
          </span>
        </div>
        <div className="calendar-toolbar__view">
          <button
            className={view === "week" ? "primary-button" : "secondary-button"}
            onClick={() => setView("week")} type="button"
          >Week</button>
          <button
            className={view === "month" ? "primary-button" : "secondary-button"}
            onClick={() => setView("month")} type="button"
          >Month</button>
        </div>
      </div>

      {schedule.loading ? <LoadingSkeleton label="Loading schedule…" /> : null}
      {schedule.error ? <ErrorCard error={schedule.error} onRetry={schedule.reload} /> : null}

      {schedule.data && rows.length ? (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={(e) => setDraggingChip(e.active.data.current?.assignment)}
          onDragEnd={handleDragEnd}
        >
          <div className="calendar-scroll-wrap">
            <table className="calendar-table">
              <thead>
                <tr>
                  <th className="calendar-table__member-col">Team Member</th>
                  {columns.map((col) => (
                    <th key={col.date} className="calendar-table__day-col">{col.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.member.id}>
                    <td className="calendar-table__member-cell">
                      <div
                        className="member-avatar"
                        style={{ background: row.member.avatar_color }}
                      >
                        {row.member.display_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                      </div>
                      <span>{row.member.display_name}</span>
                    </td>
                    {row.cells.map((cell) => (
                      <CalendarCell
                        key={cell.date}
                        date={cell.date}
                        memberId={row.member.id}
                        tone={cell.tone}
                      >
                        {cell.time_off ? (
                          <div className="time-off-bar">
                            <span>{cell.time_off.leave_type.replace("_", " ")}</span>
                          </div>
                        ) : null}
                        {cell.assignments.map((a) => (
                          <AssignmentChip
                            key={a.id}
                            assignment={a}
                            onClick={setSelectedAssignment}
                          />
                        ))}
                        {cell.total_allocated_hours > 0 && !cell.time_off ? (
                          <div className={`cell-util cell-util--${cell.tone}`}>
                            {cell.utilization_pct}%
                          </div>
                        ) : null}
                      </CalendarCell>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <DragOverlay>
            {draggingChip ? (
              <div className="assignment-chip assignment-chip--overlay"
                style={{ borderLeftColor: draggingChip.project_color }}>
                <span className="assignment-chip__name">{draggingChip.task_name}</span>
                <span className="assignment-chip__hours">{draggingChip.allocated_hours}h</span>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      ) : !schedule.loading && schedule.data ? (
        <div className="state-card state-card--muted">
          <strong>No team members found</strong>
          <p>Go to People to add team members first.</p>
        </div>
      ) : null}

      {/* Side panels */}
      {selectedAssignment ? (
        <AssignmentPanel
          assignment={selectedAssignment}
          members={allMembers}
          tasks={allTasks}
          onClose={() => setSelectedAssignment(null)}
          onSave={handleSaveAssignment}
          onDelete={handleDeleteAssignment}
        />
      ) : null}

      {showNewForm ? (
        <NewAssignmentForm
          members={allMembers}
          tasks={allTasks}
          onSave={handleCreateAssignment}
          onClose={() => setShowNewForm(false)}
        />
      ) : null}
    </div>
  );
}
