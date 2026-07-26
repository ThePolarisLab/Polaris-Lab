import { runtimeConfig } from "./runtimeConfig";

export async function apiRequest(path, options = {}) {
  const response = await fetch(`${runtimeConfig.apiBaseUrl}${path}`, {
    headers: {
      Accept: "application/json",
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
