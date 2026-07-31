import { runtimeConfig } from "./runtimeConfig.js";

const ACCESS_TOKEN_KEY = "polaris.access_token";
const REFRESH_TOKEN_KEY = "polaris.refresh_token";
const ORGANIZATION_KEY = "polaris.organization_id";

function storage() {
  return globalThis.sessionStorage || globalThis.localStorage;
}

export class ApiError extends Error {
  constructor(message, status, payload = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function getAuthSession() {
  const store = storage();
  const accessToken = store.getItem(ACCESS_TOKEN_KEY) || runtimeConfig.auth.accessToken;
  const refreshToken = store.getItem(REFRESH_TOKEN_KEY) || "";
  const organizationId = store.getItem(ORGANIZATION_KEY) || runtimeConfig.auth.organizationId;
  return { accessToken, refreshToken, organizationId, authenticated: Boolean(accessToken && organizationId) };
}

export function setAuthSession({ accessToken, refreshToken, organizationId }) {
  const store = storage();
  if (accessToken) store.setItem(ACCESS_TOKEN_KEY, accessToken);
  else store.removeItem(ACCESS_TOKEN_KEY);

  if (refreshToken) store.setItem(REFRESH_TOKEN_KEY, refreshToken);
  else if (refreshToken === null) store.removeItem(REFRESH_TOKEN_KEY);

  if (organizationId) store.setItem(ORGANIZATION_KEY, organizationId);
  else store.removeItem(ORGANIZATION_KEY);

  window.dispatchEvent(new CustomEvent("polaris-auth-changed", { detail: getAuthSession() }));
}

export function clearAuthSession(reason = "logout") {
  const store = storage();
  store.removeItem(ACCESS_TOKEN_KEY);
  store.removeItem(REFRESH_TOKEN_KEY);
  store.removeItem(ORGANIZATION_KEY);
  window.dispatchEvent(new CustomEvent("polaris-auth-changed", { detail: { reason, authenticated: false } }));
}

function authHeaders() {
  const { accessToken, organizationId } = getAuthSession();
  const headers = {};

  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (organizationId) headers["X-Polaris-Organization"] = organizationId;

  return headers;
}

function normalizeHeaders(input = {}) {
  const headers = {};
  if (!input) return headers;
  if (typeof Headers !== "undefined" && input instanceof Headers) {
    input.forEach((value, key) => { headers[key] = value; });
    return headers;
  }
  if (Array.isArray(input)) {
    for (const [key, value] of input) headers[key] = value;
    return headers;
  }
  return { ...input };
}

function requestOptions(options = {}) {
  const { headers: suppliedHeaders, ...rest } = options;
  const headers = {
    Accept: "application/json",
    ...normalizeHeaders(suppliedHeaders),
    ...authHeaders(),
  };
  return { ...rest, headers };
}

async function parsePayload(response) {
  return response.json().catch(() => ({}));
}

async function refreshSession() {
  const { refreshToken } = getAuthSession();
  if (!refreshToken) return false;
  const response = await fetch(`${runtimeConfig.apiBaseUrl}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  const payload = await parsePayload(response);
  if (!response.ok) {
    clearAuthSession("expired");
    return false;
  }
  setAuthSession({ accessToken: payload.access_token, refreshToken: payload.refresh_token, organizationId: payload.organization_id });
  return true;
}

export async function apiRequest(path, options = {}, retryOnUnauthorized = true) {
  const response = await fetch(`${runtimeConfig.apiBaseUrl}${path}`, requestOptions(options));

  const payload = await parsePayload(response);

  if (!response.ok) {
    if (response.status === 401 && retryOnUnauthorized && await refreshSession()) {
      return apiRequest(path, options, false);
    }
    const message = payload.detail || payload.message || `Request failed (${response.status})`;
    const error = new ApiError(typeof message === "string" ? message : JSON.stringify(message), response.status, payload);
    if (response.status === 401) clearAuthSession("expired");
    if (response.status === 403) window.dispatchEvent(new CustomEvent("polaris-forbidden", { detail: error }));
    throw error;
  }

  return payload;
}

export async function loginWithLocalToken({ identityId, organizationId }) {
  const response = await apiRequest("/api/v1/auth/local/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identity_id: identityId, organization_id: organizationId }),
  }, false);
  setAuthSession({ accessToken: response.access_token, refreshToken: null, organizationId });
  return getAuthSession();
}

export async function loginWithPassword({ email, password }) {
  const response = await apiRequest("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  }, false);
  setAuthSession({ accessToken: response.access_token, refreshToken: response.refresh_token, organizationId: response.organization_id });
  return getAuthSession();
}

export async function logoutSession() {
  try {
    await apiRequest("/api/v1/auth/logout", { method: "POST" }, false);
  } catch (_) {
    // Local cleanup is still required if the server session is already gone.
  } finally {
    clearAuthSession("logout");
  }
}

export async function getBootstrapStatus() {
  return apiRequest("/api/v1/auth/bootstrap/status", {}, false);
}

export async function completeBootstrap({ bootstrapSecret, password }) {
  return apiRequest("/api/v1/auth/bootstrap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bootstrap_secret: bootstrapSecret, password }),
  }, false);
}

export const apiClient = Object.freeze({
  get(path) {
    return apiRequest(path);
  },
  post(path, body) {
    return apiRequest(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
  },
  delete(path) {
    return apiRequest(path, { method: "DELETE" });
  },
});

export const authStorageKeys = Object.freeze({ ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, ORGANIZATION_KEY });