import { useMemo, useState } from "react";
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
import {
  formatCountLabel,
  formatValue,
  messageForScreenState,
  routeForScreenId,
  toneForScreenState,
} from "../utils";

function toggleFilter(currentValues, value, setter) {
  const next = new Set(currentValues);
  if (next.has(value)) {
    next.delete(value);
  } else {
    next.add(value);
  }
  setter(Array.from(next));
}

export function S05WarningsScreen({ shellState, updateShellState }) {
  const navigate = useNavigate();
  const [workflowFilters, setWorkflowFilters] = useState(null);
  const [classificationFilters, setClassificationFilters] = useState(null);
  const [signalTypeFilters, setSignalTypeFilters] = useState(null);
  const warnings = useRouteData("/api/screens/s05/warnings-workspace", {
    query: {
      planningContextKey: shellState.planningContextKey,
      sourceSnapshotId: shellState.sourceSnapshotId,
      originScreenId: shellState.warningOriginScreenId,
      originScopeType: shellState.warningOriginScopeType,
      originScopeId: shellState.warningOriginScopeId,
      originScopeExternalId: shellState.warningOriginScopeExternalId,
      originScopeLabel: shellState.warningOriginScopeLabel,
      workflowFilterId: workflowFilters || undefined,
      classificationFilter: classificationFilters || undefined,
      signalTypeFilter: signalTypeFilters || undefined,
    },
    enabled: true,
  });

  const activeWorkflowIds =
    workflowFilters ?? warnings.data?.filterState?.activeWorkflowIds ?? [];
  const activeClassificationFilters =
    classificationFilters ?? warnings.data?.filterState?.activeClassificationFilters ?? [];
  const activeSignalTypes =
    signalTypeFilters ?? warnings.data?.filterState?.activeSignalTypes ?? [];
  const trustGuidance = warnings.data?.trustGuidance ?? [];

  const groupedWarnings = useMemo(() => {
    if (!warnings.data) {
      return [];
    }
    const itemsByWorkflow = new Map();
    warnings.data.warningItems.forEach((item) => {
      const workflowId = item.affectedWorkflow?.id || "ungrouped";
      const existing = itemsByWorkflow.get(workflowId) || [];
      existing.push(item);
      itemsByWorkflow.set(workflowId, existing);
    });

    const baseGroups = (warnings.data.groupSummaries || []).map((summary) => ({
      summary,
      items: itemsByWorkflow.get(summary.workflowId) || [],
    }));
    const knownWorkflowIds = new Set(baseGroups.map((group) => group.summary.workflowId));
    const fallbackGroups = Array.from(itemsByWorkflow.entries())
      .filter(([workflowId]) => !knownWorkflowIds.has(workflowId))
      .map(([workflowId, items]) => ({
        summary: {
          workflowId,
          workflowLabel: items[0]?.affectedWorkflow?.label || workflowId,
          itemCount: items.length,
          blockingCount: items.filter((item) => item.classification === "blocking").length,
          advisoryCount: items.filter((item) => item.classification === "advisory").length,
          trustLimitedCount: items.filter((item) => item.classification === "trust_limited").length,
        },
        items,
      }));

    if (!baseGroups.length && fallbackGroups.length) {
      return fallbackGroups;
    }
    return [...baseGroups, ...fallbackGroups];
  }, [warnings.data]);

  function clearCustomFilters() {
    setWorkflowFilters(null);
    setClassificationFilters(null);
    setSignalTypeFilters(null);
  }

  function handleReturnToWorkflow() {
    const returnNavigation = warnings.data?.returnNavigation;
    const screenId = returnNavigation?.screen?.id;
    const targetPath = routeForScreenId(screenId);
    if (!targetPath) {
      return;
    }

    const patch = {};
    if (screenId === "S03") {
      patch.resourceExternalId =
        returnNavigation?.scope?.scopeExternalId ||
        returnNavigation?.scope?.scopeId ||
        shellState.resourceExternalId;
    }
    updateShellState?.(patch);
    navigate(targetPath);
  }

  return (
    <div className="screen-stack">
      <ScreenHeader
        eyebrow="S05"
        title="Planning Warnings Workspace"
        description="Dedicated warning and trust review with workflow return navigation."
        actions={
          <button className="secondary-button" onClick={warnings.reload} type="button">
            Refresh warnings
          </button>
        }
      />

      {warnings.loading ? <LoadingSkeleton label="Loading warnings workspace." /> : null}
      {warnings.error ? <ErrorCard error={warnings.error} onRetry={warnings.reload} /> : null}
      {warnings.data ? (
        <>
          <ScreenStateCard
            state={warnings.data.viewState.screenState}
            message={warnings.data.emptyState?.message || messageForScreenState(warnings.data.viewState.screenState)}
            tone={toneForScreenState(warnings.data.viewState.screenState)}
          />

          <MetricGrid
            items={[
              { label: "Visible signals", value: formatValue(warnings.data.workspaceSummary?.filteredSignalCount) },
              { label: "Blocking warnings", value: formatValue(warnings.data.workspaceSummary?.blockingWarningCount) },
              { label: "Advisories", value: formatValue(warnings.data.workspaceSummary?.advisoryWarningCount) },
              { label: "Trust-limited", value: formatValue(warnings.data.workspaceSummary?.trustLimitedCount) },
            ]}
          />

          <SectionCard
            title="Grouping and filters"
            subtitle={`Default grouping: ${formatValue(warnings.data.filterState?.groupBy)}`}
            actions={
              <button className="secondary-button" onClick={clearCustomFilters} type="button">
                Reset filters
              </button>
            }
          >
            <div className="filter-stack">
              <div className="filter-group">
                <strong>Workflow filters</strong>
                <div className="chip-row">
                  {warnings.data.filterState?.availableFilters?.workflowOptions?.length ? (
                    warnings.data.filterState.availableFilters.workflowOptions.map((option) => (
                      <button
                        aria-pressed={activeWorkflowIds.includes(option.workflowId)}
                        className="ghost-button chip-button"
                        key={option.workflowId}
                        onClick={() =>
                          toggleFilter(activeWorkflowIds, option.workflowId, setWorkflowFilters)
                        }
                        type="button"
                      >
                        {option.workflowLabel} ({option.count})
                      </button>
                    ))
                  ) : (
                    <span className="supporting-text">No workflow filters are available in the current scope.</span>
                  )}
                </div>
              </div>

              <div className="filter-group">
                <strong>Classification filters</strong>
                <div className="chip-row">
                  {warnings.data.filterState?.availableFilters?.classificationOptions?.length ? (
                    warnings.data.filterState.availableFilters.classificationOptions.map((option) => (
                      <button
                        aria-pressed={activeClassificationFilters.includes(option.id)}
                        className="ghost-button chip-button"
                        key={option.id}
                        onClick={() =>
                          toggleFilter(
                            activeClassificationFilters,
                            option.id,
                            setClassificationFilters,
                          )
                        }
                        type="button"
                      >
                        {option.label} ({option.count})
                      </button>
                    ))
                  ) : (
                    <span className="supporting-text">No classification filters are available in the current scope.</span>
                  )}
                </div>
              </div>

              <div className="filter-group">
                <strong>Signal type filters</strong>
                <div className="chip-row">
                  {warnings.data.filterState?.availableFilters?.signalTypeOptions?.length ? (
                    warnings.data.filterState.availableFilters.signalTypeOptions.map((option) => (
                      <button
                        aria-pressed={activeSignalTypes.includes(option.id)}
                        className="ghost-button chip-button"
                        key={option.id}
                        onClick={() =>
                          toggleFilter(activeSignalTypes, option.id, setSignalTypeFilters)
                        }
                        type="button"
                      >
                        {option.label} ({option.count})
                      </button>
                    ))
                  ) : (
                    <span className="supporting-text">No signal-type filters are available in the current scope.</span>
                  )}
                </div>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title="Affected workflow groups"
            subtitle={`${formatCountLabel(groupedWarnings.length, "workflow group")}`}
          >
            <div className="card-grid">
              {groupedWarnings.length ? (
                groupedWarnings.map((group) => (
                  <article className="summary-card" key={group.summary.workflowId}>
                    <span>{group.summary.workflowLabel}</span>
                    <strong>{formatCountLabel(group.summary.itemCount, "warning")}</strong>
                    <small>
                      Blocking {group.summary.blockingCount} · Advisory {group.summary.advisoryCount} · Trust-limited {group.summary.trustLimitedCount}
                    </small>
                  </article>
                ))
              ) : (
                <div className="summary-card">
                  <span>No workflow groups</span>
                  <strong>The current warning scope has no grouped workflows.</strong>
                </div>
              )}
            </div>
          </SectionCard>

          {trustGuidance.length ? (
            <SectionCard
              title="Trust guidance"
              subtitle={`${formatCountLabel(trustGuidance.length, "guidance item")}`}
            >
              <div className="card-grid">
                {trustGuidance.map((guidance) => (
                  <article className="warning-card" key={guidance.guidanceId}>
                    <div className="warning-header">
                      <div>
                        <strong>{guidance.title}</strong>
                        <small>{formatCountLabel(guidance.relatedItemCount, "related warning")}</small>
                      </div>
                    </div>
                    <p className="supporting-text">{guidance.message}</p>
                  </article>
                ))}
              </div>
            </SectionCard>
          ) : null}

          <SectionCard
            title="Warning items"
            subtitle={`${formatCountLabel(warnings.data.warningItems.length, "warning item")}`}
            actions={
              warnings.data.returnNavigation?.screen ? (
                <button
                  className="secondary-button"
                  onClick={handleReturnToWorkflow}
                  type="button"
                >
                  Return to {warnings.data.returnNavigation.screen.id}
                </button>
              ) : null
            }
          >
            <div className="warning-group-list">
              {warnings.data.warningItems.length ? (
                groupedWarnings.map((group) => (
                  <div className="warning-group" key={group.summary.workflowId}>
                    <div className="warning-group__header">
                      <div>
                        <strong>{group.summary.workflowLabel}</strong>
                        <p className="supporting-text">
                          {formatCountLabel(group.summary.itemCount, "warning")} · Blocking {group.summary.blockingCount} · Advisory {group.summary.advisoryCount} · Trust-limited {group.summary.trustLimitedCount}
                        </p>
                      </div>
                    </div>
                    <div className="warning-grid">
                      {group.items.map((item) => (
                        <article className="warning-card" key={item.itemId}>
                          <div className="warning-header">
                            <div>
                              <strong>{item.code}</strong>
                              <small>{item.classificationLabel}</small>
                            </div>
                          </div>
                          <p className="supporting-text">{item.message}</p>
                          <small>
                            Workflow: {formatValue(item.affectedWorkflow?.label)} · Scope:{" "}
                            {formatValue(item.affectedScope?.scopeLabel)}
                          </small>
                        </article>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className="summary-card">
                  <span>No warnings in scope</span>
                  <strong>{warnings.data.emptyState?.message || "There are no warning items to review."}</strong>
                </div>
              )}
            </div>
          </SectionCard>
        </>
      ) : null}
    </div>
  );
}
