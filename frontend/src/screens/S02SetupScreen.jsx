import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { nowIsoString, requestJson } from "../api";
import {
  ErrorCard,
  LoadingSkeleton,
  MetricGrid,
  ScreenHeader,
  ScreenStateCard,
  SectionCard,
  Toast,
} from "../components/ScreenPrimitives";
import { useRouteData } from "../useRouteData";
import { formatCountLabel, formatValue, messageForScreenState, toneForScreenState } from "../utils";

const PLAIN_READINESS_LABEL = {
  ready: "Ready to plan",
  ready_with_advisories: "Ready (with advisories)",
  blocked: "Blocked — resolve issues first",
  missing: "Not configured",
};

function plainReadiness(state) {
  return PLAIN_READINESS_LABEL[state] || formatValue(state);
}

export function S02SetupScreen({ shellState, updateShellState }) {
  const navigate = useNavigate();
  const [importCommand, setImportCommand] = useState({ loading: false, result: null, error: null });
  const [planningCommand, setPlanningCommand] = useState({ loading: false, result: null, error: null });
  const [statusCommand, setStatusCommand] = useState({ loading: false, result: null, error: null });
  const [toast, setToast] = useState(null);

  const setup = useRouteData("/api/screens/s02/setup", {
    query: {
      planningContextKey: shellState.planningContextKey,
      sourceSnapshotId: shellState.sourceSnapshotId,
    },
    enabled: true,
  });

  useEffect(() => {
    const resolvedSnapshotId = setup.data?.queryContext?.sourceSnapshotId;
    if (resolvedSnapshotId && resolvedSnapshotId !== shellState.sourceSnapshotId) {
      updateShellState({ sourceSnapshotId: resolvedSnapshotId });
    }
  }, [setup.data, shellState.sourceSnapshotId, updateShellState]);

  const screenState = setup.data?.viewState?.screenState || "missing";
  const metrics = useMemo(() => {
    if (!setup.data) {
      return [];
    }
    return [
      {
        label: "Plan source",
        value: plainReadiness(setup.data.sourceReadiness?.state),
      },
      {
        label: "Capacity data",
        value: plainReadiness(setup.data.capacityInputReadiness?.state),
      },
      {
        label: "Can plan now",
        value: setup.data.overallReadiness?.canContinueToPlanning ? "✓ Yes" : "✗ No",
      },
      {
        label: "Advisories",
        value: formatValue(setup.data.overallReadiness?.advisorySignalCount ?? 0),
      },
    ];
  }, [setup.data]);

  async function handleImportSyncStart() {
    setImportCommand({ loading: true, result: null, error: null });
    try {
      const result = await requestJson("/api/screens/s02/import-sync", {
        method: "POST",
        body: {
          rawPayload: { source_system: "asana" },
          requestedBy: shellState.requestedBy,
          requestedAt: nowIsoString(),
        },
      });
      setImportCommand({ loading: false, result, error: null });
      if (result.source_snapshot_id) {
        updateShellState({ sourceSnapshotId: result.source_snapshot_id });
      }
      setup.reload();
      setToast({ message: "Plan imported successfully.", tone: "good" });
    } catch (error) {
      setImportCommand({ loading: false, result: null, error });
    }
  }

  async function handlePlanningRunStart() {
    setPlanningCommand({ loading: true, result: null, error: null });
    try {
      const result = await requestJson("/api/screens/s02/planning-runs", {
        method: "POST",
        body: {
          planningContextKey: shellState.planningContextKey,
          sourceSnapshotId: shellState.sourceSnapshotId,
          requestedBy: shellState.requestedBy,
          requestedAt: nowIsoString(),
        },
      });
      const planningRunId =
        result?.workflow_instance?.planning_engine_run_id ||
        result?.workflow_instance?.planning_run_id ||
        "";
      updateShellState({
        planningWorkflowInstanceId: result.workflow_instance.workflow_instance_id,
        planningRunId,
      });
      setPlanningCommand({ loading: false, result, error: null });
      setToast({ message: "Analysis run started. Refreshing status…", tone: "good" });
    } catch (error) {
      setPlanningCommand({ loading: false, result: null, error });
    }
  }

  async function handlePlanningStatusRefresh() {
    setStatusCommand({ loading: true, result: null, error: null });
    try {
      const result = await requestJson("/api/screens/s02/planning-runs/status", {
        query: shellState.planningWorkflowInstanceId
          ? { workflowInstanceId: shellState.planningWorkflowInstanceId }
          : {
              planningContextKey: shellState.planningContextKey,
              sourceSnapshotId: shellState.sourceSnapshotId,
            },
      });
      updateShellState({
        planningRunId: result.planning_engine_run_id || result.planning_run_id || shellState.planningRunId,
      });
      setStatusCommand({ loading: false, result, error: null });
    } catch (error) {
      setStatusCommand({ loading: false, result: null, error });
    }
  }

  function handleWarningReview() {
    updateShellState({
      warningOriginScreenId: "S02",
      warningOriginScopeType: "",
      warningOriginScopeId: "",
      warningOriginScopeExternalId: "",
      warningOriginScopeLabel: "",
    });
    navigate("/s05");
  }

  const runStatus = statusCommand.result?.status || planningCommand.result?.workflow_instance?.current_status;

  return (
    <div className="screen-stack">
      {toast ? (
        <Toast message={toast.message} tone={toast.tone} onDismiss={() => setToast(null)} />
      ) : null}

      <ScreenHeader
        eyebrow="Setup"
        title="Planning Setup"
        description="Configure your plan source and run the capacity analysis before reviewing results."
        actions={
          <>
            <button className="secondary-button" onClick={setup.reload} type="button">
              Refresh
            </button>
            <button className="secondary-button" onClick={handleWarningReview} type="button">
              View Warnings
            </button>
            <button
              className="primary-button"
              disabled={!setup.data?.overallReadiness?.canContinueToPlanning}
              onClick={() => navigate("/s01")}
              type="button"
            >
              Go to Portfolio →
            </button>
          </>
        }
      />

      {setup.loading ? <LoadingSkeleton label="Loading setup status…" /> : null}
      {setup.error ? <ErrorCard error={setup.error} onRetry={setup.reload} /> : null}
      {setup.data ? (
        <>
          <ScreenStateCard
            state={setup.data.viewState.screenState}
            message={messageForScreenState(setup.data.viewState.screenState)}
            tone={toneForScreenState(setup.data.viewState.screenState)}
          />

          <MetricGrid items={metrics} />

          <div className="split-layout">
            <SectionCard
              title="1. Import Plan"
              subtitle="Load your latest project plan from the source system into the planner."
            >
              <div className="plain-list" style={{ marginBottom: "0.75rem" }}>
                <p>
                  Status:{" "}
                  <strong>
                    {shellState.sourceSnapshotId ? "✓ Plan available" : "No plan imported yet"}
                  </strong>
                </p>
                {setup.data.latestImport?.sourceSystem ? (
                  <p>Source: {formatValue(setup.data.latestImport.sourceSystem)}</p>
                ) : null}
              </div>
              <div className="command-row">
                <button
                  className="primary-button"
                  disabled={importCommand.loading}
                  onClick={handleImportSyncStart}
                  type="button"
                >
                  {importCommand.loading ? "Importing…" : "Import Plan"}
                </button>
              </div>
              {importCommand.error ? <ErrorCard error={importCommand.error} /> : null}
              {setup.data.sourceSetupIssues.length ? (
                <div style={{ marginTop: "0.75rem" }}>
                  <p className="section-label">Issues to resolve</p>
                  <ul className="plain-list">
                    {setup.data.sourceSetupIssues.map((issue) => (
                      <li key={`${issue.code}-${issue.field || "none"}`}>{issue.message}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </SectionCard>

            <SectionCard
              title="2. Run Capacity Analysis"
              subtitle="Analyse your team's capacity against the imported plan to identify overloads and conflicts."
            >
              <div className="plain-list" style={{ marginBottom: "0.75rem" }}>
                <p>
                  Status:{" "}
                  <strong>
                    {runStatus === "succeeded"
                      ? "✓ Analysis complete"
                      : runStatus === "running" || runStatus === "dispatched"
                        ? "⏳ Running…"
                        : shellState.planningRunId
                          ? "✓ Analysis available"
                          : "Not started"}
                  </strong>
                </p>
              </div>
              <div className="command-row">
                <button
                  className="primary-button"
                  disabled={
                    !setup.data?.overallReadiness?.canContinueToPlanning ||
                    !shellState.sourceSnapshotId ||
                    planningCommand.loading
                  }
                  onClick={handlePlanningRunStart}
                  type="button"
                >
                  {planningCommand.loading ? "Starting…" : "Run Analysis"}
                </button>
                <button
                  className="secondary-button"
                  disabled={
                    !shellState.planningWorkflowInstanceId &&
                    (!shellState.planningContextKey || !shellState.sourceSnapshotId)
                  }
                  onClick={handlePlanningStatusRefresh}
                  type="button"
                >
                  {statusCommand.loading ? "Checking…" : "Check Status"}
                </button>
              </div>
              {planningCommand.error ? <ErrorCard error={planningCommand.error} /> : null}
              {statusCommand.error ? <ErrorCard error={statusCommand.error} /> : null}
              {setup.data.capacityInputIssues.length ? (
                <div style={{ marginTop: "0.75rem" }}>
                  <p className="section-label">Capacity issues</p>
                  <ul className="plain-list">
                    {setup.data.capacityInputIssues.map((issue) => (
                      <li key={`${issue.code}-${issue.field || "none"}`}>{issue.message}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </SectionCard>
          </div>

          {(setup.data.noRunnablePlanBlockers.length > 0 || setup.data.advisorySignals.length > 0) ? (
            <SectionCard
              title="Readiness Details"
              subtitle="Issues that may affect whether the analysis can run."
            >
              <div className="summary-grid">
                <div className="summary-card">
                  <span>Blockers</span>
                  <strong>{formatCountLabel(setup.data.noRunnablePlanBlockers.length, "blocker")}</strong>
                </div>
                <div className="summary-card">
                  <span>Advisories</span>
                  <strong>{formatCountLabel(setup.data.advisorySignals.length, "advisory")}</strong>
                </div>
              </div>
            </SectionCard>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
