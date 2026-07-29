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

test("reports unauthenticated session for protected screen gating", () => {
  reset();
  assert.equal(api.getAuthSession().authenticated, false);
});
