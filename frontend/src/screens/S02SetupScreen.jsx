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
} from "../components/ScreenPrimitives";
import { useRouteData } from "../useRouteData";
import { formatCountLabel, formatValue, messageForScreenState, toneForScreenState } from "../utils";

const INITIAL_IMPORT_PAYLOAD = '{\n  "source_system": "asana"\n}';

export function S02SetupScreen({ shellState, updateShellState }) {
  const navigate = useNavigate();
  const [importDraft, setImportDraft] = useState(INITIAL_IMPORT_PAYLOAD);
  const [snapshotDraft, setSnapshotDraft] = useState(shellState.sourceSnapshotId);
  const [importCommand, setImportCommand] = useState({ loading: false, result: null, error: null });
  const [planningCommand, setPlanningCommand] = useState({ loading: false, result: null, error: null });
  const [statusCommand, setStatusCommand] = useState({ loading: false, result: null, error: null });

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
      setSnapshotDraft(resolvedSnapshotId);
    }
  }, [setup.data, shellState.sourceSnapshotId, updateShellState]);

  useEffect(() => {
    setSnapshotDraft(shellState.sourceSnapshotId);
  }, [shellState.sourceSnapshotId]);

  const screenState = setup.data?.viewState?.screenState || "missing";
  const metrics = useMemo(() => {
    if (!setup.data) {
      return [];
    }
    return [
      {
        label: "Source readiness",
        value: formatValue(setup.data.sourceReadiness?.state),
      },
      {
        label: "Capacity inputs",
        value: formatValue(setup.data.capacityInputReadiness?.state),
      },
      {
        label: "Runnable",
        value: setup.data.overallReadiness?.canContinueToPlanning ? "Yes" : "No",
      },
      {
        label: "Advisories",
        value: formatValue(setup.data.overallReadiness?.advisorySignalCount ?? 0),
      },
    ];
  }, [setup.data]);

  async function handleImportSyncStart(event) {
    event.preventDefault();
    let rawPayload;
    try {
      rawPayload = JSON.parse(importDraft);
    } catch (_error) {
      setImportCommand({
        loading: false,
        result: null,
        error: { code: "invalid_json", message: "Raw payload must be valid JSON." },
      });
      return;
    }

    setImportCommand({ loading: true, result: null, error: null });
    try {
      const result = await requestJson("/api/screens/s02/import-sync", {
        method: "POST",
        body: {
          rawPayload,
          requestedBy: shellState.requestedBy,
          requestedAt: nowIsoString(),
        },
      });
      setImportCommand({ loading: false, result, error: null });
      if (result.source_snapshot_id) {
        updateShellState({ sourceSnapshotId: result.source_snapshot_id });
      }
      setup.reload();
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

  return (
    <div className="screen-stack">
      <ScreenHeader
        eyebrow="S02"
        title="Planning Setup"
        description="Status-first readiness, source intake admission, and planning-run admission through the real BFF transport."
        actions={
          <>
            <button className="secondary-button" onClick={setup.reload} type="button">
              Refresh setup
            </button>
            <button className="secondary-button" onClick={handleWarningReview} type="button">
              Review warnings
            </button>
            <button
              className="primary-button"
              disabled={!setup.data?.overallReadiness?.canContinueToPlanning}
              onClick={() => navigate("/s01")}
              type="button"
            >
              Continue to S01
            </button>
          </>
        }
      />

      {setup.loading ? <LoadingSkeleton label="Loading S02 setup readiness." /> : null}
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
              title="Source intake"
              subtitle="Keep setup status first, with bounded intake actions available only when needed."
            >
              <label className="field">
                <span>Saved source snapshot ID</span>
                <input
                  aria-label="Saved source snapshot ID"
                  value={snapshotDraft}
                  onChange={(event) => setSnapshotDraft(event.target.value)}
                  placeholder="Attach an existing normalized snapshot when one is already known"
                />
              </label>
              <div className="command-row">
                <button
                  className="secondary-button"
                  onClick={() => updateShellState({ sourceSnapshotId: snapshotDraft.trim() })}
                  type="button"
                >
                  Use saved snapshot
                </button>
              </div>
              <details className="advanced-toggle">
                <summary>Start import / sync from a source payload</summary>
                <form onSubmit={handleImportSyncStart}>
                  <label className="field">
                    <span>Source plan payload</span>
                    <textarea
                      aria-label="Source plan payload"
                      value={importDraft}
                      onChange={(event) => setImportDraft(event.target.value)}
                    />
                  </label>
                  <div className="command-row">
                    <button className="primary-button" disabled={importCommand.loading} type="submit">
                      {importCommand.loading ? "Starting import…" : "Start import / sync"}
                    </button>
                  </div>
                </form>
              </details>
              {importCommand.error ? <ErrorCard error={importCommand.error} /> : null}
              {importCommand.result ? (
                <div className="command-result">
                  <strong>Import/sync admitted</strong>
                  <p>
                    Workflow status: {formatValue(importCommand.result.workflow_instance?.current_status)}
                  </p>
                  <p>
                    Snapshot: {formatValue(importCommand.result.source_snapshot_id)}. The current MVP transport exposes admission and handoff; if snapshot completion is not yet available, continue once a saved normalized snapshot becomes available.
                  </p>
                </div>
              ) : null}
            </SectionCard>

            <SectionCard
              title="Planning run"
              subtitle="Run planning when the current setup state is runnable."
            >
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
                  {planningCommand.loading ? "Starting run…" : "Start planning run"}
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
                  {statusCommand.loading ? "Refreshing status…" : "Refresh run status"}
                </button>
              </div>
              <div className="plain-list">
                <p>Current source snapshot: {formatValue(shellState.sourceSnapshotId)}</p>
                <p>Current planning run: {formatValue(shellState.planningRunId)}</p>
              </div>
              {planningCommand.error ? <ErrorCard error={planningCommand.error} /> : null}
              {planningCommand.result ? (
                <div className="command-result">
                  <strong>Planning run admitted</strong>
                  <p>
                    Workflow: {formatValue(planningCommand.result.workflow_instance?.workflow_instance_id)}
                  </p>
                  <p>
                    Planning run ID:{" "}
                    {formatValue(
                      planningCommand.result.workflow_instance?.planning_engine_run_id ||
                        planningCommand.result.workflow_instance?.planning_run_id,
                    )}
                  </p>
                </div>
              ) : null}
              {statusCommand.error ? <ErrorCard error={statusCommand.error} /> : null}
              {statusCommand.result ? (
                <div className="command-result">
                  <strong>Latest planning run status</strong>
                  <p>Status: {formatValue(statusCommand.result.status)}</p>
                  <p>
                    Planning run ID:{" "}
                    {formatValue(
                      statusCommand.result.planning_engine_run_id ||
                        statusCommand.result.planning_run_id,
                    )}
                  </p>
                </div>
              ) : null}
            </SectionCard>
          </div>

          <SectionCard
            title="Readiness detail"
            subtitle="Current blockers, advisories, and import metadata from the BFF-composed setup view."
          >
            <div className="summary-grid">
              <div className="summary-card">
                <span>Latest import</span>
                <strong>{formatValue(setup.data.latestImport?.snapshotId)}</strong>
                <small>{formatValue(setup.data.latestImport?.sourceSystem)}</small>
              </div>
              <div className="summary-card">
                <span>No-runnable blockers</span>
                <strong>{formatCountLabel(setup.data.noRunnablePlanBlockers.length, "blocker")}</strong>
              </div>
              <div className="summary-card">
                <span>Advisory signals</span>
                <strong>{formatCountLabel(setup.data.advisorySignals.length, "signal")}</strong>
              </div>
            </div>

            <div className="card-grid">
              <div className="summary-card">
                <span>Source setup issues</span>
                <ul className="plain-list">
                  {setup.data.sourceSetupIssues.length ? (
                    setup.data.sourceSetupIssues.map((issue) => (
                      <li key={`${issue.code}-${issue.field || "none"}`}>{issue.message}</li>
                    ))
                  ) : (
                    <li>No source setup issues in the current scope.</li>
                  )}
                </ul>
              </div>
              <div className="summary-card">
                <span>Capacity input issues</span>
                <ul className="plain-list">
                  {setup.data.capacityInputIssues.length ? (
                    setup.data.capacityInputIssues.map((issue) => (
                      <li key={`${issue.code}-${issue.field || "none"}`}>{issue.message}</li>
                    ))
                  ) : (
                    <li>No capacity input issues in the current scope.</li>
                  )}
                </ul>
              </div>
            </div>
          </SectionCard>
        </>
      ) : null}
    </div>
  );
}
