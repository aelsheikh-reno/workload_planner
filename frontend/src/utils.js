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
      return "No saved context is attached yet. Use the relevant upstream screen action to continue.";
    case "no_data":
      return "This screen has no saved data in the current context yet.";
    case "unavailable":
      return "The referenced context could not be resolved from the current saved planning data.";
    case "blocked":
      return "This surface is currently blocked by an approved blocker condition.";
    case "blocked_isolated_acceptance":
      return "Isolated acceptance is unsafe here. Use the connected-set flow before continuing.";
    case "warning_heavy":
      return "This view is available, but warning density is high and should be reviewed carefully.";
    case "access_restricted":
      return "Access is restricted for the current user or scope.";
    case "no_warnings":
      return "No interpreted warnings or trust-limited signals are active in the current scope.";
    case "no_actionable_recommendation":
      return "Diagnostics are available, but there are currently no actionable recommendation candidates.";
    case "indicator_present":
      return "Planning indicators are present in the current view.";
    case "loading":
      return "The latest state is loading.";
    default:
      return "The current view is available.";
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
