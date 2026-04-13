import { useEffect, useState } from "react";
import { requestJson } from "../api";

// ── PAT / Connection section ───────────────────────────────────────────────────

function ConnectionSection() {
  const [settings, setSettings] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [pat, setPat] = useState("");
  const [status, setStatus] = useState(null); // null | "saving" | "removing" | "ok" | "error"
  const [errorMsg, setErrorMsg] = useState("");

  function loadSettings() {
    requestJson("/api/settings").then(setSettings).catch(() => {});
  }

  useEffect(() => { loadSettings(); }, []);

  async function handleSave(e) {
    e.preventDefault();
    if (!pat.trim()) return;
    setStatus("saving");
    setErrorMsg("");
    try {
      await requestJson("/api/settings", { method: "POST", body: { asana_pat: pat } });
      setPat("");
      setShowForm(false);
      setStatus("ok");
      loadSettings();
      setTimeout(() => setStatus(null), 3000);
    } catch (err) {
      setStatus("error");
      setErrorMsg(err.message || "Failed to save PAT.");
    }
  }

  async function handleRemove() {
    if (!confirm("Remove the stored Asana PAT? This will also clear the configured project.")) return;
    setStatus("removing");
    try {
      await requestJson("/api/settings", { method: "POST", body: { asana_pat: "" } });
      setShowForm(false);
      setStatus(null);
      loadSettings();
    } catch (err) {
      setStatus("error");
      setErrorMsg(err.message || "Failed to remove PAT.");
    }
  }

  const isConnected = settings?.asana_pat_set;

  return (
    <div className="card" style={{ maxWidth: 560, marginBottom: "1.5rem" }}>
      <h3 style={{ margin: "0 0 1rem" }}>Asana Connection</h3>

      {isConnected && !showForm ? (
        // ── Connected state ──────────────────────────────────────────────────
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: ".75rem", marginBottom: ".75rem" }}>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: ".4rem",
              background: "#e8f5e9", color: "#2e7d32",
              padding: ".3rem .75rem", borderRadius: "99px", fontSize: ".875rem", fontWeight: 600,
            }}>
              <span style={{ fontSize: "1rem" }}>●</span> PAT stored
            </span>
            {settings.asana_workspace_gid && (
              <span className="supporting-text" style={{ fontSize: ".8rem" }}>
                Workspace: <code>{settings.asana_workspace_gid}</code>
              </span>
            )}
          </div>
          {status === "ok" && (
            <p style={{ color: "#2e7d32", fontSize: ".875rem", marginBottom: ".75rem" }}>
              Updated successfully.
            </p>
          )}
          <div style={{ display: "flex", gap: ".5rem" }}>
            <button type="button" className="ghost-button" onClick={() => { setShowForm(true); setStatus(null); }}>
              Change PAT
            </button>
            <button
              type="button"
              className="ghost-button ghost-button--danger"
              onClick={handleRemove}
              disabled={status === "removing"}
            >
              {status === "removing" ? "Removing…" : "Remove PAT"}
            </button>
          </div>
        </div>
      ) : (
        // ── Input form ───────────────────────────────────────────────────────
        <>
          {!isConnected && (
            <p className="supporting-text" style={{ marginBottom: "1rem" }}>
              Enter your Asana Personal Access Token to connect.
            </p>
          )}
          <form onSubmit={handleSave}>
            <div className="field">
              <label className="field-label">
                {isConnected ? "New Personal Access Token" : "Personal Access Token"}
              </label>
              <input
                className="text-input"
                type="password"
                value={pat}
                onChange={(e) => setPat(e.target.value)}
                placeholder="1/xxxxxxxxxxxx:yyyyyyyyyyyy"
                autoComplete="off"
                autoFocus
              />
              <p className="field-hint">
                Create a PAT in Asana: My Profile → Apps → Manage Developer Apps → New Access Token
              </p>
            </div>
            {status === "error" && (
              <p style={{ color: "#e53935", marginBottom: ".75rem", fontSize: ".875rem" }}>
                {errorMsg}
              </p>
            )}
            <div style={{ display: "flex", gap: ".5rem" }}>
              <button
                type="submit"
                className="primary-button"
                disabled={status === "saving" || !pat.trim()}
              >
                {status === "saving" ? "Connecting…" : "Save & Connect"}
              </button>
              {isConnected && (
                <button type="button" className="ghost-button" onClick={() => { setShowForm(false); setStatus(null); }}>
                  Cancel
                </button>
              )}
            </div>
          </form>
        </>
      )}
    </div>
  );
}

// ── Member sync section ────────────────────────────────────────────────────────

function MemberSyncSection() {
  const [diff, setDiff] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const [selAdd, setSelAdd] = useState(new Set());
  const [selUpdate, setSelUpdate] = useState(new Set());
  const [selDelete, setSelDelete] = useState(new Set());

  async function handleCheck() {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await requestJson("/api/asana/members/preview");
      setDiff(data);
      setSelAdd(new Set((data.to_add || []).map((u) => u.gid)));
      setSelUpdate(new Set((data.to_update || []).map((u) => u.gid)));
      setSelDelete(new Set());
    } catch (err) {
      setError(err.message || "Failed to load member preview.");
    } finally {
      setLoading(false);
    }
  }

  async function handleApply() {
    setApplying(true);
    setError("");
    try {
      const res = await requestJson("/api/asana/members/apply", {
        method: "POST",
        body: { add: [...selAdd], update: [...selUpdate], delete: [...selDelete] },
      });
      setResult(res);
      setDiff(null);
    } catch (err) {
      setError(err.message || "Failed to apply changes.");
    } finally {
      setApplying(false);
    }
  }

  function toggle(set, setFn, gid) {
    setFn((prev) => {
      const next = new Set(prev);
      if (next.has(gid)) next.delete(gid); else next.add(gid);
      return next;
    });
  }

  const hasSelections = selAdd.size > 0 || selUpdate.size > 0 || selDelete.size > 0;

  return (
    <div className="card" style={{ maxWidth: 720 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <div>
          <h3 style={{ margin: 0 }}>Team Member Sync</h3>
          <p className="supporting-text" style={{ marginTop: ".25rem" }}>
            Compare local members against Asana workspace users.
          </p>
        </div>
        <button type="button" className="primary-button" onClick={handleCheck} disabled={loading}>
          {loading ? "Checking…" : "Check Asana"}
        </button>
      </div>

      {error && <p style={{ color: "#e53935", marginBottom: ".75rem" }}>{error}</p>}

      {result && (
        <div style={{ background: "#f0f4f8", borderRadius: "8px", padding: ".75rem 1rem", marginBottom: "1rem" }}>
          <p style={{ margin: 0 }}>
            Applied: <strong>{result.added}</strong> added, <strong>{result.updated}</strong> updated,{" "}
            <strong>{result.deleted}</strong> removed.
          </p>
        </div>
      )}

      {diff && (
        <>
          {diff.to_add.length > 0 && (
            <div style={{ marginBottom: "1.5rem" }}>
              <h4 style={{ margin: "0 0 .5rem", color: "#2e7d32" }}>Add ({diff.to_add.length})</h4>
              <table className="data-table">
                <thead><tr><th style={{ width: 32 }}></th><th>Name</th><th>Email</th><th>GID</th></tr></thead>
                <tbody>
                  {diff.to_add.map((u) => (
                    <tr key={u.gid}>
                      <td><input type="checkbox" checked={selAdd.has(u.gid)} onChange={() => toggle(selAdd, setSelAdd, u.gid)} /></td>
                      <td>{u.name || "—"}</td>
                      <td>{u.email || "—"}</td>
                      <td className="muted">{u.gid}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {diff.to_update.length > 0 && (
            <div style={{ marginBottom: "1.5rem" }}>
              <h4 style={{ margin: "0 0 .5rem", color: "#e65100" }}>Update ({diff.to_update.length})</h4>
              <table className="data-table">
                <thead><tr><th style={{ width: 32 }}></th><th>Member</th><th>Changes</th></tr></thead>
                <tbody>
                  {diff.to_update.map((u) => (
                    <tr key={u.gid}>
                      <td><input type="checkbox" checked={selUpdate.has(u.gid)} onChange={() => toggle(selUpdate, setSelUpdate, u.gid)} /></td>
                      <td>{u.name}</td>
                      <td>
                        {Object.entries(u.changes).map(([field, ch]) => (
                          <div key={field} style={{ fontSize: ".875rem" }}>
                            <strong>{field}:</strong>{" "}
                            <span className="muted">{ch.from || "—"}</span> → <span>{ch.to}</span>
                          </div>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {diff.to_delete.length > 0 && (
            <div style={{ marginBottom: "1.5rem" }}>
              <h4 style={{ margin: "0 0 .5rem", color: "#e53935" }}>Remove ({diff.to_delete.length})</h4>
              <p className="supporting-text" style={{ marginBottom: ".5rem" }}>
                Local members with Asana GIDs no longer in the workspace. Unchecked by default.
              </p>
              <table className="data-table">
                <thead><tr><th style={{ width: 32 }}></th><th>Name</th><th>GID</th></tr></thead>
                <tbody>
                  {diff.to_delete.map((u) => (
                    <tr key={u.ext_id}>
                      <td><input type="checkbox" checked={selDelete.has(u.ext_id)} onChange={() => toggle(selDelete, setSelDelete, u.ext_id)} /></td>
                      <td>{u.name}</td>
                      <td className="muted">{u.ext_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {diff.to_add.length === 0 && diff.to_update.length === 0 && diff.to_delete.length === 0 && (
            <p className="muted">Local members are in sync with Asana.</p>
          )}

          {(diff.to_add.length > 0 || diff.to_update.length > 0 || diff.to_delete.length > 0) && (
            <button type="button" className="primary-button" onClick={handleApply} disabled={applying || !hasSelections}>
              {applying ? "Applying…" : "Apply Selected"}
            </button>
          )}
        </>
      )}
    </div>
  );
}

// ── Main screen ────────────────────────────────────────────────────────────────

export function SettingsScreen() {
  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <h2>Settings</h2>
          <p className="supporting-text">Asana integration configuration</p>
        </div>
      </div>
      <ConnectionSection />
      <MemberSyncSection />
    </div>
  );
}
