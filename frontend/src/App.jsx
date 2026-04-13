import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { requestJson } from "./api";
import { ShellLayout } from "./components/ShellLayout";
import { S10LoginScreen } from "./screens/S10LoginScreen";
import { DashboardScreen } from "./screens/DashboardScreen";
import { ProjectScreen } from "./screens/ProjectScreen";
import { ImportScreen } from "./screens/ImportScreen";
import { MembersScreen } from "./screens/MembersScreen";
import { TimeOffScreen } from "./screens/TimeOffScreen";
import { SettingsScreen } from "./screens/SettingsScreen";

function RequireAuth({ children }) {
  const location = useLocation();
  const token = localStorage.getItem("float_token");
  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return children;
}

export default function App() {
  const [health, setHealth] = useState({ status: "loading" });
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const stored = localStorage.getItem("float_user");
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    let active = true;
    requestJson("/health")
      .then(() => { if (active) setHealth({ status: "ok" }); })
      .catch(() => { if (active) setHealth({ status: "error" }); });
    return () => { active = false; };
  }, []);

  const location = useLocation();
  if (location.pathname === "/login") {
    return (
      <Routes>
        <Route
          path="/login"
          element={<S10LoginScreen onLogin={(user) => setCurrentUser(user)} />}
        />
      </Routes>
    );
  }

  return (
    <ShellLayout health={health} currentUser={currentUser} onSignOut={() => setCurrentUser(null)}>
      <Routes>
        <Route path="/" element={<RequireAuth><DashboardScreen /></RequireAuth>} />
        <Route path="/projects/:id" element={<RequireAuth><ProjectScreen /></RequireAuth>} />
        <Route path="/import" element={<RequireAuth><ImportScreen /></RequireAuth>} />
        <Route path="/members" element={<RequireAuth><MembersScreen /></RequireAuth>} />
        <Route path="/time-off" element={<RequireAuth><TimeOffScreen /></RequireAuth>} />
        <Route path="/settings" element={<RequireAuth><SettingsScreen /></RequireAuth>} />
        {/* Redirect old screen paths */}
        <Route path="/s06" element={<Navigate replace to="/" />} />
        <Route path="/s07" element={<Navigate replace to="/members" />} />
        <Route path="/s08" element={<Navigate replace to="/" />} />
        <Route path="/s09" element={<Navigate replace to="/time-off" />} />
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
    </ShellLayout>
  );
}
