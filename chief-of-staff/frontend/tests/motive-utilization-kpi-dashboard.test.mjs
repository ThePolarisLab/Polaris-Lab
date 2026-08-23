import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { motiveUtilizationKpiPresentation } from "../src/motiveFrontend.js";

const partialPayload = {
  status: "available_observed",
  kpi: "observed_7_day_vehicle_utilization",
  window_start: "2026-08-15",
  window_end: "2026-08-21",
  request_timezone: "America/Chicago",
  value_percent: 46.74,
  expected_requested_vehicle_days: 161,
  metric_valid_vehicle_days: 68,
  utilization_metric_coverage_percent: 42.24,
  fleet_representative: false,
};

test("presents partial observed utilization with coverage and neutral representativeness wording", () => {
  const presentation = motiveUtilizationKpiPresentation(partialPayload);
  assert.equal(presentation.status, "available_observed");
  assert.equal(presentation.title, "Observed 7-Day Vehicle Utilization");
  assert.equal(presentation.value, "46.74%");
  assert.equal(presentation.coverage, "68 / 161 vehicle-days (42.24%)");
  assert.equal(presentation.completeness, "Partial observation — not fleet representative");
  assert.equal(presentation.window, "2026-08-15 to 2026-08-21 · America/Chicago");
});

test("preserves returned zero utilization as a valid observed value", () => {
  const presentation = motiveUtilizationKpiPresentation({
    ...partialPayload,
    value_percent: 0,
    expected_requested_vehicle_days: 7,
    metric_valid_vehicle_days: 7,
    utilization_metric_coverage_percent: 100,
    fleet_representative: true,
  });
  assert.equal(presentation.value, "0.00%");
  assert.equal(presentation.coverage, "7 / 7 vehicle-days (100.00%)");
  assert.equal(presentation.completeness, "Full vehicle-day coverage");
});

test("renders unavailable and request-failure states without inventing zero utilization", () => {
  const unavailable = motiveUtilizationKpiPresentation({ status: "unavailable", value_percent: 0 });
  assert.equal(unavailable.value, "Unavailable");
  assert.equal(unavailable.coverage, null);
  assert.match(unavailable.completeness, /No certified utilization metric/i);

  const failed = motiveUtilizationKpiPresentation(null, { requestFailed: true });
  assert.equal(failed.value, "Unavailable");
  assert.equal(failed.coverage, null);
  assert.equal(failed.completeness, "Utilization reporting temporarily unavailable.");
});

test("fails closed on malformed available-observed KPI payloads", () => {
  const malformed = motiveUtilizationKpiPresentation({
    ...partialPayload,
    expected_requested_vehicle_days: 0,
  });
  assert.equal(malformed.status, "unavailable");
  assert.equal(malformed.value, "Unavailable");
});

test("dashboard places the read-only Fleet / Operations card between summary and attention sections", async () => {
  const source = await readFile(new URL("../src/components/ExecutiveDashboard.jsx", import.meta.url), "utf8");
  const summaryIndex = source.indexOf('className="summary-strip"');
  const cardIndex = source.indexOf("<UtilizationKpiCard presentation={utilizationPresentation} />");
  const attentionIndex = source.indexOf('className="dashboard-grid"');

  assert.ok(summaryIndex >= 0);
  assert.ok(cardIndex > summaryIndex);
  assert.ok(attentionIndex > cardIndex);
  assert.match(source, /apiClient\.get\("\/api\/v1\/motive\/fleet\/vehicle-utilization-kpi"\)/);
  assert.match(source, /Promise\.allSettled\(\[loadDashboard\(\), loadUtilizationKpi\(\)\]\)/);
  assert.doesNotMatch(source, /apiClient\.(?:post|delete)\("\/api\/v1\/motive\//);
});

test("utilization card itself carries no severity, threshold, or action semantics", async () => {
  const source = await readFile(new URL("../src/components/ExecutiveDashboard.jsx", import.meta.url), "utf8");
  const start = source.indexOf("function UtilizationKpiCard");
  const end = source.indexOf("function AddActionForm");
  const cardSource = source.slice(start, end);

  assert.match(cardSource, /FLEET \/ OPERATIONS/);
  assert.doesNotMatch(cardSource, /severity|critical|high|medium|watch|good|target|sync|verify/i);
});
