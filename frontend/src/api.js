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

export async function requestJson(path, { method = "GET", query, body, signal, token } = {}) {
  const storedToken = token || localStorage.getItem("float_token");
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (storedToken) headers["Authorization"] = `Bearer ${storedToken}`;
  const response = await fetch(buildApiUrl(path, query), {
    method,
    headers: Object.keys(headers).length ? headers : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  const payload = await response
    .json()
    .catch(() => ({}));

  if (!response.ok) {
    const error = payload?.error || {};
    // error may be a string (e.g. "Authentication required.") or an object {message, code}
    const errorMessage = typeof error === "string" ? error : (error.message || "Request failed.");
    const errorCode = typeof error === "string" ? "request_failed" : (error.code || "request_failed");
    throw new ApiError(errorMessage, {
      code: errorCode,
      status: response.status,
      payload,
    });
  }

  return payload;
}

export function nowIsoString() {
  return new Date().toISOString();
}
