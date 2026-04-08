const API_BASE = (import.meta.env.VITE_BFF_BASE_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, { code = "api_error", status = 500, payload = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.payload = payload;
  }
}

export function buildApiUrl(path, query = {}) {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null && item !== "") {
          url.searchParams.append(key, item);
        }
      });
      return;
    }
    url.searchParams.set(key, value);
  });
  if (!API_BASE) {
    return `${url.pathname}${url.search}`;
  }
  return url.toString();
}

export async function requestJson(path, { method = "GET", query, body, signal } = {}) {
  const response = await fetch(buildApiUrl(path, query), {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  const payload = await response
    .json()
    .catch(() => ({}));

  if (!response.ok) {
    const error = payload?.error || {};
    throw new ApiError(error.message || "Request failed.", {
      code: error.code || "request_failed",
      status: response.status,
      payload,
    });
  }

  return payload;
}

export function nowIsoString() {
  return new Date().toISOString();
}
