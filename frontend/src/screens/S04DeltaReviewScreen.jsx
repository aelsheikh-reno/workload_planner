import { useEffect, useMemo, useState } from "react";
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
import {
  formatCountLabel,
  formatValue,
  messageForScreenState,
  routeForScreenId,
  toneForScreenState,
} from "../utils";

const ATTRIBUTE_LABELS = {
  task_start_date: "Task Start Date",
  task_due_date: "Task Due Date",
  milestone_date: "Milestone Date",
  project_finish_date: "Project Finish Date",
  assigned_resource_external_ids: "Assigned Resources",
};

function friendlyAttribute(name) {
  return ATTRIBUTE_LABELS[name] || name;
}

function M01Modal({
  planningContextKey,
  requestedDeltaId,
  reviewContextId,
  onClose,
  onApplied,
}) {
  const modal = useRouteData("/api/modals/m01/connected-change-set", {
    query: {
      reviewContextId,
      requestedDeltaId,
      planningContextKey,
    },
    enabled: Boolean(requestedDeltaId && reviewContextId),
  });
  const [commandState, setCommandState] = useState({ loading: false, error: null });

  async function handleConnectedSetSelection(selected) {
    setCommandState({ loading: true, error: null });
    try {
      await requestJson("/api/modals/m01/connected-change-set/acceptance-selection", {
        method: "POST",
        body: {
          reviewContextId,
          requestedDeltaId,
          selected,
        },
      });
      setCommandState({ loading: false, error: null });
      onApplied();
      onClose();
    } catch (error) {
      setCommandState({ loading: false, error });
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-card" aria-label="Connected Changes">
        <div className="drawer-header">
          <div>
            <p className="eyebrow">Related Changes</p>
            <h3>Connected Change Set</h3>
          </div>
          <button className="secondary-button" onClick={onClose} type="button">
            Close
          </button>
        </div>

        {modal.loading ? <LoadingSkeleton label="Loading connected changes…" /> : null}
        {modal.error ? <ErrorCard error={modal.error} onRetry={modal.reload} /> : null}
        {commandState.error ? <ErrorCard error={commandState.error} /> : null}
        {modal.data ? (
          <div className="screen-stack">
            <ScreenStateCard
              state={modal.data.viewState.screenState}
              message={
                modal.data.blockingReason?.message ||
                messageForScreenState(modal.data.viewState.screenState)
              }
              tone={toneForScreenState(modal.data.viewState.screenState)}
            />
            <SectionCard title="Requested Change">
              <div className="summary-card">
                <span>Item</span>
                <strong>{formatValue(modal.data.requestedDelta?.entityName)}</strong>
              </div>
            </SectionCard>
            <SectionCard
              title="Related Changes"
              subtitle={`${formatCountLabel(
                modal.data.connectedSet?.memberItems?.length ?? 0,
                "related change",
              )} — these must be handled together`}
            >
              <div className="card-grid">
                {modal.data.connectedSet?.memberItems?.length ? (
                  modal.data.connectedSet.memberItems.map((item) => (
                    <article className="delta-card" key={item.deltaId}>
                      <strong>{item.entityName}</strong>
                    </article>
                  ))
                ) : (
                  <div className="summary-card">
                    <span>No related changes</span>
                    <strong>This change can be handled independently.</strong>
                  </div>
                )}
              </div>
              <div className="command-row">
                <button
                  className="primary-button"
                  disabled={!modal.data.actions.selectConnectedSetAvailable || commandState.loading}
                  onClick={() => handleConnectedSetSelection(true)}
                  type="button"
                >
                  {commandState.loading ? "Applying…" : "Accept All Related Changes"}
                </button>
                <button
                  className="secondary-button"
                  disabled={!modal.data.actions.deselectConnectedSetAvailable || commandState.loading}
                  onClick={() => handleConnectedSetSelection(false)}
                  type="button"
                >
                  Reject All
                </button>
              </div>
            </SectionCard>
          </div>
        ) : null}
      </section>
    </div>
  );
}

export function S04DeltaReviewScreen({ shellState, updateShellState }) {
  const navigate = useNavigate();
  const [reviewContextCommand, setReviewContextCommand] = useState({
    loading: false,
    result: null,
    error: null,
  });
  const [acceptanceCommand, setAcceptanceCommand] = useState({
    loadingDeltaId: null,
    error: null,
  });
  const [activationCommand, setActivationCommand] = useState({
    loading: false,
    result: null,
    error: null,
  });
  const [modalDeltaId, setModalDeltaId] = useState(null);
  const [expandedGroups, setExpandedGroups] = useState({});
  const [toast, setToast] = useState(null);

  const review = useRouteData("/api/screens/s04/delta-review", {
    query: {
      reviewContextId: shellState.reviewContextId,
      planningContextKey: shellState.planningContextKey,
      originScreenId: shellState.reviewOriginScreenId,
      originScopeType: shellState.reviewOriginScopeType,
      originScopeId: shellState.reviewOriginScopeId,
      originScopeExternalId: shellState.reviewOriginScopeExternalId,
      originScopeLabel: shellState.reviewOriginScopeLabel,
      focusedDeltaId: modalDeltaId,
    },
    enabled: true,
  });

  const metrics = useMemo(() => {
    if (!review.data?.deltaSummary) {
      return [];
    }
    return [
      { label: "Total changes", value: formatValue(review.data.deltaSummary.totalDeltaCount) },
      { label: "Accepted", value: formatValue(review.data.deltaSummary.selectedDeltaCount) },
      { label: "Blocked", value: formatValue(review.data.deltaSummary.blockedDeltaCount) },
      { label: "Linked groups", value: formatValue(review.data.deltaSummary.connectedSetCount) },
    ];
  }, [review.data]);

  const resolvedReviewContextId =
    shellState.reviewContextId ||
    review.data?.reviewContextStatus?.reviewContextId ||
    review.data?.queryContext?.reviewContextId ||
    "";
  const resolvedPlanningRunId =
    shellState.planningRunId || review.data?.queryContext?.planningRunId || "";
  const resolvedSourceSnapshotId =
    shellState.sourceSnapshotId || review.data?.queryContext?.sourceSnapshotId || "";
  const resolvedApprovedPlanId =
    shellState.approvedPlanId || review.data?.queryContext?.approvedPlanId || "";

  useEffect(() => {
    if (!review.data) {
      return;
    }

    const patch = {};

    if (resolvedReviewContextId && shellState.reviewContextId !== resolvedReviewContextId) {
      patch.reviewContextId = resolvedReviewContextId;
    }
    if (resolvedPlanningRunId && shellState.planningRunId !== resolvedPlanningRunId) {
      patch.planningRunId = resolvedPlanningRunId;
    }
    if (resolvedSourceSnapshotId && shellState.sourceSnapshotId !== resolvedSourceSnapshotId) {
      patch.sourceSnapshotId = resolvedSourceSnapshotId;
    }
    if (resolvedApprovedPlanId && shellState.approvedPlanId !== resolvedApprovedPlanId) {
      patch.approvedPlanId = resolvedApprovedPlanId;
    }

    if (Object.keys(patch).length) {
      updateShellState(patch);
    }
  }, [
    resolvedApprovedPlanId,
    resolvedPlanningRunId,
    resolvedReviewContextId,
    resolvedSourceSnapshotId,
    review.data,
    shellState.approvedPlanId,
    shellState.planningRunId,
    shellState.reviewContextId,
    shellState.sourceSnapshotId,
    updateShellState,
  ]);

  async function handleReviewContextGenerate() {
    setReviewContextCommand({ loading: true, result: null, error: null });
    try {
      const result = await requestJson("/api/screens/s04/review-context", {
        method: "POST",
        body: {
          planningRunId: resolvedPlanningRunId,
          approvedPlanId: resolvedApprovedPlanId || undefined,
        },
      });
      updateShellState({
        reviewContextId: result.review_context_id,
        sourceSnapshotId: result.source_snapshot_id || shellState.sourceSnapshotId,
      });
      setReviewContextCommand({ loading: false, result, error: null });
      setToast({ message: "Review context generated.", tone: "good" });
    } catch (error) {
      setReviewContextCommand({ loading: false, result: null, error });
    }
  }

  async function handleDeltaSelection(deltaId, selected) {
    setAcceptanceCommand({ loadingDeltaId: deltaId, error: null });
    try {
      const result = await requestJson("/api/screens/s04/acceptance-selection", {
        method: "POST",
        body: {
          reviewContextId: resolvedReviewContextId,
          deltaId,
          selected,
        },
      });
      if (result.modalLaunch?.available && result.modalLaunch?.requestedDeltaId) {
        setModalDeltaId(result.modalLaunch.requestedDeltaId);
      }
      setAcceptanceCommand({ loadingDeltaId: null, error: null });
      review.reload();
    } catch (error) {
      setAcceptanceCommand({ loadingDeltaId: null, error });
    }
  }

  async function handleActivation() {
    setActivationCommand({ loading: true, result: null, error: null });
    try {
      const result = await requestJson("/api/screens/s04/activation", {
        method: "POST",
        body: {
          reviewContextId: resolvedReviewContextId,
          requestedBy: shellState.requestedBy,
          requestedAt: nowIsoString(),
        },
      });
      updateShellState({
        activationId:
          result.activationId ||
          result.activationState?.activationId ||
          result.activation_state?.activation_id ||
          "",
      });
      setActivationCommand({ loading: false, result, error: null });
      setToast({ message: "Changes activated successfully.", tone: "good" });
      review.reload();
    } catch (error) {
      setActivationCommand({ loading: false, result: null, error });
    }
  }

  function handleWarningReview() {
    updateShellState({
      warningOriginScreenId: "S04",
      warningOriginScopeType: "review",
      warningOriginScopeId:
        review.data?.reviewContextStatus?.reviewContextId ||
        review.data?.queryContext?.reviewContextId ||
        "",
      warningOriginScopeExternalId:
        review.data?.reviewContextStatus?.reviewContextId ||
        review.data?.queryContext?.reviewContextId ||
        "",
      warningOriginScopeLabel: review.data?.reviewContextStatus?.reviewContextId
        ? "Current review"
        : "",
    });
    navigate("/s05");
  }

  function handleReturnToOrigin() {
    const returnNavigation = review.data?.navigation?.returnNavigation;
    const screenId = returnNavigation?.screen?.id;
    const targetPath = routeForScreenId(screenId);
    if (!targetPath) {
      return;
    }

    const originScope = returnNavigation?.originScope;
    const patch = {};
    if (screenId === "S03") {
      patch.resourceExternalId =
        originScope?.scopeExternalId || originScope?.scopeId || shellState.resourceExternalId;
    }
    updateShellState(patch);
    navigate(targetPath);
  }

  const returnNavigation = review.data?.navigation?.returnNavigation;
  const returnLabel = returnNavigation?.screen?.id
    ? `← Back to ${returnNavigation.screen.id}`
    : null;

  return (
    <div className="screen-stack">
      {toast ? (
        <Toast message={toast.message} tone={toast.tone} onDismiss={() => setToast(null)} />
      ) : null}

      <ScreenHeader
        eyebrow="Change Review"
        title="Review & Activate Changes"
        description="Review the proposed changes from your latest analysis, accept or reject each one, then activate to apply them."
        actions={
          <>
            <button className="secondary-button" onClick={review.reload} type="button">
              Refresh
            </button>
            {returnLabel ? (
              <button className="secondary-button" onClick={handleReturnToOrigin} type="button">
                {returnLabel}
              </button>
            ) : null}
            <button className="secondary-button" onClick={handleWarningReview} type="button">
              View Warnings
            </button>
          </>
        }
      />

      <SectionCard
        title="Step 1: Load Changes"
        subtitle="Generate or refresh the list of proposed changes from your latest analysis run."
      >
        <div className="command-row">
          <button
            className="primary-button"
            disabled={!resolvedPlanningRunId || reviewContextCommand.loading}
            onClick={handleReviewContextGenerate}
            type="button"
          >
            {reviewContextCommand.loading ? "Loading changes…" : "Load Changes for Review"}
          </button>
        </div>
        {!resolvedPlanningRunId ? (
          <p className="supporting-text" style={{ marginTop: "0.5rem" }}>
            No analysis run found. Go to Setup to run the capacity analysis first.
          </p>
        ) : null}
        {reviewContextCommand.error ? <ErrorCard error={reviewContextCommand.error} /> : null}
      </SectionCard>

      {review.loading ? <LoadingSkeleton label="Loading changes…" /> : null}
      {review.error ? <ErrorCard error={review.error} onRetry={review.reload} /> : null}
      {review.data ? (
        <>
          <ScreenStateCard
            state={review.data.viewState.screenState}
            message={
              review.data.blockedAcceptance?.message ||
              messageForScreenState(review.data.viewState.screenState)
            }
            tone={toneForScreenState(review.data.viewState.screenState)}
          />
          <MetricGrid items={metrics} />

          <div className="split-layout">
            <SectionCard title="Review Status">
              <div className="summary-grid">
                <div className="summary-card">
                  <span>Review stage</span>
                  <strong>{formatValue(review.data.acceptanceState?.reviewStage)}</strong>
                </div>
                <div className="summary-card">
                  <span>Comparison</span>
                  <strong>{formatValue(review.data.reviewContextStatus?.comparisonContext)}</strong>
                </div>
              </div>
            </SectionCard>

            <SectionCard title="Step 2: Activate">
              <div className="summary-card" style={{ marginBottom: "0.75rem" }}>
                <span>Activation status</span>
                <strong>{formatValue(review.data.activation?.status)}</strong>
              </div>
              <div className="command-row">
                <button
                  className="primary-button"
                  disabled={!review.data.activation?.actionAvailable || activationCommand.loading}
                  onClick={handleActivation}
                  type="button"
                >
                  {activationCommand.loading ? "Activating…" : "Activate Accepted Changes"}
                </button>
              </div>
              {!review.data.activation?.actionAvailable ? (
                <p className="supporting-text" style={{ marginTop: "0.5rem" }}>
                  Accept at least one change below before activating.
                </p>
              ) : null}
              {activationCommand.error ? <ErrorCard error={activationCommand.error} /> : null}
            </SectionCard>
          </div>

          {acceptanceCommand.error ? <ErrorCard error={acceptanceCommand.error} /> : null}

          <SectionCard
            title="Proposed Changes"
            subtitle="Review each proposed change. Accept the ones you want to apply, then click Activate above."
          >
            <div className="delta-grid">
              {review.data.groupedDeltaReview.length ? (
                review.data.groupedDeltaReview.map((group) => {
                  const isExpanded = expandedGroups[group.groupId] !== false;
                  const visibleItems = isExpanded ? group.items : group.items.slice(0, 5);
                  const hiddenCount = group.items.length - visibleItems.length;

                  return (
                    <article className="delta-group" key={group.groupId}>
                      <div className="delta-header">
                        <div>
                          <strong>{group.groupLabel}</strong>
                          <p className="supporting-text">
                            {formatCountLabel(group.deltaCount, "change")}
                            {group.blockedItemCount > 0 ? ` · ${group.blockedItemCount} blocked` : ""}
                          </p>
                        </div>
                      </div>
                      <div className="delta-list">
                        {visibleItems.map((item) => (
                          <article className="delta-card" key={item.deltaId}>
                            <strong>{item.entityName}</strong>
                            <ul className="plain-list">
                              {item.attributeChanges.map((change) => (
                                <li key={`${item.deltaId}-${change.attributeName}`}>
                                  <strong>{friendlyAttribute(change.attributeName)}:</strong>{" "}
                                  {formatValue(change.beforeValue)} → {formatValue(change.afterValue)}
                                </li>
                              ))}
                            </ul>
                            <div className="delta-actions">
                              <button
                                className="primary-button"
                                disabled={
                                  !item.acceptanceState.directSelectable ||
                                  acceptanceCommand.loadingDeltaId === item.deltaId
                                }
                                onClick={() => handleDeltaSelection(item.deltaId, !item.acceptanceState.selected)}
                                type="button"
                              >
                                {acceptanceCommand.loadingDeltaId === item.deltaId
                                  ? "…"
                                  : item.acceptanceState.selected
                                    ? "✓ Accepted — Undo"
                                    : "Accept"}
                              </button>
                              {item.connectedSetEntry?.available ? (
                                <button
                                  className="secondary-button"
                                  onClick={() => setModalDeltaId(item.connectedSetEntry.requestedDeltaId)}
                                  type="button"
                                >
                                  Related Changes
                                </button>
                              ) : null}
                            </div>
                          </article>
                        ))}
                        {hiddenCount > 0 ? (
                          <button
                            className="ghost-button"
                            onClick={() => setExpandedGroups((s) => ({ ...s, [group.groupId]: true }))}
                            type="button"
                          >
                            Show {hiddenCount} more change{hiddenCount !== 1 ? "s" : ""}…
                          </button>
                        ) : null}
                        {isExpanded && group.items.length > 5 ? (
                          <button
                            className="ghost-button"
                            onClick={() => setExpandedGroups((s) => ({ ...s, [group.groupId]: false }))}
                            type="button"
                          >
                            Collapse
                          </button>
                        ) : null}
                      </div>
                    </article>
                  );
                })
              ) : (
                <div className="summary-card">
                  <span>No changes to review</span>
                  <strong>
                    {resolvedReviewContextId
                      ? "The current review has no proposed changes."
                      : "Click 'Load Changes for Review' above to get started."}
                  </strong>
                </div>
              )}
            </div>
          </SectionCard>
        </>
      ) : null}

      {modalDeltaId ? (
        <M01Modal
          onApplied={review.reload}
          onClose={() => setModalDeltaId(null)}
          planningContextKey={shellState.planningContextKey}
          requestedDeltaId={modalDeltaId}
          reviewContextId={resolvedReviewContextId}
        />
      ) : null}
    </div>
  );
}
