import { useEffect, useState } from "react";

const STORAGE_KEY = "capacity-aware-execution-planner.frontend-shell-state";

export const DEFAULT_SHELL_STATE = {
  requestedBy: "planner@example.com",
  planningContextKey: "context::frontend-shell",
  sourceSnapshotId: "",
  planningRunId: "",
  planningWorkflowInstanceId: "",
  reviewContextId: "",
  approvedPlanId: "",
  resourceExternalId: "",
  activationId: "",
  selectedDate: "",
  selectedWeekStartDate: "",
  reviewOriginScreenId: "",
  reviewOriginScopeType: "",
  reviewOriginScopeId: "",
  reviewOriginScopeExternalId: "",
  reviewOriginScopeLabel: "",
  warningOriginScreenId: "",
  warningOriginScopeType: "",
  warningOriginScopeId: "",
  warningOriginScopeExternalId: "",
  warningOriginScopeLabel: "",
};

function normalizeState(state) {
  return {
    ...DEFAULT_SHELL_STATE,
    ...Object.fromEntries(
      Object.entries(state || {}).map(([key, value]) => [key, value ?? ""]),
    ),
  };
}

export function useShellState() {
  const [state, setState] = useState(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return DEFAULT_SHELL_STATE;
      }
      return normalizeState(JSON.parse(raw));
    } catch (_error) {
      return DEFAULT_SHELL_STATE;
    }
  });

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  function updateShellState(patch) {
    setState((current) =>
      normalizeState({
        ...current,
        ...(typeof patch === "function" ? patch(current) : patch),
      }),
    );
  }

  function resetShellState() {
    setState(DEFAULT_SHELL_STATE);
  }

  return {
    shellState: state,
    updateShellState,
    resetShellState,
  };
}
