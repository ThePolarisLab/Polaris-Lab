import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
const overview = await readFile(new URL("../src/components/FinancialOverview.jsx", import.meta.url), "utf8");

const requiredMetrics = [
  "Revenue",
  "Total expenses",
  "Gross profit",
  "Net income",
  "Cash position",
  "Accounts receivable",
  "Accounts payable",
];

test("Financial route is available in the Executive Workspace", () => {
  assert.match(app, /key: "financial"/);
  assert.match(app, /<FinancialOverview \/>/);
});

test("Financial overview reads the durable executive summary only", () => {
  assert.match(overview, /apiClient\.get\("\/api\/v1\/qbo\/executive-summary"\)/);
  assert.doesNotMatch(overview, /apiClient\.post/);
  assert.doesNotMatch(overview, /\/api\/v1\/qbo\/sync/);
  assert.match(overview, /does not call QuickBooks or trigger synchronization/);
});

test("Financial overview exposes all reconciliation KPIs with exact currency formatting", () => {
  for (const label of requiredMetrics) assert.match(overview, new RegExp(label));
  assert.match(overview, /moneyExact/);
  assert.match(overview, /metrics_metadata/);
  assert.match(overview, /Accounting basis/);
  assert.match(overview, /Last synchronized/);
});

test("Missing Gross Profit is labeled as provider-unavailable without Polaris derivation", () => {
  assert.match(overview, /Not provided by QuickBooks API/);
  assert.match(overview, /key === "gross_profit"/);
  assert.doesNotMatch(overview, /Cost of Goods Sold/);
  assert.doesNotMatch(overview, /Total Income -/);
});
