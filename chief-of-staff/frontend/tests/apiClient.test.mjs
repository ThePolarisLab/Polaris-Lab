import assert from "node:assert/strict";
import test from "node:test";

const storage = new Map();
const events = [];

globalThis.localStorage = {
  getItem(key) { return storage.has(key) ? storage.get(key) : null; },
  setItem(key, value) { storage.set(key, String(value)); },
  removeItem(key) { storage.delete(key); },
};

globalThis.CustomEvent = class CustomEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.detail = options.detail;
  }
};

globalThis.window = {
  dispatchEvent(event) { events.push(event); return true; },
};

const api = await import("../src/apiClient.js");

function reset() {
  storage.clear();
  events.length = 0;
}

test("attaches bearer token and organization headers", async () => {
  reset();
  api.setAuthSession({ accessToken: "token-1", organizationId: "org-1" });
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  };

  await api.apiClient.get("/protected");

  assert.equal(captured.options.headers.Authorization, "Bearer token-1");
  assert.equal(captured.options.headers["X-Polaris-Organization"], "org-1");
});

test("password login stores access, refresh, and organization", async () => {
  reset();
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return {
      ok: true,
      status: 200,
      json: async () => ({ access_token: "access-1", refresh_token: "refresh-1", organization_id: "org-1" }),
    };
  };

  const session = await api.loginWithPassword({ email: "admin@example.com", password: "secret" });

  assert.equal(captured.url.endsWith("/api/v1/auth/login"), true);
  assert.deepEqual(JSON.parse(captured.options.body), { email: "admin@example.com", password: "secret" });
  assert.equal(session.accessToken, "access-1");
  assert.equal(session.refreshToken, "refresh-1");
  assert.equal(session.organizationId, "org-1");
});

test("bootstrap status and completion call production endpoints", async () => {
  reset();
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/api/v1/auth/bootstrap/status")) {
      return { ok: true, status: 200, json: async () => ({ available: true }) };
    }
    return { ok: true, status: 201, json: async () => ({ status: "completed" }) };
  };

  assert.equal((await api.getBootstrapStatus()).available, true);
  await api.completeBootstrap({ bootstrapSecret: "one-time", password: "CorrectHorseBattery1" });

  assert.equal(calls[1].url.endsWith("/api/v1/auth/bootstrap"), true);
  assert.deepEqual(JSON.parse(calls[1].options.body), { bootstrap_secret: "one-time", password: "CorrectHorseBattery1" });
});

test("sends authenticated delete requests", async () => {
  reset();
  api.setAuthSession({ accessToken: "token-1", organizationId: "org-1" });
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return { ok: true, status: 200, json: async () => ({ disconnected: true }) };
  };

  await api.apiClient.delete("/api/v1/connectors/quickbooks/oauth/connection");

  assert.equal(captured.options.method, "DELETE");
  assert.equal(captured.options.headers.Authorization, "Bearer token-1");
  assert.equal(captured.options.headers["X-Polaris-Organization"], "org-1");
});

test("refreshes once on 401 before retrying protected request", async () => {
  reset();
  api.setAuthSession({ accessToken: "expired", refreshToken: "refresh-1", organizationId: "org-1" });
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/api/v1/auth/refresh")) {
      return { ok: true, status: 200, json: async () => ({ access_token: "access-2", refresh_token: "refresh-2", organization_id: "org-1" }) };
    }
    if (calls.length === 1) {
      return { ok: false, status: 401, json: async () => ({ detail: "credential expired" }) };
    }
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  };

  await api.apiClient.get("/protected");

  assert.equal(calls.length, 3);
  assert.equal(api.getAuthSession().accessToken, "access-2");
  assert.equal(api.getAuthSession().refreshToken, "refresh-2");
});

test("clears session and emits auth change on 401", async () => {
  reset();
  api.setAuthSession({ accessToken: "expired", organizationId: "org-1" });
  globalThis.fetch = async () => ({ ok: false, status: 401, json: async () => ({ detail: "credential expired" }) });

  await assert.rejects(() => api.apiClient.get("/protected"), { name: "ApiError", status: 401 });

  assert.equal(api.getAuthSession().authenticated, false);
  assert.equal(events.at(-1).type, "polaris-auth-changed");
  assert.equal(events.at(-1).detail.reason, "expired");
});

test("emits forbidden event on 403 without clearing session", async () => {
  reset();
  api.setAuthSession({ accessToken: "token-1", organizationId: "org-1" });
  globalThis.fetch = async () => ({ ok: false, status: 403, json: async () => ({ detail: "permission required" }) });

  await assert.rejects(() => api.apiClient.post("/protected", {}), { name: "ApiError", status: 403 });

  assert.equal(api.getAuthSession().authenticated, true);
  assert.equal(events.at(-1).type, "polaris-forbidden");
});

test("logout calls server and clears session", async () => {
  reset();
  api.setAuthSession({ accessToken: "token-1", refreshToken: "refresh-1", organizationId: "org-1" });
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return { ok: true, status: 200, json: async () => ({ revoked: true }) };
  };

  await api.logoutSession();

  assert.equal(captured.url.endsWith("/api/v1/auth/logout"), true);
  assert.equal(captured.options.headers.Authorization, "Bearer token-1");
  assert.equal(api.getAuthSession().authenticated, false);
});

test("reports unauthenticated session for protected screen gating", () => {
  reset();
  assert.equal(api.getAuthSession().authenticated, false);
});