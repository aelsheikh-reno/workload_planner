import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

function jsonResponse(payload, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function deferredResponse() {
  let resolve;
  const promise = new Promise((promiseResolve) => {
    resolve = promiseResolve;
  });
  return {
    promise,
    resolve(payload, status = 200) {
      resolve(
        new Response(JSON.stringify(payload), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );
    },
  };
}

function buildFetchMock(routeMap) {
  return vi.fn((input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, "http://localhost");
    const method = (init.method || "GET").toUpperCase();
    const key = `${method} ${url.pathname}`;
    const handler = routeMap[key];
    if (!handler) {
      throw new Error(`Unhandled fetch ${key}${url.search}`);
    }
    if (typeof handler === "function") {
      return handler(url, init);
    }
    if (handler instanceof Promise) {
      return handler;
    }
    return jsonResponse(handler);
  });
}

function renderAt(pathname) {
  window.history.pushState({}, "", pathname);
  return render(
    <BrowserRouter
      future={{
        v7_relativeSplatPath: true,
        v7_startTransition: true,
      }}
    >
      <App />
    </BrowserRouter>,
  );
}

const s02Payload = {
  screen: { id: "S02", label: "Planning Setup" },
  queryContext: { planningContextKey: "context::frontend-shell", sourceSnapshotId: null },
  viewState: {
    screenState: "missing",
    isRefreshing: false,
    accessRestricted: false,
    accessRestrictedReason: null,
  },
  sourceReadiness: { state: "missing", runnable: false, blockingIssueCount: 0, advisoryIssueCount: 0, totalIssueCount: 0 },
  capacityInputReadiness: { state: "missing", runnable: false, blockingIssueCount: 0, advisoryIssueCount: 0, totalIssueCount: 0, stubbed: false },
  overallReadiness: { state: "missing", runnable: false, canContinueToPlanning: false, basis: "s02_bff_composed_readiness", noRunnablePlanBlockerCount: 1, advisorySignalCount: 0 },
  latestImport: null,
  planningRunStatus: null,
  sourceSetupIssues: [],
  capacityInputIssues: [],
  setupWarningTrustState: { activeSignalCount: 0, advisorySignalCount: 0, blockingSignalCount: 0, signals: [], stubbed: false },
  noRunnablePlanBlockers: [{ code: "missing_normalized_source_snapshot", message: "A normalized source snapshot is required before planning can run." }],
  advisorySignals: [],
  stubbedDependencies: [],
};

const s01Payload = {
  screen: { id: "S01", label: "Portfolio Swimlane Home" },
  queryContext: { planningRunId: "planning-run-01", sourceSnapshotId: "snapshot-01" },
  viewState: { screenState: "indicator_present", isRefreshing: false, unavailableReason: null },
  portfolioSummary: {
    planningRunId: "planning-run-01",
    draftScheduleId: "draft-schedule-01",
    comparisonContext: "source_baseline_only",
    scheduleState: "scheduled",
  },
  indicatorSummary: {
    movementIndicatorTaskCount: 1,
    freeCapacitySegmentCount: 3,
  },
  dailySwimlanes: [
    {
      resourceExternalId: "user-ada",
      resourceDisplayName: "Ada Lovelace",
      totalAllocatedHours: 24,
      totalProductiveCapacityHours: 40,
      ghostSummary: { hasGhostLoad: false },
      dailySegments: [
        {
          date: "2026-04-08",
          weekStartDate: "2026-04-06",
          allocatedHours: 8,
          productiveCapacityHours: 8,
          taskCount: 1,
          hasGhostLoad: false,
        },
      ],
    },
  ],
  unavailableState: null,
};

const d01Payload = {
  drawer: { id: "D01", label: "Swimlane Task Drill-Down Drawer", ownerScreenId: "S01" },
  queryContext: { planningRunId: "planning-run-01", sourceSnapshotId: "snapshot-01", resourceExternalId: "user-ada", date: "2026-04-08", weekStartDate: "2026-04-06" },
  viewState: { screenState: "ready", isRefreshing: false, unavailableReason: null },
  segmentContext: { resourceExternalId: "user-ada", date: "2026-04-08", selectedTaskCount: 1 },
  segmentSummary: { taskCount: 1, ghostVisible: false },
  tasks: [
    {
      taskExternalId: "task-ada-01",
      taskName: "Prepare launch report",
      status: "scheduled",
      movementIndicator: { present: false },
      riskIndicator: { present: true },
    },
  ],
  unavailableState: null,
};

const s03Payload = {
  screen: { id: "S03", label: "Resource Detail" },
  queryContext: {
    planningRunId: "planning-run-01",
    planningContextKey: "context::frontend-shell",
    sourceSnapshotId: "snapshot-01",
    resourceExternalId: "user-ada",
    originScreenId: "S01",
  },
  viewState: {
    screenState: "no_actionable_recommendation",
    isLoading: false,
    isRefreshing: false,
    accessRestricted: false,
    accessRestrictedReason: null,
    unavailableReason: null,
  },
  resourceSummary: {
    resourceDisplayName: "Ada Lovelace",
    resourceExternalId: "user-ada",
    utilizationRatio: 0.8,
    scheduledTaskCount: 2,
    overloadedDayCount: 0,
    warningSignalCount: 1,
    totalAllocatedHours: 32,
    totalProductiveCapacityHours: 40,
    riskIndicatorCount: 1,
  },
  workloadTimeline: [{ date: "2026-04-08", allocatedHours: 8, productiveCapacityHours: 8, taskCount: 1 }],
  assignedWorkQueue: [{ taskExternalId: "task-ada-01", taskName: "Prepare launch report", status: "scheduled", scheduledStartDate: "2026-04-08", scheduledEndDate: "2026-04-08" }],
  recommendationContext: {
    state: "no_actionable_recommendations",
    totalRecommendationCount: 0,
    items: [],
  },
  warningTrustContext: {
    activeSignalCount: 1,
    items: [{ signalId: "warning-01", headline: "Low confidence on one date" }],
  },
  navigation: {},
};

const s04Payload = {
  screen: { id: "S04", label: "Delta Review" },
  queryContext: {
    reviewContextId: "review-context-01",
    planningRunId: "planning-run-01",
    planningContextKey: "context::frontend-shell",
    sourceSnapshotId: "snapshot-01",
    approvedPlanId: "approved-plan-01",
    originScreenId: "S03",
    originScope: null,
    focusedDeltaId: null,
  },
  viewState: {
    screenState: "blocked_isolated_acceptance",
    isRefreshing: false,
    accessRestricted: false,
    accessRestrictedReason: null,
  },
  reviewContextStatus: {
    reviewContextId: "review-context-01",
    comparisonContext: "draft_vs_current_approved_plan",
  },
  deltaSummary: {
    totalDeltaCount: 2,
    selectedDeltaCount: 0,
    blockedDeltaCount: 1,
    connectedSetCount: 1,
  },
  groupedDeltaReview: [
    {
      groupId: "project-01",
      groupLabel: "Project Mercury",
      deltaCount: 2,
      blockedItemCount: 1,
      items: [
        {
          deltaId: "delta-01",
          entityName: "Implementation task",
          deltaScopeAttributes: ["task_due_date"],
          attributeChanges: [
            { attributeName: "task_due_date", beforeValue: "2026-04-10", afterValue: "2026-04-12" },
          ],
          acceptanceState: {
            selected: false,
            directSelectable: true,
          },
          connectedSetEntry: {
            available: true,
            requestedDeltaId: "delta-01",
          },
        },
      ],
    },
  ],
  acceptanceState: { reviewStage: "draft" },
  activation: {
    status: "not_requested",
    actionAvailable: false,
    downstreamWorkflow: { workflowState: "not_started" },
  },
  blockedAcceptance: {
    message: "Connected set selection is required before isolated acceptance is safe.",
  },
  warningTrustContext: { activeSignalCount: 1 },
  navigation: {
    returnNavigation: {
      screen: { id: "S03", label: "Resource Detail" },
      originScope: {
        scopeType: "resource",
        scopeId: "resource-ada",
        scopeExternalId: "user-ada",
        scopeLabel: "Ada Lovelace",
      },
    },
    warningReview: {
      available: true,
      screen: { id: "S05", label: "Planning Warnings Workspace" },
    },
  },
};

const m01Payload = {
  screen: { id: "M01", label: "Connected Change Set Modal" },
  queryContext: { reviewContextId: "review-context-01", requestedDeltaId: "delta-01" },
  viewState: {
    screenState: "ready",
    isRefreshing: false,
    accessRestricted: false,
    accessRestrictedReason: null,
  },
  requestedDelta: { deltaId: "delta-01", entityName: "Implementation task" },
  blockingReason: {
    code: "connected_set_required",
    message: "This delta must be accepted with its connected set.",
  },
  connectedSet: {
    memberItems: [{ deltaId: "delta-01", entityName: "Implementation task" }],
  },
  actions: { selectConnectedSetAvailable: true, deselectConnectedSetAvailable: true },
  navigation: {},
};

const s05Payload = {
  screen: { id: "S05", label: "Planning Warnings Workspace" },
  queryContext: { planningContextKey: "context::frontend-shell", sourceSnapshotId: "snapshot-01", originScreenId: "S04" },
  viewState: { screenState: "no_warnings", isLoading: false, isRefreshing: false, accessRestricted: false, accessRestrictedReason: null },
  workspaceSummary: {
    filteredSignalCount: 0,
    blockingWarningCount: 0,
    advisoryWarningCount: 0,
    trustLimitedCount: 0,
  },
  filterState: {
    groupBy: "affected_workflow",
    activeWorkflowIds: [],
    activeClassificationFilters: [],
    activeSignalTypes: [],
    availableFilters: {
      workflowOptions: [],
      classificationOptions: [],
      signalTypeOptions: [],
    },
  },
  groupSummaries: [],
  warningItems: [],
  trustGuidance: [],
  returnNavigation: { screen: { id: "S04", label: "Delta Review" } },
  emptyState: { message: "There are no interpreted warnings or trust-limited states in the current scope." },
};

function buildRichS05Payload({
  originScreenId = "S04",
  originScope = {
    scopeType: "review",
    scopeId: "review-context-01",
    scopeExternalId: "review-context-01",
    scopeLabel: "Current review context",
  },
  activeWorkflowIds = ["S04"],
  classificationFilters = [],
} = {}) {
  const allItems = [
    {
      itemId: "warning-item-01",
      code: "dependency_safe_approval_blocked",
      message: "A connected set is still required before isolated acceptance is safe.",
      classification: "blocking",
      classificationLabel: "Blocking",
      signalType: "warning",
      affectedWorkflow: { id: "S04", label: "Delta Review" },
      affectedScope: {
        scopeType: "review",
        scopeId: "review-context-01",
        scopeExternalId: "review-context-01",
        scopeLabel: "Current review context",
      },
      navigationTarget: { screen: { id: "S04", label: "Delta Review" } },
      trustGuidance: { present: false, title: null, message: null },
    },
    {
      itemId: "warning-item-02",
      code: "resource_trust_limited",
      message: "One resource interpretation is trust-limited and should be reviewed carefully.",
      classification: "trust_limited",
      classificationLabel: "Trust-limited",
      signalType: "trust",
      affectedWorkflow: { id: "S03", label: "Resource Detail" },
      affectedScope: {
        scopeType: "resource",
        scopeId: "resource-ada",
        scopeExternalId: "user-ada",
        scopeLabel: "Ada Lovelace",
      },
      navigationTarget: { screen: { id: "S03", label: "Resource Detail" } },
      trustGuidance: {
        present: true,
        title: "Trust-limited interpretation",
        message: "Treat the current recommendation and warning interpretation with additional care.",
      },
    },
  ];

  const filteredItems = classificationFilters.length
    ? allItems.filter((item) => classificationFilters.includes(item.classification))
    : allItems;

  const workflowCounts = new Map();
  filteredItems.forEach((item) => {
    const workflowId = item.affectedWorkflow.id;
    const existing = workflowCounts.get(workflowId) || {
      workflowId,
      workflowLabel: item.affectedWorkflow.label,
      itemCount: 0,
      blockingCount: 0,
      advisoryCount: 0,
      trustLimitedCount: 0,
    };
    existing.itemCount += 1;
    if (item.classification === "blocking") {
      existing.blockingCount += 1;
    } else if (item.classification === "trust_limited") {
      existing.trustLimitedCount += 1;
    } else {
      existing.advisoryCount += 1;
    }
    workflowCounts.set(workflowId, existing);
  });

  return {
    ...s05Payload,
    queryContext: {
      planningContextKey: "context::frontend-shell",
      sourceSnapshotId: "snapshot-01",
      originScreenId,
      originScope,
    },
    viewState: {
      screenState: filteredItems.length ? "warning_heavy" : "no_warnings",
      isLoading: false,
      isRefreshing: false,
      accessRestricted: false,
      accessRestrictedReason: null,
    },
    workspaceSummary: {
      filteredSignalCount: filteredItems.length,
      blockingWarningCount: filteredItems.filter((item) => item.classification === "blocking").length,
      advisoryWarningCount: filteredItems.filter((item) => item.classification === "advisory").length,
      trustLimitedCount: filteredItems.filter((item) => item.classification === "trust_limited").length,
    },
    filterState: {
      groupBy: "affected_workflow",
      activeWorkflowIds,
      activeClassificationFilters: classificationFilters,
      activeSignalTypes: [],
      availableFilters: {
        workflowOptions: [
          { workflowId: "S04", workflowLabel: "Delta Review", count: 1 },
          { workflowId: "S03", workflowLabel: "Resource Detail", count: 1 },
        ],
        classificationOptions: [
          { id: "blocking", label: "Blocking", count: 1 },
          { id: "trust_limited", label: "Trust-limited", count: 1 },
        ],
        signalTypeOptions: [
          { id: "warning", label: "Warning", count: 1 },
          { id: "trust", label: "Trust", count: 1 },
        ],
      },
    },
    groupSummaries: Array.from(workflowCounts.values()),
    warningItems: filteredItems,
    trustGuidance: filteredItems
      .filter((item) => item.trustGuidance.present)
      .map((item) => ({
        guidanceId: `guidance::${item.code}`,
        title: item.trustGuidance.title,
        message: item.trustGuidance.message,
        relatedItemCount: 1,
      })),
    returnNavigation: {
      screen: {
        id: originScreenId,
        label:
          originScreenId === "S01"
            ? "Portfolio Swimlane Home"
            : originScreenId === "S02"
              ? "Planning Setup"
              : originScreenId === "S03"
                ? "Resource Detail"
                : "Delta Review",
      },
      scope: originScope,
    },
    emptyState: filteredItems.length
      ? null
      : { message: "There are no interpreted warnings or trust-limited states in the current scope." },
  };
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("frontend MVP shell", () => {
  it("boots the shell and renders the default S01 route", async () => {
    global.fetch = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s01/portfolio": s01Payload,
    });

    renderAt("/");

    expect(await screen.findByRole("heading", { name: "Portfolio Swimlane Home" })).toBeInTheDocument();
    expect(screen.getByText("S01 Portfolio")).toBeInTheDocument();
    expect(screen.getByText("BFF reachable")).toBeInTheDocument();
  });

  it("supports route reachability across S01 to S05 through screen-owned navigation", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        resourceExternalId: "user-ada",
        reviewContextId: "review-context-01",
        approvedPlanId: "",
        activationId: "",
        planningWorkflowInstanceId: "",
        warningOriginScreenId: "S04",
      }),
    );
    global.fetch = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s02/setup": {
        ...s02Payload,
        queryContext: { planningContextKey: "context::frontend-shell", sourceSnapshotId: "snapshot-01" },
        viewState: { ...s02Payload.viewState, screenState: "ready" },
        sourceReadiness: { ...s02Payload.sourceReadiness, state: "ready", runnable: true },
        capacityInputReadiness: { ...s02Payload.capacityInputReadiness, state: "ready", runnable: true },
        overallReadiness: {
          ...s02Payload.overallReadiness,
          state: "ready",
          runnable: true,
          canContinueToPlanning: true,
          noRunnablePlanBlockerCount: 0,
        },
      },
      "GET /api/screens/s01/portfolio": s01Payload,
      "GET /api/screens/s03/resource-detail": s03Payload,
      "GET /api/screens/s04/delta-review": s04Payload,
      "GET /api/screens/s05/warnings-workspace": s05Payload,
    });

    renderAt("/s02");

    expect(await screen.findByRole("heading", { name: "Planning Setup" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue to S01" }));
    expect(await screen.findByRole("heading", { name: "Portfolio Swimlane Home" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open S03 from segment" }));
    expect(await screen.findByRole("heading", { name: "Resource Detail" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Go to S04" }));
    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open S05" }));
    expect(await screen.findByRole("heading", { name: "Planning Warnings Workspace" })).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "There are no interpreted warnings or trust-limited states in the current scope.",
      ),
    ).not.toHaveLength(0);
  });

  it("uses a screen-owned S01 action to enter S04 review with origin context", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s01/portfolio": s01Payload,
      "GET /api/screens/s04/delta-review": (url) => {
        expect(url.searchParams.get("originScreenId")).toBe("S01");
        expect(url.searchParams.get("originScopeType")).toBe("portfolio");
        expect(url.searchParams.get("originScopeLabel")).toBe("Portfolio");
        return jsonResponse({
          ...s04Payload,
          queryContext: {
            ...s04Payload.queryContext,
            originScreenId: "S01",
            originScope: {
              scopeType: "portfolio",
              scopeId: null,
              scopeExternalId: null,
              scopeLabel: "Portfolio",
            },
          },
          navigation: {
            ...s04Payload.navigation,
            returnNavigation: {
              screen: { id: "S01", label: "Portfolio Swimlane Home" },
              originScope: {
                scopeType: "portfolio",
                scopeId: null,
                scopeExternalId: null,
                scopeLabel: "Portfolio",
              },
            },
          },
        });
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
      }),
    );

    renderAt("/s01");

    expect(await screen.findByRole("heading", { name: "Portfolio Swimlane Home" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open S04 review" }));

    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to S01" })).toBeInTheDocument();
  });

  it("opens D01 from S01 and maps swimlane context into the drawer route", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s01/portfolio": s01Payload,
      "GET /api/drawers/d01/task-drilldown": (url) => {
        expect(url.searchParams.get("resourceExternalId")).toBe("user-ada");
        expect(url.searchParams.get("date")).toBe("2026-04-08");
        return jsonResponse(d01Payload);
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
      }),
    );

    renderAt("/s01");

    expect(await screen.findByRole("heading", { name: "Portfolio Swimlane Home" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open D01" }));

    expect(await screen.findByRole("heading", { name: "Swimlane Task Drill-Down Drawer" })).toBeInTheDocument();
    expect(screen.getByText("Prepare launch report")).toBeInTheDocument();
  });

  it("keeps S02 planning-run admission blocked until readiness is runnable", async () => {
    global.fetch = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s02/setup": {
        ...s02Payload,
        queryContext: {
          planningContextKey: "context::frontend-shell",
          sourceSnapshotId: "snapshot-01",
        },
      },
    });

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
      }),
    );

    renderAt("/s02");

    expect(await screen.findByRole("heading", { name: "Planning Setup" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start planning run" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Continue to S01" })).toBeDisabled();
  });

  it("routes S01 warning review into S05 with the correct origin context", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s01/portfolio": s01Payload,
      "GET /api/screens/s05/warnings-workspace": (url) => {
        expect(url.searchParams.get("originScreenId")).toBe("S01");
        expect(url.searchParams.get("originScopeType")).toBeNull();
        expect(url.searchParams.get("originScopeId")).toBeNull();
        return jsonResponse({
          ...s05Payload,
          queryContext: {
            ...s05Payload.queryContext,
            originScreenId: "S01",
          },
          returnNavigation: {
            screen: { id: "S01", label: "Portfolio Swimlane Home" },
          },
        });
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
      }),
    );

    renderAt("/s01");

    expect(await screen.findByRole("heading", { name: "Portfolio Swimlane Home" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review warnings" }));

    expect(await screen.findByRole("heading", { name: "Planning Warnings Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to S01" })).toBeInTheDocument();
  });

  it("routes S02 warning review into S05 with the correct origin context", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s02/setup": s02Payload,
      "GET /api/screens/s05/warnings-workspace": (url) => {
        expect(url.searchParams.get("originScreenId")).toBe("S02");
        expect(url.searchParams.get("originScopeType")).toBeNull();
        expect(url.searchParams.get("originScopeId")).toBeNull();
        return jsonResponse({
          ...s05Payload,
          queryContext: {
            ...s05Payload.queryContext,
            originScreenId: "S02",
          },
          returnNavigation: {
            screen: { id: "S02", label: "Planning Setup" },
          },
        });
      },
    });
    global.fetch = fetchMock;

    renderAt("/s02");

    expect(await screen.findByRole("heading", { name: "Planning Setup" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review warnings" }));

    expect(await screen.findByRole("heading", { name: "Planning Warnings Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to S02" })).toBeInTheDocument();
  });

  it("routes S03 warning review into S05 with scoped resource context", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s03/resource-detail": s03Payload,
      "GET /api/screens/s05/warnings-workspace": (url) => {
        expect(url.searchParams.get("originScreenId")).toBe("S03");
        expect(url.searchParams.get("originScopeType")).toBe("resource");
        expect(url.searchParams.get("originScopeExternalId")).toBe("user-ada");
        return jsonResponse(
          buildRichS05Payload({
            originScreenId: "S03",
            originScope: {
              scopeType: "resource",
              scopeId: "resource-ada",
              scopeExternalId: "user-ada",
              scopeLabel: "Ada Lovelace",
            },
          }),
        );
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        resourceExternalId: "user-ada",
      }),
    );

    renderAt("/s03");

    expect(await screen.findByRole("heading", { name: "Resource Detail" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open S05" }));

    expect(await screen.findByRole("heading", { name: "Planning Warnings Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to S03" })).toBeInTheDocument();
  });

  it("opens M01 from S04 and renders the connected set modal", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s04/delta-review": s04Payload,
      "GET /api/modals/m01/connected-change-set": (url) => {
        expect(url.searchParams.get("reviewContextId")).toBe("review-context-01");
        expect(url.searchParams.get("requestedDeltaId")).toBe("delta-01");
        return jsonResponse(m01Payload);
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        reviewContextId: "review-context-01",
      }),
    );

    renderAt("/s04");

    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open M01" }));

    expect(await screen.findByRole("heading", { name: "Connected Change Set Modal" })).toBeInTheDocument();
    expect(screen.getByText("This delta must be accepted with its connected set.")).toBeInTheDocument();
  });

  it("hydrates the visible S04 review context into shell state for M01 and activation actions", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s04/delta-review": {
        ...s04Payload,
        activation: {
          status: "ready_to_activate",
          actionAvailable: true,
          downstreamWorkflow: { workflowState: "not_started" },
        },
      },
      "GET /api/modals/m01/connected-change-set": (url) => {
        expect(url.searchParams.get("reviewContextId")).toBe("review-context-01");
        return jsonResponse(m01Payload);
      },
      "POST /api/screens/s04/activation": (_url, init) => {
        const body = JSON.parse(init.body);
        expect(body.reviewContextId).toBe("review-context-01");
        return jsonResponse({
          activationId: "activation-01",
        });
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
      }),
    );

    renderAt("/s04");

    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Review context: review context attached")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Open M01" }));
    expect(await screen.findByRole("heading", { name: "Connected Change Set Modal" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Connected Change Set Modal" })).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Activate accepted changes" }));
    expect(await screen.findByText("Activation command returned")).toBeInTheDocument();
    expect(await screen.findByText("Activation ID: activation-01")).toBeInTheDocument();
  });

  it("submits the M01 connected-set selection through the BFF transport", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s04/delta-review": s04Payload,
      "GET /api/modals/m01/connected-change-set": m01Payload,
      "POST /api/modals/m01/connected-change-set/acceptance-selection": (_url, init) => {
        const body = JSON.parse(init.body);
        expect(body.reviewContextId).toBe("review-context-01");
        expect(body.requestedDeltaId).toBe("delta-01");
        expect(body.selected).toBe(true);
        return jsonResponse({
          screen: { id: "M01", label: "Connected Change Set Modal" },
          status: "applied",
        });
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        reviewContextId: "review-context-01",
      }),
    );

    renderAt("/s04");

    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open M01" }));
    expect(await screen.findByRole("heading", { name: "Connected Change Set Modal" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Select connected set" }));

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Connected Change Set Modal" })).not.toBeInTheDocument();
    });
  });

  it("submits the S04 acceptance-selection command and launches M01 when blocked", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s04/delta-review": s04Payload,
      "POST /api/screens/s04/acceptance-selection": (_url, init) => {
        const body = JSON.parse(init.body);
        expect(body.reviewContextId).toBe("review-context-01");
        expect(body.deltaId).toBe("delta-01");
        expect(body.selected).toBe(true);
        return jsonResponse({
          modalLaunch: {
            available: true,
            requestedDeltaId: "delta-01",
          },
        });
      },
      "GET /api/modals/m01/connected-change-set": m01Payload,
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        reviewContextId: "review-context-01",
      }),
    );

    renderAt("/s04");

    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select" }));

    expect(await screen.findByRole("heading", { name: "Connected Change Set Modal" })).toBeInTheDocument();
  });

  it("submits the S04 acceptance-selection command and stays on S04 when applied directly", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s04/delta-review": s04Payload,
      "POST /api/screens/s04/acceptance-selection": (_url, init) => {
        const body = JSON.parse(init.body);
        expect(body.reviewContextId).toBe("review-context-01");
        expect(body.deltaId).toBe("delta-01");
        expect(body.selected).toBe(true);
        return jsonResponse({
          status: "applied",
          modalLaunch: {
            available: false,
          },
        });
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        reviewContextId: "review-context-01",
      }),
    );

    renderAt("/s04");

    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Select" }));

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Connected Change Set Modal" })).not.toBeInTheDocument();
    });
  });

  it("returns from S04 to the originating S03 context", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s04/delta-review": (url) => {
        expect(url.searchParams.get("originScreenId")).toBe("S03");
        expect(url.searchParams.get("originScopeExternalId")).toBe("user-ada");
        return jsonResponse({
          ...s04Payload,
          queryContext: {
            ...s04Payload.queryContext,
            originScreenId: "S03",
            originScope: {
              scopeType: "resource",
              scopeId: "resource-ada",
              scopeExternalId: "user-ada",
              scopeLabel: "Ada Lovelace",
            },
          },
        });
      },
      "GET /api/screens/s03/resource-detail": (url) => {
        expect(url.searchParams.get("resourceExternalId")).toBe("user-ada");
        return jsonResponse(s03Payload);
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        reviewContextId: "review-context-01",
        resourceExternalId: "user-ada",
        reviewOriginScreenId: "S03",
        reviewOriginScopeType: "resource",
        reviewOriginScopeId: "resource-ada",
        reviewOriginScopeExternalId: "user-ada",
        reviewOriginScopeLabel: "Ada Lovelace",
      }),
    );

    renderAt("/s04");

    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to S03" }));

    expect(await screen.findByRole("heading", { name: "Resource Detail" })).toBeInTheDocument();
  });

  it("routes S04 warning review into S05 with scoped review context", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s04/delta-review": s04Payload,
      "GET /api/screens/s05/warnings-workspace": (url) => {
        expect(url.searchParams.get("originScreenId")).toBe("S04");
        expect(url.searchParams.get("originScopeType")).toBe("review");
        expect(url.searchParams.get("originScopeExternalId")).toBe("review-context-01");
        return jsonResponse(buildRichS05Payload());
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        reviewContextId: "review-context-01",
      }),
    );

    renderAt("/s04");

    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open S05" }));

    expect(await screen.findByRole("heading", { name: "Planning Warnings Workspace" })).toBeInTheDocument();
    expect(screen.getByText("Trust guidance")).toBeInTheDocument();
  });

  it("keeps the last successful payload visible when a refresh request fails", async () => {
    const user = userEvent.setup();
    let requestCount = 0;
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s05/warnings-workspace": () => {
        requestCount += 1;
        if (requestCount === 1) {
          return jsonResponse(buildRichS05Payload());
        }
        return jsonResponse(
          {
            error: {
              code: "refresh_failed",
              message: "The warnings workspace refresh failed.",
            },
          },
          500,
        );
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        warningOriginScreenId: "S04",
      }),
    );

    renderAt("/s05");

    expect(await screen.findByText("dependency_safe_approval_blocked")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh warnings" }));

    expect(await screen.findByText("The warnings workspace refresh failed.")).toBeInTheDocument();
    expect(screen.getByText("dependency_safe_approval_blocked")).toBeInTheDocument();
  });

  it("renders grouped warnings, trust guidance, and filter-driven refresh on S05", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s05/warnings-workspace": (url) => {
        const classificationFilters = url.searchParams.getAll("classificationFilter");
        return jsonResponse(
          buildRichS05Payload({
            classificationFilters,
          }),
        );
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        warningOriginScreenId: "S04",
      }),
    );

    renderAt("/s05");

    expect(await screen.findByRole("heading", { name: "Planning Warnings Workspace" })).toBeInTheDocument();
    expect(screen.getByText("Affected workflow groups")).toBeInTheDocument();
    expect(screen.getByText("Trust guidance")).toBeInTheDocument();
    expect(screen.getAllByText("Delta Review").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Blocking (1)" }));

    await waitFor(() => {
      expect(
        screen.queryByText("Treat the current recommendation and warning interpretation with additional care."),
      ).not.toBeInTheDocument();
    });
    expect(
      screen.getByText("A connected set is still required before isolated acceptance is safe."),
    ).toBeInTheDocument();
  });

  it("keeps the S05 group summary panel aligned when BFF group summaries are incomplete", async () => {
    const incompleteSummaryPayload = buildRichS05Payload();
    global.fetch = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s05/warnings-workspace": {
        ...incompleteSummaryPayload,
        groupSummaries: incompleteSummaryPayload.groupSummaries.slice(0, 1),
      },
    });

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        warningOriginScreenId: "S04",
      }),
    );

    renderAt("/s05");

    expect(await screen.findByText("2 workflow groups")).toBeInTheDocument();
    expect(screen.getAllByText("Delta Review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Resource Detail").length).toBeGreaterThan(0);
    expect(await screen.findByText("dependency_safe_approval_blocked")).toBeInTheDocument();
    expect(screen.getByText("resource_trust_limited")).toBeInTheDocument();
  });

  it("submits the S02 import-sync command through the BFF transport", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s02/setup": s02Payload,
      "POST /api/screens/s02/import-sync": (_url, init) => {
        const body = JSON.parse(init.body);
        expect(body.rawPayload).toEqual({ source_system: "asana" });
        expect(body.requestedBy).toBe("planner@example.com");
        return jsonResponse(
          {
            workflow_instance: {
              current_status: "dispatched",
            },
            source_snapshot_id: "snapshot-02",
          },
          202,
        );
      },
    });
    global.fetch = fetchMock;

    renderAt("/s02");

    expect(await screen.findByRole("heading", { name: "Planning Setup" })).toBeInTheDocument();
    await user.click(screen.getByText("Start import / sync from a source payload"));
    await user.click(screen.getByRole("button", { name: "Start import / sync" }));

    expect(await screen.findByText("Import/sync admitted")).toBeInTheDocument();
    expect(screen.getByText(/Snapshot: snapshot-02/)).toBeInTheDocument();
  });

  it("shows a local validation error when S02 import payload JSON is invalid", async () => {
    const user = userEvent.setup();
    global.fetch = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s02/setup": s02Payload,
    });

    renderAt("/s02");

    expect(await screen.findByRole("heading", { name: "Planning Setup" })).toBeInTheDocument();
    await user.click(screen.getByText("Start import / sync from a source payload"));
    const textarea = screen.getByRole("textbox", { name: "Source plan payload" });
    await user.clear(textarea);
    await user.click(textarea);
    await user.paste('{"source_system"');
    await user.click(screen.getByRole("button", { name: "Start import / sync" }));

    expect(await screen.findByText("Raw payload must be valid JSON.")).toBeInTheDocument();
  });

  it("submits the S03 recommendation-refresh command through the BFF transport", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s03/resource-detail": s03Payload,
      "POST /api/screens/s03/recommendation-context/refresh": (_url, init) => {
        const body = JSON.parse(init.body);
        expect(body.planningRunId).toBe("planning-run-01");
        expect(body.resourceExternalId).toBe("user-ada");
        return jsonResponse({
          contextId: "recommendation-context-01",
        });
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        resourceExternalId: "user-ada",
      }),
    );

    renderAt("/s03");

    expect(await screen.findByRole("heading", { name: "Resource Detail" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh recommendation context" }));

    expect(await screen.findByText("Recommendation context refreshed")).toBeInTheDocument();
  });

  it("renders an access-restricted warning workspace state from the BFF payload", async () => {
    global.fetch = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s05/warnings-workspace": {
        ...s05Payload,
        viewState: {
          screenState: "access_restricted",
          isLoading: false,
          isRefreshing: false,
          accessRestricted: true,
          accessRestrictedReason: "scope_denied",
        },
        emptyState: null,
      },
    });

    renderAt("/s05");

    expect(await screen.findByRole("heading", { name: "Planning Warnings Workspace" })).toBeInTheDocument();
    expect(screen.getByText("access_restricted")).toBeInTheDocument();
  });

  it("shows a loading state while a screen route is pending", async () => {
    const deferred = deferredResponse();
    global.fetch = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s02/setup": deferred.promise,
    });

    renderAt("/s02");

    expect(screen.getByText("Loading S02 setup readiness.")).toBeInTheDocument();
    deferred.resolve(s02Payload);

    expect(await screen.findByRole("heading", { name: "Planning Setup" })).toBeInTheDocument();
  });

  it("submits S04 activation through its dedicated command path", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s04/delta-review": {
        ...s04Payload,
        activation: {
          status: "ready_to_activate",
          actionAvailable: true,
          downstreamWorkflow: { workflowState: "not_started" },
        },
      },
      "POST /api/screens/s04/activation": (_url, init) => {
        const body = JSON.parse(init.body);
        expect(body.reviewContextId).toBe("review-context-01");
        return jsonResponse({
          activationId: "activation-01",
        });
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
        planningRunId: "planning-run-01",
        reviewContextId: "review-context-01",
      }),
    );

    renderAt("/s04");

    expect(await screen.findByRole("heading", { name: "Delta Review" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Activate accepted changes" }));

    expect(await screen.findByText("Activation command returned")).toBeInTheDocument();
    expect(await screen.findByText("Activation ID: activation-01")).toBeInTheDocument();
  });

  it("submits the S02 planning-run command and stores the returned planning run id", async () => {
    const user = userEvent.setup();
    const fetchMock = buildFetchMock({
      "GET /health": { status: "ok" },
      "GET /api/screens/s02/setup": {
        ...s02Payload,
        queryContext: { planningContextKey: "context::frontend-shell", sourceSnapshotId: "snapshot-01" },
        viewState: { ...s02Payload.viewState, screenState: "ready" },
        sourceReadiness: { ...s02Payload.sourceReadiness, state: "ready", runnable: true },
        capacityInputReadiness: { ...s02Payload.capacityInputReadiness, state: "ready", runnable: true },
        overallReadiness: { ...s02Payload.overallReadiness, state: "ready", runnable: true, canContinueToPlanning: true, noRunnablePlanBlockerCount: 0 },
      },
      "POST /api/screens/s02/planning-runs": (_url, init) => {
        const body = JSON.parse(init.body);
        expect(body.sourceSnapshotId).toBe("snapshot-01");
        expect(body.planningContextKey).toBe("context::frontend-shell");
        return jsonResponse({
          workflow_instance: {
            workflow_instance_id: "workflow-01",
            planning_engine_run_id: "planning-run-99",
          },
        }, 202);
      },
    });
    global.fetch = fetchMock;

    window.localStorage.setItem(
      "capacity-aware-execution-planner.frontend-shell-state",
      JSON.stringify({
        requestedBy: "planner@example.com",
        planningContextKey: "context::frontend-shell",
        sourceSnapshotId: "snapshot-01",
      }),
    );

    renderAt("/s02");

    expect(await screen.findByRole("heading", { name: "Planning Setup" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start planning run" }));

    expect(await screen.findByText("Planning run admitted")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Current planning run: planning-run-99")).toBeInTheDocument();
    });
  });
});
