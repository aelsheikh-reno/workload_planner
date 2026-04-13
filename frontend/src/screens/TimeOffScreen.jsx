import { useEffect, useState } from "react";
import { requestJson } from "../api";

export function TimeOffScreen() {
  const [entries, setEntries] = useState([]);
  const [members, setMembers] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ member_id: "", start_date: "", end_date: "", leave_type: "annual" });
  const [saving, setSaving] = useState(false);

  function load() {
    Promise.all([
      requestJson("/api/float/time-off"),
      requestJson("/api/float/members"),
    ]).then(([toData, mData]) => {
      setEntries(toData.time_offs || []);
      setMembers(mData.members || []);
    });
  }

  useEffect(() => { load(); }, []);

  const memberMap = Object.fromEntries(members.map((m) => [m.id, m.display_name]));

  async function handleCreate(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await requestJson("/api/float/time-off", { method: "POST", body: form });
      setForm({ member_id: "", start_date: "", end_date: "", leave_type: "annual" });
      setShowForm(false);
      load();
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm("Remove this time-off entry?")) return;
    await requestJson(`/api/float/time-off/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <h2>Time Off</h2>
          <p className="supporting-text">{entries.length} entr{entries.length !== 1 ? "ies" : "y"}</p>
        </div>
        <button type="button" className="primary-button" onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "Add Entry"}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ maxWidth: 480, marginBottom: "1.5rem" }}>
          <h3 style={{ margin: "0 0 1rem" }}>New Time-Off Entry</h3>
          <form onSubmit={handleCreate}>
            <div className="field">
              <label className="field-label">Member *</label>
              <select
                className="text-input"
                value={form.member_id}
                onChange={(e) => setForm((f) => ({ ...f, member_id: e.target.value }))}
                required
              >
                <option value="">— select —</option>
                {members.map((m) => <option key={m.id} value={m.id}>{m.display_name}</option>)}
              </select>
            </div>
            <div className="field">
              <label className="field-label">Start date *</label>
              <input
                className="text-input"
                type="date"
                value={form.start_date}
                onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
                required
              />
            </div>
            <div className="field">
              <label className="field-label">End date *</label>
              <input
                className="text-input"
                type="date"
                value={form.end_date}
                onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
                required
              />
            </div>
            <div className="field">
              <label className="field-label">Type</label>
              <select
                className="text-input"
                value={form.leave_type}
                onChange={(e) => setForm((f) => ({ ...f, leave_type: e.target.value }))}
              >
                <option value="annual">Annual Leave</option>
                <option value="sick">Sick Leave</option>
                <option value="public_holiday">Public Holiday</option>
                <option value="custom">Other</option>
              </select>
            </div>
            <button type="submit" className="primary-button" disabled={saving}>
              {saving ? "Saving…" : "Add Entry"}
            </button>
          </form>
        </div>
      )}

      <div className="card">
        <table className="data-table">
          <thead>
            <tr>
              <th>Member</th>
              <th>Type</th>
              <th>From</th>
              <th>To</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td>{memberMap[e.member_id] || e.member_id}</td>
                <td>{e.leave_type}</td>
                <td>{e.start_date}</td>
                <td>{e.end_date}</td>
                <td>
                  <button
                    type="button"
                    className="ghost-button ghost-button--danger"
                    onClick={() => handleDelete(e.id)}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={5} className="muted" style={{ textAlign: "center", padding: "2rem" }}>
                  No time-off entries.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
