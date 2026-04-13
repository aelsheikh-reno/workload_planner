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

const CLASSIFICATION_LABELS = {
  blocking: "⛔ Blocking",
  advisory: "⚠ Advisory",
  trust_limited: "ℹ Trust-Limited",
};

function friendlyClassification(label) {
  return CLASSIFICATION_LABELS[label] || label;
}

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

  const totalActiveFilters =
    activeWorkflowIds.length + activeClassificationFilters.length + activeSignalTypes.length;

  const hasCustomFilters =
    workflowFilters !== null || classificationFilters !== null || signalTypeFilters !== null;

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
        eyebrow="Warnings"
        title="Planning Warnings"
        description="Review all planning warnings and trust signals. Blocking warnings must be resolved before proceeding."
        actions={
          <button className="secondary-button" onClick={warnings.reload} type="button">
            Refresh
          </button>
        }
      />

      {warnings.loading ? <LoadingSkeleton label="Loading warnings…" /> : null}
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
              { label: "Total warnings", value: formatValue(warnings.data.workspaceSummary?.filteredSignalCount) },
              { label: "Blocking", value: formatValue(warnings.data.workspaceSummary?.blockingWarningCount) },
              { label: "Advisory", value: formatValue(warnings.data.workspaceSummary?.advisoryWarningCount) },
              { label: "Trust-limited", value: formatValue(warnings.data.workspaceSummary?.trustLimitedCount) },
            ]}
          />

          <SectionCard
            title="Filter Warnings"
            subtitle={totalActiveFilters > 0 ? `${totalActiveFilters} filter${totalActiveFilters !== 1 ? "s" : ""} active` : "Showing all warnings"}
            actions={
              hasCustomFilters ? (
                <button className="secondary-button" onClick={clearCustomFilters} type="button">
                  Clear All Filters
                </button>
              ) : null
            }
          >
            <div className="filter-stack">
              {warnings.data.filterState?.availableFilters?.workflowOptions?.length ? (
                <div className="filter-group">
                  <strong style={{ fontSize: "0.85rem" }}>By Workflow</strong>
                  <div className="chip-row">
                    {warnings.data.filterState.availableFilters.workflowOptions.map((option) => (
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
                    ))}
                  </div>
                </div>
              ) : null}

              {warnings.data.filterState?.availableFilters?.classificationOptions?.length ? (
                <div className="filter-group">
                  <strong style={{ fontSize: "0.85rem" }}>By Type</strong>
                  <div className="chip-row">
                    {warnings.data.filterState.availableFilters.classificationOptions.map((option) => (
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
                        {friendlyClassification(option.id)} ({option.count})
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {warnings.data.filterState?.availableFilters?.signalTypeOptions?.length ? (
                <div className="filter-group">
                  <strong style={{ fontSize: "0.85rem" }}>By Signal</strong>
                  <div className="chip-row">
                    {warnings.data.filterState.availableFilters.signalTypeOptions.map((option) => (
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
                    ))}
                  </div>
                </div>
              ) : null}

              {!warnings.data.filterState?.availableFilters?.workflowOptions?.length &&
               !warnings.data.filterState?.availableFilters?.classificationOptions?.length &&
               !warnings.data.filterState?.availableFilters?.signalTypeOptions?.length ? (
                <span className="supporting-text">No filters available for the current warning set.</span>
              ) : null}
            </div>
          </SectionCard>

          {trustGuidance.length ? (
            <SectionCard
              title="Trust Guidance"
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
            title="Warning Details"
            subtitle={`${formatCountLabel(warnings.data.warningItems.length, "warning")}`}
            actions={
              warnings.data.returnNavigation?.screen ? (
                <button
                  className="secondary-button"
                  onClick={handleReturnToWorkflow}
                  type="button"
                >
                  ← Back to {warnings.data.returnNavigation.screen.id}
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
                          {formatCountLabel(group.summary.itemCount, "warning")}
                          {group.summary.blockingCount > 0 ? ` · ${group.summary.blockingCount} blocking` : ""}
                          {group.summary.advisoryCount > 0 ? ` · ${group.summary.advisoryCount} advisory` : ""}
                          {group.summary.trustLimitedCount > 0 ? ` · ${group.summary.trustLimitedCount} trust-limited` : ""}
                        </p>
                      </div>
                    </div>
                    <div className="warning-grid">
                      {group.items.map((item) => (
                        <article className="warning-card" key={item.itemId}>
                          <div className="warning-header">
                            <div>
                              <strong>{item.message || item.code}</strong>
                              <small>{friendlyClassification(item.classification) || item.classificationLabel}</small>
                            </div>
                          </div>
                          {item.message && item.code !== item.message ? (
                            <p className="supporting-text">{item.code}</p>
                          ) : null}
                          {item.affectedScope?.scopeLabel ? (
                            <small>Scope: {formatValue(item.affectedScope.scopeLabel)}</small>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className="summary-card">
                  <span>No warnings</span>
                  <strong>{warnings.data.emptyState?.message || "No warnings to review in the current scope."}</strong>
                </div>
              )}
            </div>
          </SectionCard>
        </>
      ) : null}
    </div>
  );
}
