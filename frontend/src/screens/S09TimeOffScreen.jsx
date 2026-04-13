import { useState } from "react";

import { requestJson } from "../api";
import { ErrorCard, LoadingSkeleton, ScreenHeader, SectionCard, Toast } from "../components/ScreenPrimitives";
import { useRouteData } from "../useRouteData";
import { formatCountLabel, formatValue } from "../utils";

const LEAVE_TYPES = [
  { value: "annual", label: "Annual Leave" },
  { value: "sick", label: "Sick Leave" },
  { value: "public_holiday", label: "Public Holiday" },
  { value: "custom", label: "Custom / Other" },
];

const LEAVE_TYPE_LABELS = Object.fromEntries(LEAVE_TYPES.map(({ value, label }) => [value, label]));

const EMPTY_FORM = {
  member_id: "",
  leave_type: "annual",
  start_date: "",
  end_date: "",
  note: "",
};

export function S09TimeOffScreen({ shellState }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const timeOff = useRouteData("/api/float/time-off", { enabled: true });
  const members = useRouteData("/api/float/members", { enabled: true });

  function handleFieldChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleAddTimeOff(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const token = localStorage.getItem("float_token");
      await requestJson("/api/float/time-off", {
        method: "POST",
        body: { ...form, member_id: Number(form.member_id) },
        token,
      });
      setShowForm(false);
      setForm(EMPTY_FORM);
      timeOff.reload();
      setToast({ message: "Time off added.", tone: "good" });
    } catch (err) {
      setToast({ message: err.message || "Failed to add time off.", tone: "bad" });
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    setDeletingId(id);
    try {
      const token = localStorage.getItem("float_token");
      await requestJson(`/api/float/time-off/${id}`, { method: "DELETE", token });
      timeOff.reload();
      setToast({ message: "Time off removed.", tone: "good" });
    } catch (err) {
      setToast({ message: err.message || "Failed to remove.", tone: "bad" });
    } finally {
      setDeletingId(null);
    }
  }

  // Build per-member summary
  const memberMap = (members.data?.members || []).reduce((acc, m) => {
    acc[m.id] = m;
    return acc;
  }, {});

  const perMemberEntries = (timeOff.data?.time_offs || []).reduce((acc, entry) => {
    (acc[entry.member_id] = acc[entry.member_id] || []).push(entry);
    return acc;
  }, {});

  function daysCount(entry) {
    if (!entry.start_date || !entry.end_date) return 0;
    const s = new Date(entry.start_date);
    const e = new Date(entry.end_date);
    return Math.round((e - s) / 86400000) + 1;
  }

  return (
    <div className="screen-stack">
      {toast ? <Toast message={toast.message} tone={toast.tone} onDismiss={() => setToast(null)} /> : null}

      <ScreenHeader
        eyebrow="Availability"
        title="Time Off"
        description="Track team leave, public holidays, and scheduled time away."
        actions={
          <>
            <button className="secondary-button" onClick={timeOff.reload} type="button">Refresh</button>
            <button className="primary-button" onClick={() => setShowForm((v) => !v)} type="button">
              {showForm ? "Cancel" : "+ Add Time Off"}
            </button>
          </>
        }
      />

      {showForm ? (
        <SectionCard title="Add Time Off">
          <form className="inline-form" onSubmit={handleAddTimeOff}>
            <div className="inline-form__grid">
              <div className="field-group">
                <label className="field-label">Team member *</label>
                <select className="field-input" name="member_id" value={form.member_id}
                  onChange={handleFieldChange} required>
                  <option value="">Select a team member…</option>
                  {(members.data?.members || []).map((m) => (
                    <option key={m.id} value={m.id}>{m.display_name}</option>
                  ))}
                </select>
              </div>
              <div className="field-group">
                <label className="field-label">Leave type</label>
                <select className="field-input" name="leave_type" value={form.leave_type}
                  onChange={handleFieldChange}>
                  {LEAVE_TYPES.map(({ value, label }) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <div className="field-group">
                <label className="field-label">Start date *</label>
                <input className="field-input" name="start_date" type="date"
                  value={form.start_date} onChange={handleFieldChange} required />
              </div>
              <div className="field-group">
                <label className="field-label">End date *</label>
                <input className="field-input" name="end_date" type="date"
                  value={form.end_date} onChange={handleFieldChange} required />
              </div>
              <div className="field-group" style={{ gridColumn: "1 / -1" }}>
                <label className="field-label">Note (optional)</label>
                <input className="field-input" name="note" value={form.note}
                  onChange={handleFieldChange} placeholder="e.g. Spring break" />
              </div>
            </div>
            <div className="command-row">
              <button className="primary-button" type="submit" disabled={saving}>
                {saving ? "Saving…" : "Add Time Off"}
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}

      {timeOff.loading || members.loading ? <LoadingSkeleton label="Loading time off…" /> : null}
      {timeOff.error ? <ErrorCard error={timeOff.error} onRetry={timeOff.reload} /> : null}

      {timeOff.data ? (
        Object.keys(perMemberEntries).length ? (
          Object.entries(perMemberEntries).map(([memberId, entries]) => {
            const member = memberMap[memberId] || { display_name: "Unknown" };
            const totalDays = entries.reduce((sum, e) => sum + daysCount(e), 0);
            return (
              <SectionCard
                key={memberId}
                title={member.display_name}
                subtitle={`${formatCountLabel(entries.length, "entry")} · ${totalDays} days total`}
              >
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Start</th>
                      <th>End</th>
                      <th>Days</th>
                      <th>Note</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map((entry) => (
                      <tr key={entry.id}>
                        <td>
                          <span className={`leave-badge leave-badge--${entry.leave_type}`}>
                            {LEAVE_TYPE_LABELS[entry.leave_type] || entry.leave_type}
                          </span>
                        </td>
                        <td>{formatValue(entry.start_date)}</td>
                        <td>{formatValue(entry.end_date)}</td>
                        <td>{daysCount(entry)}</td>
                        <td className="supporting-text">{entry.note || "—"}</td>
                        <td>
                          <button
                            className="ghost-button ghost-button--danger"
                            onClick={() => handleDelete(entry.id)}
                            disabled={deletingId === entry.id}
                            type="button"
                          >
                            {deletingId === entry.id ? "Removing…" : "Remove"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </SectionCard>
            );
          })
        ) : (
          <div className="state-card state-card--muted">
            <strong>No time off recorded</strong>
            <p>Click "Add Time Off" to record leave for a team member.</p>
          </div>
        )
      ) : null}
    </div>
  );
}
