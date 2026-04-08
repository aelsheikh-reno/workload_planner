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
import {
  formatCountLabel,
  formatValue,
  messageForScreenState,
  routeForScreenId,
  toneForScreenState,
} from "../utils";

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
      <section className="modal-card" aria-label="M01 modal">
        <div className="drawer-header">
          <div>
            <p className="eyebrow">M01</p>
            <h3>Connected Change Set Modal</h3>
          </div>
          <button className="secondary-button" onClick={onClose} type="button">
            Close
          </button>
        </div>

        {modal.loading ? <LoadingSkeleton label="Loading connected set." /> : null}
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
            <SectionCard title="Requested delta">
              <div className="summary-card">
                <span>Entity</span>
                <strong>{formatValue(modal.data.requestedDelta?.entityName)}</strong>
                <small>{formatValue(modal.data.requestedDelta?.deltaId)}</small>
              </div>
            </SectionCard>
            <SectionCard
              title="Connected set"
              subtitle={`${formatCountLabel(
                modal.data.connectedSet?.memberItems?.length ?? 0,
                "member item",
              )}`}
            >
              <div className="card-grid">
                {modal.data.connectedSet?.memberItems?.length ? (
                  modal.data.connectedSet.memberItems.map((item) => (
                    <article className="delta-card" key={item.deltaId}>
                      <strong>{item.entityName}</strong>
                      <small>{item.deltaId}</small>
                    </article>
                  ))
                ) : (
                  <div className="summary-card">
                    <span>No connected set required</span>
                    <strong>This delta is already safe to handle directly.</strong>
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
                  {commandState.loading ? "Applying…" : "Select connected set"}
                </button>
                <button
                  className="secondary-button"
                  disabled={!modal.data.actions.deselectConnectedSetAvailable || commandState.loading}
                  onClick={() => handleConnectedSetSelection(false)}
                  type="button"
                >
                  Deselect connected set
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
      { label: "Total deltas", value: formatValue(review.data.deltaSummary.totalDeltaCount) },
      {
        label: "Selected",
        value: formatValue(review.data.deltaSummary.selectedDeltaCount),
      },
      {
        label: "Blocked",
        value: formatValue(review.data.deltaSummary.blockedDeltaCount),
      },
      {
        label: "Connected sets",
        value: formatValue(review.data.deltaSummary.connectedSetCount),
      },
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
      warningOriginScopeLabel:
        review.data?.reviewContextStatus?.reviewContextId
          ? "Current review context"
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
    ? `Return to ${returnNavigation.screen.id}`
    : null;

  return (
    <div className="screen-stack">
      <ScreenHeader
        eyebrow="S04"
        title="Delta Review"
        description="Formal review, acceptance, connected-set handling, and explicit activation over the current review context."
        actions={
          <>
            <button className="secondary-button" onClick={review.reload} type="button">
              Refresh review
            </button>
            {returnLabel ? (
              <button className="secondary-button" onClick={handleReturnToOrigin} type="button">
                {returnLabel}
              </button>
            ) : null}
            <button className="secondary-button" onClick={handleWarningReview} type="button">
              Open S05
            </button>
          </>
        }
      />

      <SectionCard
        title="Review context admission"
        subtitle="Generate or refresh the current review context from the current planning run."
      >
        <div className="command-row">
          <button
            className="primary-button"
            disabled={!resolvedPlanningRunId || reviewContextCommand.loading}
            onClick={handleReviewContextGenerate}
            type="button"
          >
            {reviewContextCommand.loading ? "Generating…" : "Generate / refresh review context"}
          </button>
        </div>
        {reviewContextCommand.error ? <ErrorCard error={reviewContextCommand.error} /> : null}
        {reviewContextCommand.result ? (
          <div className="command-result">
            <strong>Review context ready</strong>
            <p>Review context ID: {formatValue(reviewContextCommand.result.review_context_id)}</p>
          </div>
        ) : null}
      </SectionCard>

      {review.loading ? <LoadingSkeleton label="Loading S04 review state." /> : null}
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
            <SectionCard title="Review context status">
              <div className="summary-grid">
                <div className="summary-card">
                  <span>Review context</span>
                  <strong>{formatValue(review.data.reviewContextStatus?.reviewContextId)}</strong>
                </div>
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

            <SectionCard title="Activation">
              <div className="summary-card">
                <span>Status</span>
                <strong>{formatValue(review.data.activation?.status)}</strong>
                <small>
                  Workflow: {formatValue(review.data.activation?.downstreamWorkflow?.workflowState)}
                </small>
              </div>
              <div className="command-row">
                <button
                  className="primary-button"
                  disabled={!review.data.activation?.actionAvailable || activationCommand.loading}
                  onClick={handleActivation}
                  type="button"
                >
                  {activationCommand.loading ? "Activating…" : "Activate accepted changes"}
                </button>
              </div>
              {activationCommand.error ? <ErrorCard error={activationCommand.error} /> : null}
              {activationCommand.result ? (
                <div className="command-result">
                  <strong>Activation command returned</strong>
                  <p>
                    Activation ID:{" "}
                    {formatValue(
                      activationCommand.result.activationId ||
                      activationCommand.result.activationState?.activationId ||
                        activationCommand.result.activation_state?.activation_id,
                    )}
                  </p>
                </div>
              ) : null}
            </SectionCard>
          </div>

          {acceptanceCommand.error ? <ErrorCard error={acceptanceCommand.error} /> : null}

          <SectionCard title="Grouped delta review">
            <div className="delta-grid">
              {review.data.groupedDeltaReview.length ? (
                review.data.groupedDeltaReview.map((group) => (
                  <article className="delta-group" key={group.groupId}>
                    <div className="delta-header">
                      <div>
                        <strong>{group.groupLabel}</strong>
                        <p className="supporting-text">
                          {formatCountLabel(group.deltaCount, "delta")} · {formatCountLabel(group.blockedItemCount, "blocked item")}
                        </p>
                      </div>
                    </div>
                    <div className="delta-list">
                      {group.items.map((item) => (
                        <article className="delta-card" key={item.deltaId}>
                          <strong>{item.entityName}</strong>
                          <small>{item.deltaScopeAttributes.join(", ")}</small>
                          <ul className="plain-list">
                            {item.attributeChanges.map((change) => (
                              <li key={`${item.deltaId}-${change.attributeName}`}>
                                {change.attributeName}: {formatValue(change.beforeValue)} → {formatValue(change.afterValue)}
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
                              {item.acceptanceState.selected ? "Deselect" : "Select"}
                            </button>
                            {item.connectedSetEntry?.available ? (
                              <button
                                className="secondary-button"
                                onClick={() => setModalDeltaId(item.connectedSetEntry.requestedDeltaId)}
                                type="button"
                              >
                                Open M01
                              </button>
                            ) : null}
                          </div>
                        </article>
                      ))}
                    </div>
                  </article>
                ))
              ) : (
                <div className="summary-card">
                  <span>No deltas</span>
                  <strong>The current review context has no grouped items.</strong>
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
