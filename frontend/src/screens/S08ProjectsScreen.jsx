import { useState } from "react";

import { requestJson } from "../api";
import { ErrorCard, LoadingSkeleton, ScreenHeader, SectionCard, Toast } from "../components/ScreenPrimitives";
import { useRouteData } from "../useRouteData";
import { formatCountLabel, formatValue } from "../utils";

const PROJECT_COLORS = [
  "#2196F3", "#4CAF50", "#FF9800", "#9C27B0",
  "#F44336", "#00BCD4", "#E91E63", "#FF5722",
];

const EMPTY_PROJECT_FORM = {
  name: "",
  color: "#2196F3",
  start_date: "",
  end_date: "",
};

const EMPTY_TASK_FORM = {
  name: "",
  scheduled_start_date: "",
  scheduled_end_date: "",
  estimated_hours: "",
};

function ProjectCard({ project, tasks, onAddTask }) {
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [taskForm, setTaskForm] = useState(EMPTY_TASK_FORM);
  const [saving, setSaving] = useState(false);

  async function handleAddTask(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const token = localStorage.getItem("float_token");
      await requestJson("/api/float/tasks", {
        method: "POST",
        body: {
          ...taskForm,
          project_id: project.id,
          estimated_hours: taskForm.estimated_hours ? Number(taskForm.estimated_hours) : undefined,
        },
        token,
      });
      setShowTaskForm(false);
      setTaskForm(EMPTY_TASK_FORM);
      onAddTask?.();
    } catch (err) {
      alert(err.message || "Failed to add task.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="project-card">
      <div className="project-card__header">
        <div className="project-card__color-bar" style={{ background: project.color }} />
        <div className="project-card__info">
          <strong>{project.name}</strong>
          <div className="supporting-text">
            {project.start_date ? `${project.start_date} → ${project.end_date || "ongoing"}` : "No dates set"}
            {" · "}
            {formatCountLabel(project.task_count, "task")}
          </div>
        </div>
        <button
          className="ghost-button"
          onClick={() => setShowTaskForm((v) => !v)}
          type="button"
        >
          {showTaskForm ? "Cancel" : "+ Task"}
        </button>
      </div>

      {showTaskForm ? (
        <form className="inline-form" onSubmit={handleAddTask} style={{ padding: "0.75rem 1rem", background: "#f8f9fa" }}>
          <div className="inline-form__grid">
            <div className="field-group">
              <label className="field-label">Task name *</label>
              <input className="field-input" value={taskForm.name} required
                onChange={(e) => setTaskForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="e.g. Backend API development" />
            </div>
            <div className="field-group">
              <label className="field-label">Start date</label>
              <input className="field-input" type="date" value={taskForm.scheduled_start_date}
                onChange={(e) => setTaskForm((p) => ({ ...p, scheduled_start_date: e.target.value }))} />
            </div>
            <div className="field-group">
              <label className="field-label">End date</label>
              <input className="field-input" type="date" value={taskForm.scheduled_end_date}
                onChange={(e) => setTaskForm((p) => ({ ...p, scheduled_end_date: e.target.value }))} />
            </div>
            <div className="field-group">
              <label className="field-label">Estimated hours</label>
              <input className="field-input" type="number" min={1} value={taskForm.estimated_hours}
                onChange={(e) => setTaskForm((p) => ({ ...p, estimated_hours: e.target.value }))}
                placeholder="40" />
            </div>
          </div>
          <div className="command-row">
            <button className="primary-button" type="submit" disabled={saving}>
              {saving ? "Saving…" : "Add Task"}
            </button>
          </div>
        </form>
      ) : null}

      {tasks?.length ? (
        <ul className="task-list">
          {tasks.map((t) => (
            <li key={t.id} className="task-list__item">
              <span>{t.name}</span>
              <small className="supporting-text">
                {formatValue(t.scheduled_start_date)} → {formatValue(t.scheduled_end_date)}
                {t.estimated_hours ? ` · ${t.estimated_hours}h` : ""}
              </small>
            </li>
          ))}
        </ul>
      ) : (
        <p className="supporting-text" style={{ padding: "0.5rem 1rem" }}>No tasks yet.</p>
      )}
    </div>
  );
}

export function S08ProjectsScreen({ shellState }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_PROJECT_FORM);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const projects = useRouteData("/api/float/projects", { enabled: true });
  const tasks = useRouteData("/api/float/tasks", { enabled: true });

  function handleFieldChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleAddProject(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const token = localStorage.getItem("float_token");
      await requestJson("/api/float/projects", {
        method: "POST",
        body: form,
        token,
      });
      setShowForm(false);
      setForm(EMPTY_PROJECT_FORM);
      projects.reload();
      setToast({ message: "Project created.", tone: "good" });
    } catch (err) {
      setToast({ message: err.message || "Failed to create project.", tone: "bad" });
    } finally {
      setSaving(false);
    }
  }

  const tasksByProject = (tasks.data?.tasks || []).reduce((acc, t) => {
    (acc[t.project_id] = acc[t.project_id] || []).push(t);
    return acc;
  }, {});

  return (
    <div className="screen-stack">
      {toast ? <Toast message={toast.message} tone={toast.tone} onDismiss={() => setToast(null)} /> : null}

      <ScreenHeader
        eyebrow="Work"
        title="Projects"
        description="Manage projects and their tasks."
        actions={
          <>
            <button className="secondary-button" onClick={() => { projects.reload(); tasks.reload(); }} type="button">Refresh</button>
            <button className="primary-button" onClick={() => setShowForm((v) => !v)} type="button">
              {showForm ? "Cancel" : "+ New Project"}
            </button>
          </>
        }
      />

      {showForm ? (
        <SectionCard title="New Project">
          <form className="inline-form" onSubmit={handleAddProject}>
            <div className="inline-form__grid">
              <div className="field-group">
                <label className="field-label">Project name *</label>
                <input className="field-input" name="name" value={form.name}
                  onChange={handleFieldChange} required placeholder="Project Alpha" />
              </div>
              <div className="field-group">
                <label className="field-label">Start date</label>
                <input className="field-input" name="start_date" type="date"
                  value={form.start_date} onChange={handleFieldChange} />
              </div>
              <div className="field-group">
                <label className="field-label">End date</label>
                <input className="field-input" name="end_date" type="date"
                  value={form.end_date} onChange={handleFieldChange} />
              </div>
              <div className="field-group">
                <label className="field-label">Colour</label>
                <div className="color-picker-row">
                  {PROJECT_COLORS.map((c) => (
                    <button key={c} type="button"
                      className={`color-swatch${form.color === c ? " color-swatch--active" : ""}`}
                      style={{ background: c }}
                      onClick={() => setForm((p) => ({ ...p, color: c }))}
                    />
                  ))}
                </div>
              </div>
            </div>
            <div className="command-row">
              <button className="primary-button" type="submit" disabled={saving}>
                {saving ? "Saving…" : "Create Project"}
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}

      {projects.loading ? <LoadingSkeleton label="Loading projects…" /> : null}
      {projects.error ? <ErrorCard error={projects.error} onRetry={projects.reload} /> : null}

      {projects.data ? (
        projects.data.projects?.length ? (
          <div className="project-grid">
            {projects.data.projects.map((p) => (
              <ProjectCard
                key={p.id}
                project={p}
                tasks={tasksByProject[p.id]}
                onAddTask={() => tasks.reload()}
              />
            ))}
          </div>
        ) : (
          <div className="state-card state-card--muted">
            <strong>No projects yet</strong>
            <p>Click "New Project" to create your first project.</p>
          </div>
        )
      ) : null}
    </div>
  );
}
