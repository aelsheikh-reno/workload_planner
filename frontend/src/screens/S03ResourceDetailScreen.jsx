import { useMemo, useState } from "react";
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

export function S03ResourceDetailScreen({ shellState, updateShellState }) {
  const navigate = useNavigate();
  const [refreshResult, setRefreshResult] = useState({ loading: false, result: null, error: null });
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
      { label: "Utilization ratio", value: formatValue(summary.utilizationRatio) },
      { label: "Scheduled tasks", value: formatValue(summary.scheduledTaskCount) },
      { label: "Overloaded days", value: formatValue(summary.overloadedDayCount) },
      { label: "Warning signals", value: formatValue(summary.warningSignalCount) },
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

  return (
    <div className="screen-stack">
      <ScreenHeader
        eyebrow="S03"
        title="Resource Detail"
        description="Single-resource diagnosis with timeline, queue, warnings, and recommendation consumption."
        actions={
          <>
            <button className="secondary-button" onClick={detail.reload} type="button">
              Refresh detail
            </button>
            <button className="secondary-button" onClick={() => navigate("/s01")} type="button">
              Back to S01
            </button>
          </>
        }
      />

      {detail.loading ? <LoadingSkeleton label="Loading resource detail." /> : null}
      {detail.error ? <ErrorCard error={detail.error} onRetry={detail.reload} /> : null}
      {detail.data ? (
        <>
          <ScreenStateCard
            state={detail.data.viewState.screenState}
            message={messageForScreenState(detail.data.viewState.screenState)}
            tone={toneForScreenState(detail.data.viewState.screenState)}
          />
          <MetricGrid items={metrics} />

          <SectionCard
            title={detail.data.resourceSummary?.resourceDisplayName || "No resource selected"}
            subtitle={detail.data.resourceSummary?.resourceExternalId || "Attach a resource external ID in the shared shell state or via S01."}
            actions={
              <button
                className="secondary-button"
                disabled={!shellState.planningRunId || !shellState.resourceExternalId || refreshResult.loading}
                onClick={handleRecommendationRefresh}
                type="button"
              >
                {refreshResult.loading ? "Refreshing recommendations…" : "Refresh recommendation context"}
              </button>
            }
          >
            {refreshResult.error ? <ErrorCard error={refreshResult.error} /> : null}
            {refreshResult.result ? (
              <div className="command-result">
                <strong>Recommendation context refreshed</strong>
                <p>Context ID: {formatValue(refreshResult.result.context_id || refreshResult.result.contextId)}</p>
              </div>
            ) : null}
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
                <span>Selected swimlane window</span>
                <strong>
                  {formatValue(
                    shellState.selectedDate || shellState.selectedWeekStartDate,
                  )}
                </strong>
              </div>
            </div>
          </SectionCard>

          <div className="split-layout">
            <SectionCard title="Workload timeline">
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
                    <span>No timeline rows</span>
                    <strong>The current resource context does not expose workload rows.</strong>
                  </div>
                )}
              </div>
            </SectionCard>

            <SectionCard title="Assigned work / queue">
              <div className="queue-list">
                {detail.data.assignedWorkQueue.length ? (
                  detail.data.assignedWorkQueue.map((item) => (
                    <article className="queue-card" key={item.taskExternalId}>
                      <strong>{item.taskName}</strong>
                      <small>{item.status}</small>
                      <p>
                        Scheduled: {formatValue(item.scheduledStartDate)} → {formatValue(item.scheduledEndDate)}
                      </p>
                    </article>
                  ))
                ) : (
                  <div className="summary-card">
                    <span>No queued work</span>
                    <strong>No assigned work is visible for the current resource.</strong>
                  </div>
                )}
              </div>
            </SectionCard>
          </div>

          <div className="split-layout">
            <SectionCard
              title="Recommendation context"
              subtitle={`${formatValue(detail.data.recommendationContext?.state)} · ${formatCountLabel(detail.data.recommendationContext?.totalRecommendationCount ?? 0, "candidate")}`}
              actions={
                <button className="secondary-button" onClick={handleOpenReview} type="button">
                  Go to S04
                </button>
              }
            >
              <div className="card-grid">
                {detail.data.recommendationContext?.items?.length ? (
                  detail.data.recommendationContext.items.map((item) => (
                    <article className="recommendation-card" key={item.recommendationId || item.recommendation_id}>
                      <strong>{item.actionFamily || item.action_family || "Recommendation candidate"}</strong>
                      <p className="supporting-text">
                        {item.effectSummary || item.effect_summary || "No effect summary published."}
                      </p>
                    </article>
                  ))
                ) : (
                  <div className="summary-card">
                    <span>No recommendation items</span>
                    <strong>The current published context has no actionable candidates.</strong>
                  </div>
                )}
              </div>
            </SectionCard>

            <SectionCard
              title="Warning / trust context"
              subtitle={`${formatCountLabel(detail.data.warningTrustContext?.activeSignalCount ?? 0, "signal")}`}
              actions={
                <button className="secondary-button" onClick={handleOpenWarnings} type="button">
                  Open S05
                </button>
              }
            >
              <ul className="warning-list">
                {detail.data.warningTrustContext?.items?.length ? (
                  detail.data.warningTrustContext.items.map((item) => (
                    <li key={item.signalId}>
                      {item.headline || item.message || item.signalId}
                    </li>
                  ))
                ) : (
                  <li>No warning or trust-limited signals are active for this resource.</li>
                )}
              </ul>
            </SectionCard>
          </div>
        </>
      ) : null}
    </div>
  );
}
