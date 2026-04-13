import { useEffect, useState } from "react";
import { requestJson } from "../api";

const ALL_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function EditRow({ member, onSave, onCancel }) {
  const [form, setForm] = useState({
    display_name: member.display_name || "",
    email: member.email || "",
    weekly_capacity_hours: member.weekly_capacity_hours ?? 40,
    role: member.role || "team_member",
    working_days: member.working_days || ["Sun", "Mon", "Tue", "Wed", "Thu"],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function toggleDay(day) {
    setForm((f) => {
      const days = f.working_days.includes(day)
        ? f.working_days.filter((d) => d !== day)
        : [...f.working_days, day];
      return { ...f, working_days: days };
    });
  }

  async function handleSave(e) {
    e.preventDefault();
    if (!form.display_name.trim()) return;
    setSaving(true);
    setError("");
    try {
      await requestJson(`/api/float/members/${member.id}`, { method: "PATCH", body: form });
      onSave();
    } catch (err) {
      setError(err.message || "Save failed.");
      setSaving(false);
    }
  }

  return (
    <tr style={{ background: "var(--color-surface-2, #f8fafc)" }}>
      <td colSpan={5} style={{ padding: "1rem 1.25rem" }}>
        <form onSubmit={handleSave}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".75rem 1.25rem", marginBottom: ".75rem" }}>
            <div className="field" style={{ margin: 0 }}>
              <label className="field-label">Name *</label>
              <input
                className="text-input"
                value={form.display_name}
                onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
                required
                autoFocus
              />
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label className="field-label">Email</label>
              <input
                className="text-input"
                type="email"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              />
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label className="field-label">Weekly capacity (hours)</label>
              <input
                className="text-input"
                type="number"
                min="1"
                max="80"
                value={form.weekly_capacity_hours}
                onChange={(e) => setForm((f) => ({ ...f, weekly_capacity_hours: +e.target.value }))}
              />
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label className="field-label">Role</label>
              <select
                className="text-input"
                value={form.role}
                onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
              >
                <option value="team_member">Team Member</option>
                <option value="manager">Manager</option>
              </select>
            </div>
          </div>

          <div className="field" style={{ margin: "0 0 .75rem" }}>
            <label className="field-label">Working days</label>
            <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap", marginTop: ".25rem" }}>
              {ALL_DAYS.map((day) => (
                <label
                  key={day}
                  style={{
                    display: "flex", alignItems: "center", gap: ".3rem",
                    cursor: "pointer", userSelect: "none",
                    padding: ".25rem .6rem",
                    borderRadius: "6px",
                    background: form.working_days.includes(day) ? "var(--color-primary, #1565C0)" : "var(--color-border, #e0e0e0)",
                    color: form.working_days.includes(day) ? "#fff" : "inherit",
                    fontSize: ".8rem", fontWeight: 500,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={form.working_days.includes(day)}
                    onChange={() => toggleDay(day)}
                    style={{ display: "none" }}
                  />
                  {day}
                </label>
              ))}
            </div>
          </div>

          {error && <p style={{ color: "#e53935", fontSize: ".875rem", marginBottom: ".5rem" }}>{error}</p>}

          <div style={{ display: "flex", gap: ".5rem" }}>
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button type="button" className="ghost-button" onClick={onCancel}>Cancel</button>
          </div>
        </form>
      </td>
    </tr>
  );
}

export function MembersScreen() {
  const [members, setMembers] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ display_name: "", email: "", weekly_capacity_hours: 40 });
  const [saving, setSaving] = useState(false);

  function load() {
    requestJson("/api/float/members").then((d) => setMembers(d.members || []));
  }

  useEffect(() => { load(); }, []);

  async function handleCreate(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await requestJson("/api/float/members", { method: "POST", body: form });
      setForm({ display_name: "", email: "", weekly_capacity_hours: 40 });
      setShowForm(false);
      load();
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDeactivate(id) {
    if (!confirm("Deactivate this member?")) return;
    await requestJson(`/api/float/members/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <h2>Team Members</h2>
          <p className="supporting-text">{members.length} member{members.length !== 1 ? "s" : ""}</p>
        </div>
        <button type="button" className="primary-button" onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "Add Member"}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ maxWidth: 480, marginBottom: "1.5rem" }}>
          <h3 style={{ margin: "0 0 1rem" }}>New Team Member</h3>
          <form onSubmit={handleCreate}>
            <div className="field">
              <label className="field-label">Name *</label>
              <input
                className="text-input"
                value={form.display_name}
                onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
                required
              />
            </div>
            <div className="field">
              <label className="field-label">Email</label>
              <input
                className="text-input"
                type="email"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              />
            </div>
            <div className="field">
              <label className="field-label">Weekly capacity (hours)</label>
              <input
                className="text-input"
                type="number"
                min="1"
                max="80"
                value={form.weekly_capacity_hours}
                onChange={(e) => setForm((f) => ({ ...f, weekly_capacity_hours: +e.target.value }))}
              />
            </div>
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? "Saving…" : "Add Member"}
            </button>
          </form>
        </div>
      )}

      <div className="card">
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Capacity</th>
              <th>Role</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              editingId === m.id ? (
                <EditRow
                  key={m.id}
                  member={m}
                  onSave={() => { setEditingId(null); load(); }}
                  onCancel={() => setEditingId(null)}
                />
              ) : (
                <tr key={m.id}>
                  <td>
                    <span className="avatar-dot" style={{ background: m.avatar_color || "#4A90D9" }} />
                    {m.display_name}
                  </td>
                  <td>{m.email || "—"}</td>
                  <td>{m.weekly_capacity_hours}h/wk</td>
                  <td>{m.role}</td>
                  <td>
                    <div style={{ display: "flex", gap: ".5rem" }}>
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => setEditingId(m.id)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="ghost-button ghost-button--danger"
                        onClick={() => handleDeactivate(m.id)}
                      >
                        Deactivate
                      </button>
                    </div>
                  </td>
                </tr>
              )
            ))}
            {members.length === 0 && (
              <tr>
                <td colSpan={5} className="muted" style={{ textAlign: "center", padding: "2rem" }}>
                  No team members yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
