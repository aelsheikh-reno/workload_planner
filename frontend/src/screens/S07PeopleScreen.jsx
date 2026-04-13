import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { requestJson } from "../api";
import { ErrorCard, LoadingSkeleton, ScreenHeader, SectionCard, Toast } from "../components/ScreenPrimitives";
import { useRouteData } from "../useRouteData";

const AVATAR_COLORS = [
  "#4CAF50", "#2196F3", "#FF9800", "#9C27B0",
  "#F44336", "#00BCD4", "#795548", "#607D8B",
];

function AvatarBadge({ name, color }) {
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <span className="avatar-badge" style={{ background: color }}>
      {initials}
    </span>
  );
}

const EMPTY_FORM = {
  display_name: "",
  email: "",
  role: "team_member",
  weekly_capacity_hours: 40,
  avatar_color: "#4CAF50",
};

export function S07PeopleScreen({ shellState, updateShellState }) {
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  const people = useRouteData("/api/float/members", { enabled: true });
  const [syncing, setSyncing] = useState(false);

  async function handleSyncFromAsana() {
    setSyncing(true);
    try {
      const token = localStorage.getItem("float_token");
      const result = await requestJson("/api/float/members/sync-from-asana", {
        method: "POST",
        token,
      });
      people.reload();
      const { created, updated, unchanged } = result.synced ?? {};
      setToast({
        message: `Sync complete — ${created} created, ${updated} updated, ${unchanged} unchanged.`,
        tone: "good",
      });
    } catch (err) {
      setToast({ message: err.message || "Sync failed.", tone: "bad" });
    } finally {
      setSyncing(false);
    }
  }

  function handleFieldChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleAddMember(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const token = localStorage.getItem("float_token");
      await requestJson("/api/float/members", {
        method: "POST",
        body: { ...form, weekly_capacity_hours: Number(form.weekly_capacity_hours) },
        token,
      });
      setShowForm(false);
      setForm(EMPTY_FORM);
      people.reload();
      setToast({ message: "Team member added.", tone: "good" });
    } catch (err) {
      setToast({ message: err.message || "Failed to add member.", tone: "bad" });
    } finally {
      setSaving(false);
    }
  }

  function handleOpenDetail(member) {
    updateShellState({ resourceExternalId: member.external_id });
    navigate("/s03");
  }

  return (
    <div className="screen-stack">
      {toast ? <Toast message={toast.message} tone={toast.tone} onDismiss={() => setToast(null)} /> : null}

      <ScreenHeader
        eyebrow="Team"
        title="People"
        description="Manage your team members and their capacity."
        actions={
          <>
            <button className="secondary-button" onClick={people.reload} type="button">Refresh</button>
            <button className="secondary-button" onClick={handleSyncFromAsana} disabled={syncing} type="button">
              {syncing ? "Syncing…" : "Sync from Asana"}
            </button>
            <button className="primary-button" onClick={() => setShowForm((v) => !v)} type="button">
              {showForm ? "Cancel" : "+ Add Member"}
            </button>
          </>
        }
      />

      {showForm ? (
        <SectionCard title="Add Team Member">
          <form className="inline-form" onSubmit={handleAddMember}>
            <div className="inline-form__grid">
              <div className="field-group">
                <label className="field-label">Full name *</label>
                <input className="field-input" name="display_name" value={form.display_name}
                  onChange={handleFieldChange} required placeholder="Ada Lovelace" />
              </div>
              <div className="field-group">
                <label className="field-label">Email</label>
                <input className="field-input" name="email" type="email" value={form.email}
                  onChange={handleFieldChange} placeholder="ada@example.com" />
              </div>
              <div className="field-group">
                <label className="field-label">Role</label>
                <select className="field-input" name="role" value={form.role} onChange={handleFieldChange}>
                  <option value="team_member">Team Member</option>
                  <option value="manager">Manager</option>
                </select>
              </div>
              <div className="field-group">
                <label className="field-label">Weekly capacity (hours)</label>
                <input className="field-input" name="weekly_capacity_hours" type="number"
                  min={1} max={80} value={form.weekly_capacity_hours} onChange={handleFieldChange} />
              </div>
              <div className="field-group">
                <label className="field-label">Avatar colour</label>
                <div className="color-picker-row">
                  {AVATAR_COLORS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      className={`color-swatch${form.avatar_color === c ? " color-swatch--active" : ""}`}
                      style={{ background: c }}
                      onClick={() => setForm((prev) => ({ ...prev, avatar_color: c }))}
                    />
                  ))}
                </div>
              </div>
            </div>
            <div className="command-row">
              <button className="primary-button" type="submit" disabled={saving}>
                {saving ? "Saving…" : "Save Member"}
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}

      {people.loading ? <LoadingSkeleton label="Loading team…" /> : null}
      {people.error ? <ErrorCard error={people.error} onRetry={people.reload} /> : null}

      {people.data ? (
        <SectionCard
          title="Team Members"
          subtitle={`${people.data.members?.length ?? 0} ${people.data.members?.length === 1 ? "member" : "members"}`}
        >
          {people.data.members?.length ? (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Role</th>
                  <th>Weekly capacity</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {people.data.members.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        <AvatarBadge name={m.display_name} color={m.avatar_color} />
                        <div>
                          <strong>{m.display_name}</strong>
                          {m.email ? <div className="supporting-text">{m.email}</div> : null}
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className={`role-badge role-badge--${m.role}`}>
                        {m.role === "manager" ? "Manager" : "Team Member"}
                      </span>
                    </td>
                    <td>{m.weekly_capacity_hours}h / week</td>
                    <td>
                      <button
                        className="ghost-button"
                        onClick={() => handleOpenDetail(m)}
                        type="button"
                      >
                        View detail →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="state-card state-card--muted">
              <strong>No team members yet</strong>
              <p>Click "Add Member" to add your first team member.</p>
            </div>
          )}
        </SectionCard>
      ) : null}
    </div>
  );
}
