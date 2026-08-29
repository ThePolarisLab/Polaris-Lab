import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const dispatch = await readFile(new URL("../src/components/DispatchDashboard.jsx", import.meta.url), "utf8");
const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

test("dispatch dashboard is a first-class executive route", () => {
  assert.match(app, /key: "dispatch"/);
  assert.match(app, /label: "Dispatch"/);
  assert.match(app, /<DispatchDashboard \/>/);
});

test("dispatch dashboard reads durable TorqueAI records only", () => {
  assert.match(dispatch, /\/api\/v1\/torqueai\/dispatches\?/);
  assert.match(dispatch, /apiClient\.get/);
  assert.match(dispatch, /TorqueAI provider calls/);
  assert.match(dispatch, /Neon read only · no provider call/);
  assert.doesNotMatch(dispatch, /dispatches\/ingest/);
  assert.doesNotMatch(dispatch, /apiClient\.post/);
  assert.doesNotMatch(dispatch, /setInterval|setTimeout/);
});

test("dispatch dashboard exposes bounded durable filters and pagination", () => {
  assert.match(dispatch, /PAGE_LIMIT = 25/);
  assert.match(dispatch, /params\.set\("from", filters\.from\)/);
  assert.match(dispatch, /params\.set\("to", filters\.to\)/);
  assert.match(dispatch, /params\.set\("status", filters\.status\)/);
  assert.match(dispatch, /params\.set\("customer", filters\.customer\)/);
  assert.match(dispatch, /params\.set\("dispatcher", filters\.dispatcher\)/);
  assert.match(dispatch, />Previous</);
  assert.match(dispatch, />Next</);
});

test("dispatch dashboard keeps deferred sensitive provider fields out of the screen", () => {
  assert.match(dispatch, /Financial fields, billing details, stops, addresses, raw provider payloads/);
  assert.doesNotMatch(dispatch, /total_charge|totalCharge|billing\.|billing\[|street|latitude|longitude/);
});
