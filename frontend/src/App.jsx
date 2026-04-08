import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { requestJson } from "./api";
import { ShellLayout } from "./components/ShellLayout";
import { S01PortfolioScreen } from "./screens/S01PortfolioScreen";
import { S02SetupScreen } from "./screens/S02SetupScreen";
import { S03ResourceDetailScreen } from "./screens/S03ResourceDetailScreen";
import { S04DeltaReviewScreen } from "./screens/S04DeltaReviewScreen";
import { S05WarningsScreen } from "./screens/S05WarningsScreen";
import { useShellState } from "./shellState";

export default function App() {
  const { shellState, updateShellState, resetShellState } = useShellState();
  const [health, setHealth] = useState({ status: "loading" });

  useEffect(() => {
    let active = true;
    requestJson("/health")
      .then(() => {
        if (active) {
          setHealth({ status: "ok" });
        }
      })
      .catch(() => {
        if (active) {
          setHealth({ status: "error" });
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const sharedProps = {
    shellState,
    updateShellState,
  };

  return (
    <ShellLayout
      health={health}
      shellState={shellState}
      resetShellState={resetShellState}
    >
      <Routes>
        <Route path="/" element={<Navigate replace to="/s01" />} />
        <Route path="/s01" element={<S01PortfolioScreen {...sharedProps} />} />
        <Route path="/s02" element={<S02SetupScreen {...sharedProps} />} />
        <Route path="/s03" element={<S03ResourceDetailScreen {...sharedProps} />} />
        <Route path="/s04" element={<S04DeltaReviewScreen {...sharedProps} />} />
        <Route path="/s05" element={<S05WarningsScreen {...sharedProps} />} />
      </Routes>
    </ShellLayout>
  );
}
