import { runtimeConfig } from "./runtimeConfig";

const ACCESS_TOKEN_KEY = "polaris.access_token";
const ORGANIZATION_KEY = "polaris.organization_id";

export function setAuthSession({ accessToken, organizationId }) {
  if (accessToken) localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  else localStorage.removeItem(ACCESS_TOKEN_KEY);

  if (organizationId) localStorage.setItem(ORGANIZATION_KEY, organizationId);
  else localStorage.removeItem(ORGANIZATION_KEY);
}

export function clearAuthSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(ORGANIZATION_KEY);
}

function authHeaders() {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY) || runtimeConfig.auth.accessToken;
  const organizationId = localStorage.getItem(ORGANIZATION_KEY) || runtimeConfig.auth.organizationId;
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
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }

  return payload;
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
