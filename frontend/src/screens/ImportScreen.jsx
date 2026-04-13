import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { buildApiUrl, requestJson } from "../api";

// ── Import Progress Component ───────────────────────────────────────────────

function ImportProgress({ progress, logs, error, result }) {
  const logRef = useRef(null);
  const [showLog, setShowLog] = useState(false);

  useEffect(() => {
    if (logRef.current && showLog) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs, showLog]);

  if (!progress && !error) return null;

  const pct = progress && progress.total > 0
    ? Math.round((progress.current / progress.total) * 100)
    : 0;

  return (
    <div style={{ marginTop: "1rem" }}>
      {/* Current step label */}
      {progress && (
        <div style={{ marginBottom: 6 }}>
          <div style={{ fontSize: ".85rem", fontWeight: 600, marginBottom: 4 }}>
            {progress.message}
          </div>
          {/* Progress bar */}
          {progress.total > 0 && (
            <div style={{
              width: "100%", height: 8, background: "var(--line)",
              borderRadius: 4, overflow: "hidden",
            }}>
              <div style={{
                width: `${pct}%`, height: "100%",
                background: error ? "var(--warn)" : "var(--accent)",
                borderRadius: 4,
                transition: "width 0.2s ease",
              }} />
            </div>
          )}
          {progress.total > 0 && (
            <div className="muted" style={{ fontSize: ".75rem", marginTop: 2 }}>
              {progress.current} / {progress.total} ({pct}%)
            </div>
          )}
          {progress.total === 0 && !error && (
            <div style={{
              width: "100%", height: 8, background: "var(--line)",
              borderRadius: 4, overflow: "hidden",
            }}>
              <div style={{
                width: "30%", height: "100%", background: "var(--accent)",
                borderRadius: 4,
                animation: "indeterminate 1.5s infinite ease-in-out",
              }} />
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="banner banner--warn" style={{ marginTop: 8 }}>
          {error}
        </div>
      )}

      {/* Log toggle + content */}
      {logs.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <button
            type="button"
            className="ghost-button"
            style={{ fontSize: ".78rem", padding: "2px 8px" }}
            onClick={() => setShowLog(!showLog)}
          >
            {showLog ? "Hide Log" : `Show Log (${logs.length} entries)`}
          </button>
          {showLog && (
            <pre
              ref={logRef}
              style={{
                marginTop: 4, padding: "8px 10px", fontSize: ".75rem",
                background: "var(--bg-dark, #1e1e1e)", color: "#d4d4d4",
                borderRadius: 4, maxHeight: 200, overflowY: "auto",
                fontFamily: "monospace", whiteSpace: "pre-wrap",
              }}
            >
              {logs.join("\n")}
            </pre>
          )}
        </div>
      )}

      {result && result.project_id && (
        <div style={{ marginTop: 12 }}>
          <a
            href={`/projects/${result.project_id}`}
            className="primary-button"
            style={{ display: "inline-block", textDecoration: "none" }}
          >
            View Project
          </a>
        </div>
      )}
    </div>
  );
}

// ── SSE Import Hook ─────────────────────────────────────────────────────────

function useSSEImport() {
  const [progress, setProgress] = useState(null);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [importing, setImporting] = useState(false);

  const startImport = useCallback(async (url, options = {}) => {
    setProgress(null);
    setLogs([]);
    setError(null);
    setResult(null);
    setImporting(true);

    const token = localStorage.getItem("float_token");
    const headers = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    let fetchOptions = { method: "POST", headers };

    if (options.rawBody) {
      // MS Project XML — raw bytes
      headers["Content-Type"] = "application/xml";
      fetchOptions.body = options.rawBody;
    } else if (options.jsonBody) {
      headers["Content-Type"] = "application/json";
      fetchOptions.body = JSON.stringify(options.jsonBody);
    }

    try {
      const resp = await fetch(buildApiUrl(url), fetchOptions);
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        setError(errData.error || `HTTP ${resp.status}`);
        setImporting(false);
        return null;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const events = buffer.split("\n\n");
        buffer = events.pop(); // keep incomplete chunk

        for (const raw of events) {
          if (!raw.trim()) continue;
          let eventType = "message";
          let data = "";
          for (const line of raw.split("\n")) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            else if (line.startsWith("data: ")) data = line.slice(6);
          }
          if (!data) continue;

          try {
            const parsed = JSON.parse(data);
            if (eventType === "progress") {
              setProgress(parsed);
            } else if (eventType === "log") {
              setLogs((prev) => [...prev, parsed.message]);
            } else if (eventType === "complete") {
              setResult(parsed);
              setImporting(false);
              return parsed;
            } else if (eventType === "error") {
              setError(parsed.message);
              setImporting(false);
              return null;
            }
          } catch (e) {
            // ignore malformed JSON
          }
        }
      }

      setImporting(false);
      return result;
    } catch (err) {
      setError(err.message);
      setImporting(false);
      return null;
    }
  }, []);

  return { progress, logs, error, result, importing, startImport };
}

// ── Phase constants ──────────────────────────────────────────────────────────
const PHASE_INPUT = "input";
const PHASE_IMPORTING = "importing";
const PHASE_WIZARD_DATE = "wizard-date";
const PHASE_WIZARD_MEMBERS = "wizard-members";
const PHASE_DONE = "done";

// ── Source Tab Toggle ────────────────────────────────────────────────────────

function SourceTabs({ mode, onSwitch }) {
  return (
    <div className="tab-bar" style={{ marginBottom: "1.5rem" }}>
      <button
        type="button"
        className={`tab-button${mode === "xml" ? " tab-button--active" : ""}`}
        onClick={() => onSwitch("xml")}
      >
        MS Project XML
      </button>
      <button
        type="button"
        className={`tab-button${mode === "asana" ? " tab-button--active" : ""}`}
        onClick={() => onSwitch("asana")}
      >
        From Asana
      </button>
    </div>
  );
}

// ── XML Import Form ──────────────────────────────────────────────────────────

function XmlImportForm({ onImported, onError, importing, setImporting }) {
  const fileRef = useRef(null);
  const sse = useSSEImport();
  const [preview, setPreview] = useState(null); // preview response from backend
  const [xmlBase64, setXmlBase64] = useState(null); // stored for step 2
  const [resourceMap, setResourceMap] = useState({}); // resource_ext_id → member_id
  const [previewing, setPreviewing] = useState(false);

  async function handlePreview(e) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    setPreviewing(true);
    const token = localStorage.getItem("float_token");
    try {
      const rawBytes = await file.arrayBuffer();
      // Store base64 for step 2 (chunked to avoid stack overflow on large files)
      const bytes = new Uint8Array(rawBytes);
      let binary = "";
      const chunkSize = 8192;
      for (let i = 0; i < bytes.length; i += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
      }
      setXmlBase64(btoa(binary));

      const resp = await fetch(buildApiUrl("/api/import/preview"), {
        method: "POST",
        headers: {
          "Content-Type": "application/xml",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: rawBytes,
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        onError(data.error || "Preview failed.");
      } else {
        setPreview(data);
        // Pre-fill mapping: use matched or suggested members
        const defaultMap = {};
        for (const r of data.resources || []) {
          if (r.matched_member_id) {
            defaultMap[r.resource_external_id] = r.matched_member_id;
          } else if (r.suggested_member_id) {
            defaultMap[r.resource_external_id] = r.suggested_member_id;
          }
        }
        setResourceMap(defaultMap);
      }
    } catch (err) {
      onError(err.message);
    } finally {
      setPreviewing(false);
    }
  }

  async function handleApply() {
    if (!xmlBase64) {
      onError("No XML data stored. Please re-select the file.");
      return;
    }
    setImporting(true);
    try {
      const data = await requestJson("/api/import/apply", {
        method: "POST",
        body: { xml_base64: xmlBase64, resource_mapping: resourceMap },
      });
      onImported(data);
      // Don't call setImporting(false) here — onImported already
      // advances the parent phase. setImporting(false) would reset
      // the phase back to PHASE_INPUT, undoing the transition.
    } catch (err) {
      onError(err.message || "Import failed.");
      setImporting(false);
    }
  }

  function resetPreview() {
    setPreview(null);
    setXmlBase64(null);
    setResourceMap({});
  }

  // Step 1: File selection
  if (!preview) {
    return (
      <form onSubmit={handlePreview}>
        <div className="field">
          <label className="field-label">MS Project XML file</label>
          <input
            ref={fileRef}
            type="file"
            accept=".xml,application/xml,text/xml"
            required
            className="file-input"
          />
          <p className="field-hint">
            Export from MS Project: File &rarr; Save As &rarr; XML Format (.xml)
          </p>
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: "1.5rem" }}>
          <button type="submit" className="primary-button" disabled={previewing}>
            {previewing ? "Parsing..." : "Import"}
          </button>
        </div>
      </form>
    );
  }

  // Step 2: Resource mapping
  const allMapped = (preview.resources || []).every(
    (r) => r.matched_member_id || resourceMap[r.resource_external_id]
  );

  return (
    <div>
      {/* Summary */}
      <div style={{ marginBottom: "1rem", padding: "10px 14px", border: "1px solid var(--accent)", borderRadius: 6, background: "#f0f7ff" }}>
        <div style={{ fontSize: ".88rem", fontWeight: 600, marginBottom: 4 }}>
          File parsed successfully
        </div>
        <div className="muted" style={{ fontSize: ".82rem" }}>
          {preview.task_count} tasks ({preview.leaf_task_count} leaf, {preview.parent_task_count} parent)
          {" "}&middot;{" "}{preview.dependency_count} dependencies
          {" "}&middot;{" "}{preview.resources?.length || 0} resources
        </div>
      </div>

      {/* Resource mapping */}
      <div style={{ marginBottom: "1rem" }}>
        <label className="field-label" style={{ display: "block", marginBottom: 6, fontSize: ".82rem", fontWeight: 600 }}>
          Map Resources to Team Members
        </label>
        {preview.has_unmatched && (
          <div className="muted" style={{ fontSize: ".78rem", marginBottom: 8 }}>
            Some resources in the XML file don't match existing members. Map them below so assignments are preserved.
          </div>
        )}

        <div style={{ border: "1px solid var(--line)", borderRadius: 6, overflow: "hidden" }}>
          {(preview.resources || []).map((r) => {
            const isMatched = !!r.matched_member_id;
            const selectedId = resourceMap[r.resource_external_id] || r.matched_member_id || "";

            return (
              <div key={r.resource_external_id} style={{
                display: "flex", alignItems: "center", gap: ".75rem",
                padding: "8px 12px", borderBottom: "1px solid var(--line)",
                fontSize: ".85rem",
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>{r.resource_name}</div>
                  <div className="muted" style={{ fontSize: ".72rem" }}>
                    {r.task_count} task{r.task_count !== 1 ? "s" : ""} assigned
                  </div>
                </div>
                <div style={{ fontSize: ".82rem", color: "var(--text-muted)", margin: "0 4px" }}>&rarr;</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  {isMatched ? (
                    <div style={{ color: "var(--success, #4CAF50)", fontSize: ".82rem", fontWeight: 600 }}>
                      {r.matched_member_name} (auto-matched)
                    </div>
                  ) : (
                    <select
                      value={selectedId}
                      onChange={(e) => setResourceMap((prev) => ({
                        ...prev,
                        [r.resource_external_id]: e.target.value ? parseInt(e.target.value, 10) : null,
                      }))}
                      style={{ width: "100%", fontSize: ".82rem", padding: "4px 6px" }}
                    >
                      <option value="">-- Select member --</option>
                      {(preview.available_members || []).map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.display_name}
                          {r.suggested_member_id === m.id ? " (suggested)" : ""}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 8, marginTop: "1.5rem" }}>
        <button type="button" className="secondary-button" onClick={resetPreview}>
          Back
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={handleApply}
          disabled={importing || !allMapped}
        >
          {importing ? "Importing..." : "Import"}
        </button>
      </div>
      {!allMapped && (
        <div style={{ color: "var(--warn)", fontSize: ".78rem", marginTop: 6 }}>
          Please map all resources to team members before importing.
        </div>
      )}

      <ImportProgress progress={sse.progress} logs={sse.logs} error={sse.error} result={sse.result} />
    </div>
  );
}

// ── Asana Import Form ────────────────────────────────────────────────────────

function AsanaImportForm({ onImported, onError, importing, setImporting }) {
  const [asanaProjects, setAsanaProjects] = useState(null); // null = loading
  const [selectedGid, setSelectedGid] = useState("");
  const [patConfigured, setPatConfigured] = useState(true);
  const sse = useSSEImport();

  useEffect(() => {
    requestJson("/api/asana/projects")
      .then((d) => setAsanaProjects(d.projects || []))
      .catch(() => {
        setPatConfigured(false);
        setAsanaProjects([]);
      });
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!selectedGid) return;

    setImporting(true);
    const result = await sse.startImport("/api/import/asana/stream", {
      jsonBody: { asana_project_gid: selectedGid },
    });
    if (result) {
      onImported(result);
      // Don't call setImporting(false) — onImported advances the phase
    } else {
      if (sse.error) onError(sse.error);
      setImporting(false);
    }
  }

  if (asanaProjects === null) {
    return <p className="muted">Loading Asana projects...</p>;
  }

  if (!patConfigured) {
    return (
      <div className="banner banner--warn">
        <strong>Asana not configured.</strong> Go to{" "}
        <a href="/settings">Settings</a> to set your Asana Personal Access Token first.
      </div>
    );
  }

  if (asanaProjects.length === 0) {
    return (
      <div className="banner banner--warn">
        No projects found in your Asana workspace. Check your PAT and workspace in{" "}
        <a href="/settings">Settings</a>.
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="field">
        <label className="field-label">Asana Project</label>
        <select
          className="input"
          value={selectedGid}
          onChange={(e) => setSelectedGid(e.target.value)}
          required
        >
          <option value="">-- Select a project --</option>
          {asanaProjects.map((p) => (
            <option key={p.gid} value={p.gid}>
              {p.name}{p.archived ? " (archived)" : ""}
            </option>
          ))}
        </select>
        <p className="field-hint">
          All tasks, hierarchy, dependencies, and assignees will be imported.
          Missing members will be auto-created.
        </p>
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: "1.5rem" }}>
        <button
          type="submit"
          className="primary-button"
          disabled={importing || sse.importing || !selectedGid}
        >
          {sse.importing ? "Importing from Asana..." : "Import from Asana"}
        </button>
      </div>

      <ImportProgress progress={sse.progress} logs={sse.logs} error={sse.error} result={sse.result} />
    </form>
  );
}

// ── Wizard Step 1: Start Date ────────────────────────────────────────────────

function WizardStartDate({ importResult, onNext }) {
  const currentDate = importResult.start_date || "";
  const [newDate, setNewDate] = useState(currentDate);
  const [shifting, setShifting] = useState(false);
  const [shifted, setShifted] = useState(false);

  async function handleShift() {
    if (!newDate || newDate === currentDate) {
      onNext();
      return;
    }
    setShifting(true);
    try {
      await requestJson(
        `/api/float/projects/${importResult.project_id}/shift-start`,
        { method: "POST", body: { new_start_date: newDate } }
      );
      setShifted(true);
      setTimeout(() => onNext(), 600);
    } catch (err) {
      alert("Failed to shift dates: " + err.message);
      setShifting(false);
    }
  }

  return (
    <div>
      <h3 style={{ margin: "0 0 .5rem" }}>Project Start Date</h3>
      <p className="supporting-text" style={{ marginBottom: "1rem" }}>
        The imported project starts on <strong>{currentDate || "unknown"}</strong> and ends on{" "}
        <strong>{importResult.end_date || "unknown"}</strong>. You can shift all task dates to a
        new start date.
      </p>

      <div className="field">
        <label className="field-label">Start date</label>
        <input
          type="date"
          className="input"
          value={newDate}
          onChange={(e) => setNewDate(e.target.value)}
          style={{ maxWidth: 220 }}
        />
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: "1.25rem" }}>
        {newDate && newDate !== currentDate ? (
          <button
            type="button"
            className="primary-button"
            disabled={shifting}
            onClick={handleShift}
          >
            {shifting ? "Shifting..." : shifted ? "Shifted!" : "Apply & Shift Tasks"}
          </button>
        ) : null}
        <button
          type="button"
          className="secondary-button"
          onClick={onNext}
          disabled={shifting}
        >
          {newDate === currentDate || !newDate ? "Keep Original & Continue" : "Skip"}
        </button>
      </div>
    </div>
  );
}

// ── Wizard Step 2: Member Picker ─────────────────────────────────────────────

function WizardMembers({ importResult, onDone }) {
  const [allMembers, setAllMembers] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    requestJson("/api/float/members")
      .then((d) => {
        const members = (d.members || []).filter((m) => m.is_active !== false);
        setAllMembers(members);
        // Pre-check members discovered from Asana import
        const discovered = new Set(
          (importResult.discovered_member_ids || []).map((id) => id)
        );
        if (discovered.size > 0) {
          setSelected(discovered);
        }
      })
      .finally(() => setLoading(false));
  }, [importResult.discovered_member_ids]);

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSave() {
    if (selected.size === 0) {
      onDone();
      return;
    }
    setSaving(true);
    try {
      await requestJson(
        `/api/float/projects/${importResult.project_id}/members`,
        { method: "POST", body: { member_ids: [...selected] } }
      );
      onDone();
    } catch (err) {
      alert("Failed to add members: " + err.message);
      setSaving(false);
    }
  }

  if (loading) return <p className="muted">Loading members...</p>;

  return (
    <div>
      <h3 style={{ margin: "0 0 .5rem" }}>Team Members</h3>
      <p className="supporting-text" style={{ marginBottom: "1rem" }}>
        Select the members who will work on this project. You can change this later
        from the project's Schedule tab.
      </p>

      {allMembers.length === 0 ? (
        <p className="muted">
          No members found. Add team members from the{" "}
          <a href="/members">Members</a> page or sync from Asana in{" "}
          <a href="/settings">Settings</a>.
        </p>
      ) : (
        <div
          style={{
            maxHeight: 320,
            overflowY: "auto",
            border: "1px solid var(--line)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          {allMembers.map((m) => (
            <label
              key={m.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: ".75rem",
                padding: ".6rem 1rem",
                borderBottom: "1px solid var(--line)",
                cursor: "pointer",
                background: selected.has(m.id) ? "var(--accent-light)" : "transparent",
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(m.id)}
                onChange={() => toggle(m.id)}
              />
              <span
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  background: m.avatar_color || "#4A90D9",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#fff",
                  fontSize: ".75rem",
                  fontWeight: 600,
                  flexShrink: 0,
                }}
              >
                {(m.display_name || "?")[0]}
              </span>
              <div>
                <div style={{ fontWeight: 500, fontSize: ".9rem" }}>{m.display_name}</div>
                {m.email && (
                  <div className="muted" style={{ fontSize: ".78rem" }}>{m.email}</div>
                )}
              </div>
            </label>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: "1.25rem" }}>
        <button
          type="button"
          className="primary-button"
          disabled={saving}
          onClick={handleSave}
        >
          {saving
            ? "Adding..."
            : selected.size > 0
              ? `Add ${selected.size} Member${selected.size !== 1 ? "s" : ""}`
              : "Skip"}
        </button>
        {selected.size > 0 && (
          <button
            type="button"
            className="secondary-button"
            onClick={onDone}
          >
            Skip
          </button>
        )}
      </div>
    </div>
  );
}

// ── Import Summary Banner ────────────────────────────────────────────────────

function _countLine(created, updated, singular, plural) {
  const parts = [];
  if (created > 0) parts.push(`${created} new`);
  if (updated > 0) parts.push(`${updated} updated`);
  if (parts.length === 0) return `0 ${plural}`;
  return `${parts.join(", ")} ${created + updated !== 1 ? plural : singular}`;
}

function ImportSummary({ result, source }) {
  return (
    <div className="banner banner--ok" style={{ marginBottom: "1.25rem" }}>
      <strong>Import successful</strong> ({source === "asana" ? "from Asana" : "MS Project XML"})
      <ul style={{ margin: "0.5rem 0 0", padding: "0 0 0 1.2rem" }}>
        <li>{_countLine(result.projects, result.projects_updated || 0, "project", "projects")}</li>
        <li>{_countLine(result.tasks, result.tasks_updated || 0, "task", "tasks")}</li>
        <li>{_countLine(result.dependencies, result.dependencies_updated || 0, "dependency", "dependencies")}</li>
        <li>{result.assignments} assignment{result.assignments !== 1 ? "s" : ""}</li>
        {result.members_created > 0 && (
          <li>{result.members_created} new member{result.members_created !== 1 ? "s" : ""} created</li>
        )}
        {result.unmatched_resources?.length > 0 && (
          <li className="warn">
            {result.unmatched_resources.length} unmatched resource
            {result.unmatched_resources.length !== 1 ? "s" : ""}
          </li>
        )}
      </ul>
    </div>
  );
}

// ── Main ImportScreen ────────────────────────────────────────────────────────

export function ImportScreen() {
  const [mode, setMode] = useState("xml"); // "xml" | "asana"
  const [phase, setPhase] = useState(PHASE_INPUT);
  const [importResult, setImportResult] = useState(null);
  const [importSource, setImportSource] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  function handleImported(data) {
    setImportResult(data);
    setImportSource(mode);
    setError(null);
    // Go to wizard if we have a project_id and dates
    if (data.project_id && data.start_date) {
      setPhase(PHASE_WIZARD_DATE);
    } else if (data.project_id) {
      setPhase(PHASE_WIZARD_MEMBERS);
    } else {
      setPhase(PHASE_DONE);
    }
  }

  function handleError(msg) {
    setError(msg);
    setPhase(PHASE_INPUT);
  }

  function handleSwitchMode(newMode) {
    if (phase === PHASE_INPUT || phase === PHASE_IMPORTING) {
      setMode(newMode);
      setError(null);
    }
  }

  const importing = phase === PHASE_IMPORTING;

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <h2>Import Project</h2>
          <p className="supporting-text">
            Import from an MS Project XML file or pull directly from Asana.
          </p>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 600 }}>
        {/* Phase: input or importing */}
        {(phase === PHASE_INPUT || phase === PHASE_IMPORTING) && (
          <>
            <SourceTabs mode={mode} onSwitch={handleSwitchMode} />

            {error && (
              <div className="banner banner--warn" style={{ marginBottom: "1rem" }}>
                <strong>Import failed:</strong> {error}
              </div>
            )}

            {mode === "xml" ? (
              <XmlImportForm
                onImported={handleImported}
                onError={handleError}
                importing={importing}
                setImporting={(v) => setPhase(v ? PHASE_IMPORTING : PHASE_INPUT)}
              />
            ) : (
              <AsanaImportForm
                onImported={handleImported}
                onError={handleError}
                importing={importing}
                setImporting={(v) => setPhase(v ? PHASE_IMPORTING : PHASE_INPUT)}
              />
            )}
          </>
        )}

        {/* Phase: wizard - start date */}
        {phase === PHASE_WIZARD_DATE && importResult && (
          <>
            <ImportSummary result={importResult} source={importSource} />
            <WizardStartDate
              importResult={importResult}
              onNext={() => setPhase(PHASE_WIZARD_MEMBERS)}
            />
          </>
        )}

        {/* Phase: wizard - members */}
        {phase === PHASE_WIZARD_MEMBERS && importResult && (
          <>
            {phase === PHASE_WIZARD_MEMBERS && (
              <ImportSummary result={importResult} source={importSource} />
            )}
            <WizardMembers
              importResult={importResult}
              onDone={() => setPhase(PHASE_DONE)}
            />
          </>
        )}

        {/* Phase: done */}
        {phase === PHASE_DONE && importResult && (
          <>
            <ImportSummary result={importResult} source={importSource} />
            <div style={{ display: "flex", gap: 8 }}>
              {importResult.project_id && (
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => navigate(`/projects/${importResult.project_id}`)}
                >
                  View Project
                </button>
              )}
              <button
                type="button"
                className="secondary-button"
                onClick={() => navigate("/")}
              >
                Back to Dashboard
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setPhase(PHASE_INPUT);
                  setImportResult(null);
                  setError(null);
                }}
              >
                Import Another
              </button>
            </div>
          </>
        )}
      </div>

      {/* Help section - only show during input phase */}
      {(phase === PHASE_INPUT || phase === PHASE_IMPORTING) && mode === "xml" && (
        <div className="card" style={{ maxWidth: 600, marginTop: "1.5rem" }}>
          <h3 style={{ margin: "0 0 .75rem" }}>How to export from MS Project</h3>
          <ol style={{ margin: 0, paddingLeft: "1.4rem", lineHeight: 1.8 }}>
            <li>Open your project in Microsoft Project</li>
            <li>Go to <strong>File &rarr; Save As</strong></li>
            <li>Choose <strong>XML Format (*.xml)</strong> from the file type dropdown</li>
            <li>Save the file and upload it here</li>
          </ol>
          <p className="supporting-text" style={{ marginTop: ".75rem" }}>
            Tasks, resources, assignments, and dependencies are all imported.
            Effort hours come from the task Work field.
          </p>
        </div>
      )}
    </div>
  );
}
