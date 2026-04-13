import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { nowIsoString, requestJson } from "../api";
import { Toast } from "../components/ScreenPrimitives";
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

export function S03ResourceDetailScreen({ shellState, updateShellState }) {
  const navigate = useNavigate();
  const [refreshResult, setRefreshResult] = useState({ loading: false, result: null, error: null });
  const [toast, setToast] = useState(null);

  const detail = useRouteData("/api/screens/s03/resource-detail", {
    query: {
      planningRunId: shellState.planningRunId,
      planningContextKey: shellState.planningContextKey,
      sourceSnapshotId: shellState.sourceSnapshotId,
      resourceExternalId: shellState.resourceExternalId,
      originScreenId: "S01",
    },
    enabled: true,
  });

  const metrics = useMemo(() => {
    if (!detail.data?.resourceSummary) {
      return [];
    }
    const summary = detail.data.resourceSummary;
    return [
      { label: "Utilization", value: formatValue(summary.utilizationRatio) },
      { label: "Scheduled tasks", value: formatValue(summary.scheduledTaskCount) },
      { label: "Overloaded days", value: formatValue(summary.overloadedDayCount) },
      { label: "Active warnings", value: formatValue(summary.warningSignalCount) },
    ];
  }, [detail.data]);

  async function handleRecommendationRefresh() {
    setRefreshResult({ loading: true, result: null, error: null });
    try {
      const result = await requestJson("/api/screens/s03/recommendation-context/refresh", {
        method: "POST",
        body: {
          planningRunId: shellState.planningRunId,
          resourceExternalId: shellState.resourceExternalId,
        },
      });
      setRefreshResult({ loading: false, result, error: null });
      setToast({ message: "Recommendations refreshed.", tone: "good" });
      detail.reload();
    } catch (error) {
      setRefreshResult({ loading: false, result: null, error });
    }
  }

  function handleOpenWarnings() {
    updateShellState({
      warningOriginScreenId: "S03",
      warningOriginScopeType: detail.data?.navigation?.warningReview?.scope?.scopeType || "resource",
      warningOriginScopeId: detail.data?.navigation?.warningReview?.scope?.scopeId || detail.data?.queryContext?.resourceId || "",
      warningOriginScopeExternalId:
        detail.data?.navigation?.warningReview?.scope?.scopeExternalId ||
        detail.data?.queryContext?.resourceExternalId ||
        "",
      warningOriginScopeLabel:
        detail.data?.navigation?.warningReview?.scope?.scopeLabel ||
        detail.data?.resourceSummary?.resourceDisplayName ||
        "",
    });
    navigate("/s05");
  }

  function handleOpenReview() {
    updateShellState({
      reviewOriginScreenId: "S03",
      reviewOriginScopeType: "resource",
      reviewOriginScopeId: detail.data?.queryContext?.resourceId || "",
      reviewOriginScopeExternalId: detail.data?.queryContext?.resourceExternalId || "",
      reviewOriginScopeLabel: detail.data?.resourceSummary?.resourceDisplayName || "",
    });
    navigate("/s04");
  }

  const resourceName = detail.data?.resourceSummary?.resourceDisplayName;

  return (
    <div className="screen-stack">
      {toast ? (
        <Toast message={toast.message} tone={toast.tone} onDismiss={() => setToast(null)} />
      ) : null}

      <ScreenHeader
        eyebrow="Resource Detail"
        title={resourceName || "Resource Detail"}
        description="Detailed workload, task queue, warnings, and recommendations for this team member."
        actions={
          <>
            <button className="secondary-button" onClick={detail.reload} type="button">
              Refresh
            </button>
            <button className="secondary-button" onClick={() => navigate("/s01")} type="button">
              ← Portfolio
            </button>
          </>
        }
      />

      {detail.loading ? <LoadingSkeleton label="Loading resource detail…" /> : null}
      {detail.error ? <ErrorCard error={detail.error} onRetry={detail.reload} /> : null}

      {!shellState.resourceExternalId && !detail.loading && !detail.error ? (
        <div className="state-card state-card--muted">
          <strong>No resource selected</strong>
          <p>Go to the Portfolio view and click a team member's name to open their detail here.</p>
        </div>
      ) : null}

      {detail.data ? (
        <>
          <ScreenStateCard
            state={detail.data.viewState.screenState}
            message={messageForScreenState(detail.data.viewState.screenState)}
            tone={toneForScreenState(detail.data.viewState.screenState)}
          />
          <MetricGrid items={metrics} />

          <SectionCard
            title={resourceName || "Resource"}
            subtitle={detail.data.resourceSummary?.resourceExternalId || ""}
            actions={
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button
                  className="secondary-button"
                  disabled={!shellState.planningRunId || !shellState.resourceExternalId || refreshResult.loading}
                  onClick={handleRecommendationRefresh}
                  type="button"
                >
                  {refreshResult.loading ? "Refreshing…" : "Refresh Recommendations"}
                </button>
                <button className="secondary-button" onClick={handleOpenWarnings} type="button">
                  View Warnings
                </button>
                <button className="secondary-button" onClick={handleOpenReview} type="button">
                  Review Changes
                </button>
              </div>
            }
          >
            {refreshResult.error ? <ErrorCard error={refreshResult.error} /> : null}
            <div className="summary-grid">
              <div className="summary-card">
                <span>Allocated hours</span>
                <strong>{formatValue(detail.data.resourceSummary?.totalAllocatedHours)}</strong>
              </div>
              <div className="summary-card">
                <span>Capacity hours</span>
                <strong>{formatValue(detail.data.resourceSummary?.totalProductiveCapacityHours)}</strong>
              </div>
              <div className="summary-card">
                <span>Risk indicators</span>
                <strong>{formatValue(detail.data.resourceSummary?.riskIndicatorCount)}</strong>
              </div>
              <div className="summary-card">
                <span>Selected date</span>
                <strong>
                  {formatValue(shellState.selectedDate || shellState.selectedWeekStartDate)}
                </strong>
              </div>
            </div>
          </SectionCard>

          <div className="split-layout">
            <SectionCard title="Daily Workload Timeline">
              <div className="timeline-table">
                {detail.data.workloadTimeline.length ? (
                  detail.data.workloadTimeline.map((segment) => (
                    <div className="timeline-row" key={segment.date}>
                      <strong>{segment.date}</strong>
                      <small>
                        {segment.allocatedHours}/{segment.productiveCapacityHours}h · {formatCountLabel(segment.taskCount, "task")}
                      </small>
                    </div>
                  ))
                ) : (
                  <div className="summary-card">
                    <span>No timeline data</span>
                    <strong>No workload data available for this resource.</strong>
                  </div>
                )}
              </div>
            </SectionCard>

            <SectionCard title="Assigned Tasks">
              <div className="queue-list">
                {detail.data.assignedWorkQueue.length ? (
                  detail.data.assignedWorkQueue.map((item) => (
                    <article className="queue-card" key={item.taskExternalId}>
                      <strong>{item.taskName}</strong>
                      <small>{item.status}</small>
                      <p>
                        {formatValue(item.scheduledStartDate)} → {formatValue(item.scheduledEndDate)}
                      </p>
                    </article>
                  ))
                ) : (
                  <div className="summary-card">
                    <span>No assigned tasks</span>
                    <strong>No tasks are assigned to this resource.</strong>
                  </div>
                )}
              </div>
            </SectionCard>
          </div>

          <div className="split-layout">
            <SectionCard
              title="Recommendations"
              subtitle={`${formatCountLabel(detail.data.recommendationContext?.totalRecommendationCount ?? 0, "suggestion")}`}
            >
              <div className="card-grid">
                {detail.data.recommendationContext?.items?.length ? (
                  detail.data.recommendationContext.items.map((item) => (
                    <article className="recommendation-card" key={item.recommendationId || item.recommendation_id}>
                      <strong>{item.actionFamily || item.action_family || "Recommendation"}</strong>
                      <p className="supporting-text">
                        {item.effectSummary || item.effect_summary || "No summary available."}
                      </p>
                    </article>
                  ))
                ) : (
                  <div className="summary-card">
                    <span>No recommendations</span>
                    <strong>No actionable suggestions at this time.</strong>
                  </div>
                )}
              </div>
            </SectionCard>

            <SectionCard
              title="Active Warnings"
              subtitle={`${formatCountLabel(detail.data.warningTrustContext?.activeSignalCount ?? 0, "warning")}`}
            >
              <ul className="warning-list">
                {detail.data.warningTrustContext?.items?.length ? (
                  detail.data.warningTrustContext.items.map((item) => (
                    <li key={item.signalId}>
                      {item.headline || item.message || item.signalId}
                    </li>
                  ))
                ) : (
                  <li>No active warnings for this resource.</li>
                )}
              </ul>
            </SectionCard>
          </div>
        </>
      ) : null}
    </div>
  );
}
