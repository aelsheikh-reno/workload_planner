import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

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

function utilizationTone(allocated, capacity) {
  if (!capacity || capacity === 0) return "green";
  const ratio = allocated / capacity;
  if (ratio >= 1.0) return "red";
  if (ratio >= 0.8) return "amber";
  return "green";
}

function utilizationPct(allocated, capacity) {
  if (!capacity || capacity === 0) return "—";
  return Math.round((allocated / capacity) * 100) + "%";
}

function D01Drawer({ shellState, drawerContext, onClose }) {
  const drawer = useRouteData("/api/drawers/d01/task-drilldown", {
    query: {
      planningRunId: shellState.planningRunId,
      sourceSnapshotId: shellState.sourceSnapshotId,
      resourceExternalId: drawerContext.resourceExternalId,
      date: drawerContext.date,
      weekStartDate: drawerContext.weekStartDate,
    },
    enabled: Boolean(drawerContext),
  });

  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="drawer-card" aria-label="Task Drill-Down">
        <div className="drawer-header">
          <div>
            <p className="eyebrow">Task Detail</p>
            <h3>Swimlane Drill-Down</h3>
          </div>
          <button className="secondary-button" onClick={onClose} type="button">
            Close
          </button>
        </div>
        {drawer.loading ? <LoadingSkeleton label="Loading task details…" /> : null}
        {drawer.error ? <ErrorCard error={drawer.error} onRetry={drawer.reload} /> : null}
        {drawer.data ? (
          <div className="screen-stack">
            <ScreenStateCard
              state={drawer.data.viewState.screenState}
              message={messageForScreenState(drawer.data.viewState.screenState)}
              tone={toneForScreenState(drawer.data.viewState.screenState)}
            />
            <SectionCard
              title="Segment Summary"
              subtitle={`${formatValue(drawer.data.segmentContext.resourceExternalId)} · ${formatValue(drawer.data.segmentContext.date)}`}
            >
              <MetricGrid
                items={[
                  {
                    label: "Selected tasks",
                    value: formatValue(drawer.data.segmentContext.selectedTaskCount),
                  },
                  {
                    label: "Total tasks",
                    value: formatValue(drawer.data.segmentSummary?.taskCount ?? 0),
                  },
                  {
                    label: "Ghost load",
                    value: drawer.data.segmentSummary?.ghostVisible ? "Present" : "None",
                  },
                ]}
              />
            </SectionCard>
            <SectionCard title="Tasks">
              <div className="card-grid">
                {drawer.data.tasks.length ? (
                  drawer.data.tasks.map((task) => (
                    <article className="task-card" key={task.taskExternalId}>
                      <strong>{task.taskName}</strong>
                      <small>{task.taskExternalId}</small>
                      <p>Status: {formatValue(task.status)}</p>
                      <p>
                        Movement: {task.movementIndicator?.present ? "⚡ Present" : "None"} · Risk:{" "}
                        {task.riskIndicator?.present ? "⚠ Present" : "None"}
                      </p>
                    </article>
                  ))
                ) : (
                  <div className="summary-card">
                    <span>No tasks</span>
                    <strong>No tasks match this segment.</strong>
                  </div>
                )}
              </div>
            </SectionCard>
          </div>
        ) : null}
      </aside>
    </div>
  );
}

export function S01PortfolioScreen({ shellState, updateShellState }) {
  const navigate = useNavigate();
  const [drawerContext, setDrawerContext] = useState(null);
  const portfolio = useRouteData("/api/screens/s01/portfolio", {
    query: {
      planningRunId: shellState.planningRunId,
      sourceSnapshotId: shellState.sourceSnapshotId,
    },
    enabled: true,
  });

  const metrics = useMemo(() => {
    if (!portfolio.data) {
      return [];
    }
    return [
      {
        label: "Schedule status",
        value: formatValue(portfolio.data.portfolioSummary?.scheduleState),
      },
      {
        label: "Resources",
        value: formatValue(portfolio.data.dailySwimlanes.length),
      },
      {
        label: "Movement indicators",
        value: formatValue(portfolio.data.indicatorSummary?.movementIndicatorTaskCount ?? 0),
      },
      {
        label: "Free capacity days",
        value: formatValue(portfolio.data.indicatorSummary?.freeCapacitySegmentCount ?? 0),
      },
    ];
  }, [portfolio.data]);

  useEffect(() => {
    const queryContext = portfolio.data?.queryContext;
    const portfolioSummary = portfolio.data?.portfolioSummary;
    if (!queryContext && !portfolioSummary) {
      return;
    }

    const nextPatch = {};
    if (queryContext?.planningRunId && queryContext.planningRunId !== shellState.planningRunId) {
      nextPatch.planningRunId = queryContext.planningRunId;
    }
    if (queryContext?.sourceSnapshotId && queryContext.sourceSnapshotId !== shellState.sourceSnapshotId) {
      nextPatch.sourceSnapshotId = queryContext.sourceSnapshotId;
    }
    if (portfolioSummary?.planningContextKey && portfolioSummary.planningContextKey !== shellState.planningContextKey) {
      nextPatch.planningContextKey = portfolioSummary.planningContextKey;
    }

    if (Object.keys(nextPatch).length) {
      updateShellState(nextPatch);
    }
  }, [
    portfolio.data,
    shellState.planningContextKey,
    shellState.planningRunId,
    shellState.sourceSnapshotId,
    updateShellState,
  ]);

  const currentPlanningRunId =
    shellState.planningRunId || portfolio.data?.queryContext?.planningRunId || "";

  function handleWarningReview() {
    updateShellState({
      warningOriginScreenId: "S01",
      warningOriginScopeType: "",
      warningOriginScopeId: "",
      warningOriginScopeExternalId: "",
      warningOriginScopeLabel: "",
    });
    navigate("/s05");
  }

  function handleOpenReview() {
    updateShellState({
      planningRunId: currentPlanningRunId,
      sourceSnapshotId:
        shellState.sourceSnapshotId || portfolio.data?.queryContext?.sourceSnapshotId || "",
      reviewOriginScreenId: "S01",
      reviewOriginScopeType: "portfolio",
      reviewOriginScopeId: "",
      reviewOriginScopeExternalId: "",
      reviewOriginScopeLabel: "Portfolio",
    });
    navigate("/s04");
  }

  return (
    <div className="screen-stack">
      <ScreenHeader
        eyebrow="Portfolio"
        title="Portfolio Overview"
        description="See your team's workload across all resources. Click a resource name to drill into their detail."
        actions={
          <>
            <button className="secondary-button" onClick={portfolio.reload} type="button">
              Refresh
            </button>
            <button className="secondary-button" onClick={handleWarningReview} type="button">
              View Warnings
            </button>
            <button
              className="secondary-button"
              disabled={!currentPlanningRunId}
              onClick={handleOpenReview}
              type="button"
            >
              Review Changes
            </button>
            <button className="primary-button" onClick={() => navigate("/s02")} type="button">
              Setup →
            </button>
          </>
        }
      />

      {portfolio.loading ? <LoadingSkeleton label="Loading portfolio…" /> : null}
      {portfolio.error ? <ErrorCard error={portfolio.error} onRetry={portfolio.reload} /> : null}
      {portfolio.data ? (
        <>
          <ScreenStateCard
            state={portfolio.data.viewState.screenState}
            message={messageForScreenState(portfolio.data.viewState.screenState)}
            tone={toneForScreenState(portfolio.data.viewState.screenState)}
          />
          <MetricGrid items={metrics} />

          <SectionCard
            title="Team Workload"
            subtitle="Each row shows a team member's daily capacity vs. allocated hours. Click a name to see their full detail."
          >
            <div className="card-grid">
              {portfolio.data.dailySwimlanes.length ? (
                portfolio.data.dailySwimlanes.map((lane) => {
                  const tone = utilizationTone(lane.totalAllocatedHours, lane.totalProductiveCapacityHours);
                  const pct = utilizationPct(lane.totalAllocatedHours, lane.totalProductiveCapacityHours);
                  const fillPct = lane.totalProductiveCapacityHours
                    ? Math.min(100, Math.round((lane.totalAllocatedHours / lane.totalProductiveCapacityHours) * 100))
                    : 0;

                  return (
                    <article className="swimlane-card" key={lane.resourceExternalId}>
                      <div className="swimlane-header">
                        <div>
                          <strong>
                            <button
                              className="ghost-button"
                              style={{ padding: 0, fontWeight: 700, fontSize: "1rem", color: "var(--accent-strong)" }}
                              onClick={() => {
                                updateShellState({
                                  resourceExternalId: lane.resourceExternalId,
                                  selectedDate: "",
                                  selectedWeekStartDate: "",
                                });
                                navigate("/s03");
                              }}
                              type="button"
                            >
                              {lane.resourceDisplayName}
                            </button>
                          </strong>
                        </div>
                        <span className={`swimlane-utilization swimlane-utilization--${tone}`}>
                          {pct}
                        </span>
                      </div>

                      <div className="swimlane-bar">
                        <div
                          className={`swimlane-bar__fill swimlane-bar__fill--${tone}`}
                          style={{ width: `${fillPct}%` }}
                        />
                      </div>

                      <MetricGrid
                        items={[
                          {
                            label: "Allocated hrs",
                            value: formatValue(lane.totalAllocatedHours),
                          },
                          {
                            label: "Capacity hrs",
                            value: formatValue(lane.totalProductiveCapacityHours),
                          },
                          {
                            label: "Ghost load",
                            value: lane.ghostSummary?.hasGhostLoad ? "⚠ Yes" : "None",
                          },
                        ]}
                      />
                      <div className="segment-row">
                        {lane.dailySegments.map((segment) => (
                          <div className="summary-card" key={`${lane.resourceExternalId}-${segment.date}`}>
                            <span>{segment.date}</span>
                            <strong>
                              {segment.allocatedHours}/{segment.productiveCapacityHours}h
                            </strong>
                            <small>{formatCountLabel(segment.taskCount, "task")}</small>
                            <div className="segment-actions">
                              <button
                                className="ghost-button"
                                disabled={segment.taskCount === 0 && !segment.hasGhostLoad}
                                onClick={() => {
                                  updateShellState({
                                    resourceExternalId: lane.resourceExternalId,
                                    selectedDate: segment.date,
                                    selectedWeekStartDate: segment.weekStartDate,
                                  });
                                  navigate("/s03");
                                }}
                                type="button"
                              >
                                Resource Detail
                              </button>
                              <button
                                className="ghost-button"
                                disabled={segment.taskCount === 0 && !segment.hasGhostLoad}
                                onClick={() =>
                                  setDrawerContext({
                                    resourceExternalId: lane.resourceExternalId,
                                    date: segment.date,
                                    weekStartDate: segment.weekStartDate,
                                  })
                                }
                                type="button"
                              >
                                Task Detail
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </article>
                  );
                })
              ) : (
                <div className="summary-card">
                  <span>No data available</span>
                  <strong>No analysis results found.</strong>
                  <p className="supporting-text" style={{ marginTop: "0.5rem" }}>
                    Go to <Link to="/s02" style={{ color: "var(--accent)" }}>Setup</Link> to import your plan and run the capacity analysis.
                  </p>
                </div>
              )}
            </div>
          </SectionCard>
        </>
      ) : null}

      {drawerContext ? (
        <D01Drawer
          drawerContext={drawerContext}
          onClose={() => setDrawerContext(null)}
          shellState={shellState}
        />
      ) : null}
    </div>
  );
}
