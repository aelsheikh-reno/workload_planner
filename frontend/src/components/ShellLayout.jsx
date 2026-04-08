import { useLocation } from "react-router-dom";

const SCREEN_LINKS = [
  { to: "/s01", label: "S01 Portfolio" },
  { to: "/s02", label: "S02 Planning Setup" },
  { to: "/s03", label: "S03 Resource Detail" },
  { to: "/s04", label: "S04 Delta Review" },
  { to: "/s05", label: "S05 Warnings" },
];

function StatusPill({ tone, label }) {
  return <span className={`status-pill status-pill--${tone}`}>{label}</span>;
}

export function ShellLayout({
  children,
  health,
  shellState,
  resetShellState,
}) {
  const location = useLocation();

  return (
    <div className="shell">
      <aside className="shell__rail">
        <div className="brand-card">
          <p className="eyebrow">Capacity-Aware Execution Planner</p>
          <h1>MVP Shell</h1>
          <p className="supporting-text">
            Real screen routing over the live API Gateway / BFF transport.
          </p>
          <div className="health-row">
            <StatusPill
              tone={health.status === "ok" ? "good" : health.status === "error" ? "bad" : "muted"}
              label={
                health.status === "ok"
                  ? "BFF reachable"
                  : health.status === "error"
                    ? "BFF unavailable"
                    : "Checking BFF"
              }
            />
          </div>
        </div>

        <nav className="nav-card" aria-label="Approved screens">
          <p className="section-label">Screens</p>
          <div className="nav-links">
            {SCREEN_LINKS.map((link) => (
              <div
                aria-current={location.pathname === link.to ? "page" : undefined}
                className={location.pathname === link.to ? "nav-link nav-link--active" : "nav-link"}
                key={link.to}
              >
                {link.label}
              </div>
            ))}
          </div>
        </nav>
      </aside>

      <main className="shell__main">{children}</main>

      <aside className="shell__context">
        <div className="context-card">
          <div className="context-card__header">
            <div>
              <p className="section-label">Shared context</p>
              <h2>Active planning context</h2>
            </div>
            <button className="secondary-button" onClick={resetShellState} type="button">
              Reset
            </button>
          </div>

          <div className="context-summary">
            <p className="section-label">Context carried between screens</p>
            <ul>
              <li>
                Source readiness: {shellState.sourceSnapshotId ? "saved snapshot attached" : "no snapshot attached"}
              </li>
              <li>
                Planning run: {shellState.planningRunId ? "draft planning run attached" : "no planning run attached"}
              </li>
              <li>
                Resource focus: {shellState.resourceExternalId || "none selected"}
              </li>
              <li>
                Selected window: {shellState.selectedDate || shellState.selectedWeekStartDate || "not set"}
              </li>
              <li>
                Review context: {shellState.reviewContextId ? "review context attached" : "no review context attached"}
              </li>
              <li>
                Review origin: {shellState.reviewOriginScreenId || "not set"}
              </li>
              <li>
                Warning origin: {shellState.warningOriginScreenId || "not set"}
              </li>
            </ul>
            <p className="supporting-text">
              Use the screen-owned actions to advance setup, diagnosis, review, and warning navigation. The shell only preserves the active context.
            </p>
          </div>
        </div>
      </aside>
    </div>
  );
}
