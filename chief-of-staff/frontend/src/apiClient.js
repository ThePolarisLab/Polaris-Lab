import { runtimeConfig } from "./runtimeConfig";

const ACCESS_TOKEN_KEY = "polaris.access_token";
const ORGANIZATION_KEY = "polaris.organization_id";

export class ApiError extends Error {
  constructor(message, status, payload = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function getAuthSession() {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY) || runtimeConfig.auth.accessToken;
  const organizationId = localStorage.getItem(ORGANIZATION_KEY) || runtimeConfig.auth.organizationId;
  return { accessToken, organizationId, authenticated: Boolean(accessToken && organizationId) };
}

export function setAuthSession({ accessToken, organizationId }) {
  if (accessToken) localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  else localStorage.removeItem(ACCESS_TOKEN_KEY);

  if (organizationId) localStorage.setItem(ORGANIZATION_KEY, organizationId);
  else localStorage.removeItem(ORGANIZATION_KEY);

  window.dispatchEvent(new CustomEvent("polaris-auth-changed", { detail: getAuthSession() }));
}

export function clearAuthSession(reason = "logout") {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(ORGANIZATION_KEY);
  window.dispatchEvent(new CustomEvent("polaris-auth-changed", { detail: { reason, authenticated: false } }));
}

function authHeaders() {
  const { accessToken, organizationId } = getAuthSession();
  const headers = {};

  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (organizationId) headers["X-Polaris-Organization"] = organizationId;

  return headers;
}

export async function apiRequest(path, options = {}) {
  const response = await fetch(`${runtimeConfig.apiBaseUrl}${path}`, {
    headers: {
      Accept: "application/json",
      ...authHeaders(),
      ...options.headers,
    },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
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
  });
  setAuthSession({ accessToken: response.access_token, organizationId });
  return getAuthSession();
}

export const apiClient = Object.freeze({
  get(path) {
    return apiRequest(path);
  },
  post(path, body) {
    return apiRequest(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
});

export const authStorageKeys = Object.freeze({ ACCESS_TOKEN_KEY, ORGANIZATION_KEY });
