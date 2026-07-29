import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
const views = await readFile(new URL("../src/components/ExecutiveViews.jsx", import.meta.url), "utf8");

const requiredViews = [
  "DailyBriefView",
  "EvidenceView",
  "DecisionCenterView",
  "ConnectorsView",
  "SystemHealthView",
];

test("all Mission 003 executive views are implemented", () => {
  for (const view of requiredViews) assert.match(views, new RegExp(`export function ${view}`));
});

test("workspace routes render through the governed route component", () => {
  assert.match(app, /ExecutiveRouteView/);
  assert.doesNotMatch(app, /PlaceholderView/);
});

test("observer and evidence governance remain visible", () => {
  assert.match(app, /Observer mode/);
  assert.match(views, /read-only/);
  assert.match(views, /explicit authority/);
});

test("Motive connector remains identified as planned work", () => {
  assert.match(views, /Issue #62/);
});

test("QuickBooks connector reflects live status rather than a placeholder", () => {
  assert.doesNotMatch(views, /Issue #61/);
  assert.match(views, /oauth\/authorize/);
});
