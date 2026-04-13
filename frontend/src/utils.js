export function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }
  return String(value);
}

export function formatCountLabel(count, singular, plural = `${singular}s`) {
  if (count === null || count === undefined) {
    return `0 ${plural}`;
  }
  return `${count} ${count === 1 ? singular : plural}`;
}

export function toneForScreenState(screenState) {
  if (
    [
      "blocked",
      "blocked_isolated_acceptance",
      "access_restricted",
      "unavailable",
    ].includes(screenState)
  ) {
    return "bad";
  }
  if (["warning_heavy", "indicator_present", "no_actionable_recommendation"].includes(screenState)) {
    return "warn";
  }
  if (["ready", "scheduled"].includes(screenState)) {
    return "good";
  }
  return "muted";
}

export function messageForScreenState(screenState) {
  switch (screenState) {
    case "missing":
      return "No data found. Complete the Setup steps first, then return here.";
    case "no_data":
      return "No data available yet. Run a capacity analysis from Setup to populate this view.";
    case "unavailable":
      return "The requested data could not be found. Try refreshing or check your Setup.";
    case "blocked":
      return "This view is blocked. Resolve the indicated issues before continuing.";
    case "blocked_isolated_acceptance":
      return "This change must be handled together with related changes. Use the 'Related Changes' button.";
    case "warning_heavy":
      return "This view is available, but there are several warnings that should be reviewed.";
    case "access_restricted":
      return "You do not have access to this content.";
    case "no_warnings":
      return "No warnings or trust issues are active in the current scope.";
    case "no_actionable_recommendation":
      return "No actionable recommendations are available at this time.";
    case "indicator_present":
      return "Planning indicators are present. Review the highlighted items below.";
    case "loading":
      return "Loading latest data…";
    default:
      return "This view is ready.";
  }
}

export function summarizeError(error) {
  if (!error) {
    return "Unknown request failure.";
  }
  return error.message || "Unknown request failure.";
}

export function routeForScreenId(screenId) {
  switch (screenId) {
    case "S01":
      return "/s01";
    case "S02":
      return "/s02";
    case "S03":
      return "/s03";
    case "S04":
      return "/s04";
    case "S05":
      return "/s05";
    default:
      return null;
  }
}
