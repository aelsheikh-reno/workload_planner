import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

const NAV_LINKS = [
  { to: "/",        label: "Projects",  icon: "\u25A6" },
  { to: "/import",  label: "Import",    icon: "\u2191" },
  { to: "/members", label: "Team",      icon: "\u25CE" },
  { to: "/time-off",label: "Time Off",  icon: "\u25F7" },
  { to: "/settings",label: "Settings",  icon: "\u2699" },
];

function StatusPill({ tone, label }) {
  return <span className={`status-pill status-pill--${tone}`}>{label}</span>;
}

export function ShellLayout({ children, health, currentUser, onSignOut }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar_collapsed") === "true");

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar_collapsed", String(next));
      return next;
    });
  }

  function handleSignOut() {
    localStorage.removeItem("float_token");
    localStorage.removeItem("float_user");
    onSignOut?.();
    navigate("/login");
  }

  function isActive(to) {
    if (to === "/") return location.pathname === "/";
    return location.pathname.startsWith(to);
  }

  return (
    <div className={`shell${collapsed ? " shell--collapsed" : ""}`}>
      <aside className="shell__rail">
        {!collapsed && (
          <div className="brand-card">
            <p className="eyebrow">Resource Planner</p>
            <h1>Scheduler</h1>
            <div className="health-row">
              <StatusPill
                tone={
                  health.status === "ok"
                    ? "good"
                    : health.status === "error"
                      ? "bad"
                      : "muted"
                }
                label={
                  health.status === "ok"
                    ? "Connected"
                    : health.status === "error"
                      ? "Disconnected"
                      : "Connecting\u2026"
                }
              />
            </div>
          </div>
        )}

        <nav className="nav-card" aria-label="Main navigation">
          <div className="nav-links">
            {NAV_LINKS.map((link) => (
              <Link
                aria-current={isActive(link.to) ? "page" : undefined}
                className={isActive(link.to) ? "nav-link nav-link--active" : "nav-link"}
                key={link.to}
                to={link.to}
                title={collapsed ? link.label : undefined}
              >
                <span className="nav-link__icon">{link.icon}</span>
                {!collapsed && link.label}
              </Link>
            ))}
          </div>
          <button
            className="ghost-button"
            onClick={toggleCollapsed}
            type="button"
            style={{
              padding: "8px", textAlign: "center",
              fontSize: "1rem", borderTop: "1px solid var(--line)",
              marginTop: "4px", width: "100%",
            }}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? "\u276F" : "\u276E"}
          </button>
        </nav>

        {!collapsed && currentUser ? (
          <div className="user-card">
            <div className="user-card__info">
              <strong>{currentUser.display_name}</strong>
              <span className={`role-badge role-badge--${currentUser.role}`}>
                {currentUser.role === "manager" ? "Manager" : "Member"}
              </span>
            </div>
            <button className="ghost-button" onClick={handleSignOut} type="button">
              Sign out
            </button>
          </div>
        ) : null}
      </aside>

      <main className="shell__main">{children}</main>
    </div>
  );
}
