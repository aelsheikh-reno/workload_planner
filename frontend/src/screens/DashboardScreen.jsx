import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { requestJson } from "../api";

// ── Asana project sync panel ───────────────────────────────────────────────────

function AsanaSyncPanel({ onClose }) {
  const [projects, setProjects] = useState(null); // null = loading
  const [selectedGid, setSelectedGid] = useState("");
  const [currentGid, setCurrentGid] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      requestJson("/api/asana/projects"),
      requestJson("/api/settings"),
    ])
      .then(([pData, sData]) => {
        setProjects(pData.projects || []);
        const gid = sData.asana_project_gid || "";
        setCurrentGid(gid);
        setSelectedGid(gid);
      })
      .catch((err) => {
        setError(err.message || "Could not load Asana projects. Make sure your PAT is configured in Settings.");
        setProjects([]);
      });
  }, []);

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      await requestJson("/api/settings", { method: "POST", body: { asana_project_gid: selectedGid } });
      setCurrentGid(selectedGid);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.message || "Failed to save project.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card" style={{ marginBottom: "1.25rem", borderLeft: "3px solid #6c8ebf" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h4 style={{ margin: "0 0 .25rem" }}>Asana Project Sync</h4>
          <p className="supporting-text" style={{ marginBottom: ".75rem" }}>
            Select which Asana project to sync tasks with.
            {currentGid && <> Current GID: <code>{currentGid}</code></>}
          </p>
        </div>
        <button type="button" className="ghost-button" onClick={onClose} style={{ padding: ".25rem .5rem" }}>
          ✕
        </button>
      </div>

      {projects === null && <p className="muted">Loading projects…</p>}

      {error && (
        <p style={{ color: "#e53935", fontSize: ".875rem", marginBottom: ".5rem" }}>
          {error}
        </p>
      )}

      {projects !== null && projects.length === 0 && !error && (
        <p className="muted">No projects found. Configure your Asana PAT in <a href="/settings">Settings</a> first.</p>
      )}

      {projects !== null && projects.length > 0 && (
        <form onSubmit={handleSave} style={{ display: "flex", gap: ".75rem", alignItems: "center", flexWrap: "wrap" }}>
          <select
            className="text-input"
            style={{ flex: "1", minWidth: "220px", maxWidth: "400px" }}
            value={selectedGid}
            onChange={(e) => setSelectedGid(e.target.value)}
          >
            <option value="">— select a project —</option>
            {projects.map((p) => (
              <option key={p.gid} value={p.gid}>
                {p.name}{p.archived ? " (archived)" : ""}
              </option>
            ))}
          </select>
          <button type="submit" className="primary-button" disabled={saving || !selectedGid}>
            {saving ? "Saving…" : "Set Project"}
          </button>
          {saved && <span style={{ color: "#2e7d32", fontSize: ".875rem" }}>Saved.</span>}
        </form>
      )}
    </div>
  );
}

// ── Dashboard ──────────────────────────────────────────────────────────────────

export function DashboardScreen() {
  const [projects, setProjects] = useState([]);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAsanaPanel, setShowAsanaPanel] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      requestJson("/api/float/projects"),
      requestJson("/api/schedule/runs").catch(() => ({ runs: [] })),
    ]).then(([projData, runData]) => {
      setProjects(projData.projects || []);
      setRuns(runData.runs || []);
    }).finally(() => setLoading(false));
  }, []);

  const lastRun = runs[0];

  async function handleDeleteProject(id, { deleteFromAsana = false } = {}) {
    const qs = deleteFromAsana
      ? `?permanent=true&delete_from_asana=true`
      : `?permanent=true`;
    try {
      await requestJson(`/api/float/projects/${id}${qs}`, { method: "DELETE" });
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      alert("Delete failed: " + (err.message || "Unknown error"));
    } finally {
      setConfirmDeleteId(null);
    }
  }

  if (loading) return <div className="screen-loading">Loading projects…</div>;

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <h2>Projects</h2>
          <p className="supporting-text">
            {projects.length === 0
              ? "No projects yet — import an MS Project XML file or sync from Asana."
              : `${projects.length} project${projects.length !== 1 ? "s" : ""}`}
          </p>
        </div>
        <div style={{ display: "flex", gap: ".5rem" }}>
          <button
            type="button"
            className="ghost-button"
            onClick={() => setShowAsanaPanel((v) => !v)}
          >
            Asana Sync
          </button>
          <button
            className="primary-button"
            onClick={() => navigate("/import")}
            type="button"
          >
            Import Project
          </button>
        </div>
      </div>

      {showAsanaPanel && (
        <AsanaSyncPanel onClose={() => setShowAsanaPanel(false)} />
      )}

      {lastRun && (
        <div className={`banner banner--${lastRun.status === "succeeded" ? "ok" : "warn"}`}>
          Last schedule run: <strong>{lastRun.status}</strong> &nbsp;·&nbsp;
          {lastRun.written_count} allocations written &nbsp;·&nbsp;
          {lastRun.triggered_at?.slice(0, 16).replace("T", " ")}
        </div>
      )}

      {projects.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state__icon">▦</div>
          <p>Import an MS Project XML file to create your first project.</p>
          <button
            className="primary-button"
            onClick={() => navigate("/import")}
            type="button"
          >
            Import Project
          </button>
        </div>
      ) : (
        <div className="project-grid">
          {projects.map((p) => (
            <div
              key={p.id}
              className="project-card"
              style={{ borderTop: `4px solid ${p.color || "#2196F3"}`, cursor: "default", position: "relative" }}
            >
              <button
                type="button"
                style={{ all: "unset", display: "block", cursor: "pointer", flex: 1 }}
                onClick={() => navigate(`/projects/${p.id}`)}
              >
                <div className="project-card__name">{p.name}</div>
                <div className="project-card__meta">
                  <span className={`status-badge status-badge--${p.status}`}>{p.status}</span>
                  {p.start_date && (
                    <span className="project-card__date">
                      {p.start_date} → {p.end_date || "…"}
                    </span>
                  )}
                </div>
              </button>

              {confirmDeleteId === p.id ? (
                <div style={{ marginTop: ".75rem" }}>
                  {p.asana_project_gid ? (
                    <>
                      <span style={{ fontSize: ".8rem", color: "var(--danger)", display: "block", marginBottom: ".5rem" }}>
                        This project is linked to Asana. Delete from Asana too?
                      </span>
                      <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="ghost-button"
                          style={{ fontSize: ".75rem", color: "var(--danger)", borderColor: "var(--danger-border)" }}
                          onClick={() => handleDeleteProject(p.id, { deleteFromAsana: true })}
                        >
                          Delete from Asana too
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          style={{ fontSize: ".75rem", color: "var(--danger)", borderColor: "var(--danger-border)" }}
                          onClick={() => handleDeleteProject(p.id)}
                        >
                          Unlink only
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          style={{ fontSize: ".75rem" }}
                          onClick={() => setConfirmDeleteId(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </>
                  ) : (
                    <div style={{ display: "flex", gap: ".5rem", alignItems: "center" }}>
                      <span style={{ fontSize: ".8rem", color: "var(--danger)" }}>Delete project and all tasks?</span>
                      <button
                        type="button"
                        className="ghost-button"
                        style={{ fontSize: ".75rem", color: "var(--danger)", borderColor: "var(--danger-border)" }}
                        onClick={() => handleDeleteProject(p.id)}
                      >
                        Yes, delete
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        style={{ fontSize: ".75rem" }}
                        onClick={() => setConfirmDeleteId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <button
                  type="button"
                  className="ghost-button"
                  style={{ fontSize: ".75rem", marginTop: ".5rem", color: "var(--danger)" }}
                  onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(p.id); }}
                >
                  Delete
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
