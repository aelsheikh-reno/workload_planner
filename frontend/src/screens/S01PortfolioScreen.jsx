import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

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
      <aside className="drawer-card" aria-label="D01 drawer">
        <div className="drawer-header">
          <div>
            <p className="eyebrow">D01</p>
            <h3>Swimlane Task Drill-Down Drawer</h3>
          </div>
          <button className="secondary-button" onClick={onClose} type="button">
            Close
          </button>
        </div>
        {drawer.loading ? <LoadingSkeleton label="Loading D01 drill-down." /> : null}
        {drawer.error ? <ErrorCard error={drawer.error} onRetry={drawer.reload} /> : null}
        {drawer.data ? (
          <div className="screen-stack">
            <ScreenStateCard
              state={drawer.data.viewState.screenState}
              message={messageForScreenState(drawer.data.viewState.screenState)}
              tone={toneForScreenState(drawer.data.viewState.screenState)}
            />
            <SectionCard
              title="Segment summary"
              subtitle={`${formatValue(drawer.data.segmentContext.resourceExternalId)} · ${formatValue(drawer.data.segmentContext.date)}`}
            >
              <MetricGrid
                items={[
                  {
                    label: "Selected tasks",
                    value: formatValue(drawer.data.segmentContext.selectedTaskCount),
                  },
                  {
                    label: "Task count",
                    value: formatValue(drawer.data.segmentSummary?.taskCount ?? 0),
                  },
                  {
                    label: "Ghost load",
                    value: drawer.data.segmentSummary?.ghostVisible ? "Visible" : "None",
                  },
                ]}
              />
            </SectionCard>
            <SectionCard title="Task details">
              <div className="card-grid">
                {drawer.data.tasks.length ? (
                  drawer.data.tasks.map((task) => (
                    <article className="task-card" key={task.taskExternalId}>
                      <strong>{task.taskName}</strong>
                      <small>{task.taskExternalId}</small>
                      <p>Status: {formatValue(task.status)}</p>
                      <p>
                        Movement: {task.movementIndicator?.present ? "Present" : "None"} · Risk:{" "}
                        {task.riskIndicator?.present ? "Present" : "None"}
                      </p>
                    </article>
                  ))
                ) : (
                  <div className="summary-card">
                    <span>No matching tasks</span>
                    <strong>Empty drill-down</strong>
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
        label: "Schedule state",
        value: formatValue(portfolio.data.portfolioSummary?.scheduleState),
      },
      {
        label: "Resources",
        value: formatValue(portfolio.data.dailySwimlanes.length),
      },
      {
        label: "Indicator segments",
        value: formatValue(portfolio.data.indicatorSummary?.movementIndicatorTaskCount ?? 0),
      },
      {
        label: "Free capacity segments",
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
    if (
      queryContext?.planningRunId &&
      queryContext.planningRunId !== shellState.planningRunId
    ) {
      nextPatch.planningRunId = queryContext.planningRunId;
    }
    if (
      queryContext?.sourceSnapshotId &&
      queryContext.sourceSnapshotId !== shellState.sourceSnapshotId
    ) {
      nextPatch.sourceSnapshotId = queryContext.sourceSnapshotId;
    }
    if (
      portfolioSummary?.planningContextKey &&
      portfolioSummary.planningContextKey !== shellState.planningContextKey
    ) {
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
        eyebrow="S01"
        title="Portfolio Swimlane Home"
        description="Portfolio visibility and navigation over the current planning run."
        actions={
          <>
            <button className="secondary-button" onClick={portfolio.reload} type="button">
              Refresh portfolio
            </button>
            <button className="secondary-button" onClick={handleWarningReview} type="button">
              Review warnings
            </button>
            <button
              className="secondary-button"
              disabled={!currentPlanningRunId}
              onClick={handleOpenReview}
              type="button"
            >
              Open S04 review
            </button>
            <button className="primary-button" onClick={() => navigate("/s02")} type="button">
              Open S02
            </button>
          </>
        }
      />

      {portfolio.loading ? <LoadingSkeleton label="Loading portfolio swimlanes." /> : null}
      {portfolio.error ? <ErrorCard error={portfolio.error} onRetry={portfolio.reload} /> : null}
      {portfolio.data ? (
        <>
          <ScreenStateCard
            state={portfolio.data.viewState.screenState}
            message={messageForScreenState(portfolio.data.viewState.screenState)}
            tone={toneForScreenState(portfolio.data.viewState.screenState)}
          />
          <MetricGrid items={metrics} />

          <SectionCard title="Portfolio summary">
            <div className="summary-grid">
              <div className="summary-card">
                <span>Planning run</span>
                <strong>{formatValue(portfolio.data.portfolioSummary?.planningRunId)}</strong>
              </div>
              <div className="summary-card">
                <span>Draft schedule</span>
                <strong>{formatValue(portfolio.data.portfolioSummary?.draftScheduleId)}</strong>
              </div>
              <div className="summary-card">
                <span>Comparison context</span>
                <strong>{formatValue(portfolio.data.portfolioSummary?.comparisonContext)}</strong>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Swimlanes" subtitle="Open D01 from a lane segment or navigate into S03 by resource.">
            <div className="card-grid">
              {portfolio.data.dailySwimlanes.length ? (
                portfolio.data.dailySwimlanes.map((lane) => (
                  <article className="swimlane-card" key={lane.resourceExternalId}>
                    <div className="swimlane-header">
                      <div>
                        <strong>{lane.resourceDisplayName}</strong>
                        <p className="supporting-text">{lane.resourceExternalId}</p>
                      </div>
                    </div>
                    <MetricGrid
                      items={[
                        {
                          label: "Allocated hours",
                          value: formatValue(lane.totalAllocatedHours),
                        },
                        {
                          label: "Capacity hours",
                          value: formatValue(lane.totalProductiveCapacityHours),
                        },
                        {
                          label: "Ghost load",
                          value: lane.ghostSummary?.hasGhostLoad ? "Yes" : "No",
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
                              Open S03 from segment
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
                              Open D01
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </article>
                ))
              ) : (
                <div className="summary-card">
                  <span>No swimlanes</span>
                  <strong>Use S02 to attach a planning run first.</strong>
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
