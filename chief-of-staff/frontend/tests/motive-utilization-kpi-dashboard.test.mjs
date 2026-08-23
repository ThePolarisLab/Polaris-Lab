import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  motiveIdleTimeShareKpiPresentation,
  motiveUtilizationKpiPresentation,
} from "../src/motiveFrontend.js";

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

const idlePartialPayload = {
  status: "available_observed",
  kpi: "observed_7_day_vehicle_idle_time_share",
  window_start: "2026-08-15",
  window_end: "2026-08-21",
  request_timezone: "America/Chicago",
  value_percent: 50.97,
  expected_requested_vehicle_days: 161,
  metric_valid_vehicle_days: 68,
  idle_time_metric_coverage_percent: 42.24,
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

test("fails closed on malformed available-observed utilization payloads", () => {
  const malformed = motiveUtilizationKpiPresentation({
    ...partialPayload,
    expected_requested_vehicle_days: 0,
  });
  assert.equal(malformed.status, "unavailable");
  assert.equal(malformed.value, "Unavailable");
});

test("presents certified partial idle-time share with coverage and neutral descriptor", () => {
  const presentation = motiveIdleTimeShareKpiPresentation(idlePartialPayload);
  assert.equal(presentation.status, "available_observed");
  assert.equal(presentation.title, "Observed 7-Day Vehicle Idle-Time Share");
  assert.equal(presentation.description, "Share of observed idle + driving time reported as idle.");
  assert.equal(presentation.value, "50.97%");
  assert.equal(presentation.coverage, "68 / 161 vehicle-days (42.24%)");
  assert.equal(presentation.completeness, "Partial observation — not fleet representative");
  assert.equal(presentation.window, "2026-08-15 to 2026-08-21 · America/Chicago");
});

test("preserves valid zero idle-time share", () => {
  const presentation = motiveIdleTimeShareKpiPresentation({
    ...idlePartialPayload,
    value_percent: 0,
    expected_requested_vehicle_days: 7,
    metric_valid_vehicle_days: 7,
    idle_time_metric_coverage_percent: 100,
    fleet_representative: true,
  });
  assert.equal(presentation.status, "available_observed");
  assert.equal(presentation.value, "0.00%");
  assert.equal(presentation.coverage, "7 / 7 vehicle-days (100.00%)");
  assert.equal(presentation.completeness, "Full vehicle-day coverage");
});

test("idle-time unavailable and request failure never invent zero", () => {
  const unavailable = motiveIdleTimeShareKpiPresentation({ status: "unavailable", value_percent: 0 });
  assert.equal(unavailable.value, "Unavailable");
  assert.equal(unavailable.coverage, null);
  assert.match(unavailable.completeness, /No certified idle-time-share metric/i);

  const failed = motiveIdleTimeShareKpiPresentation(null, { requestFailed: true });
  assert.equal(failed.value, "Unavailable");
  assert.equal(failed.coverage, null);
  assert.equal(failed.completeness, "Idle-time-share reporting temporarily unavailable.");
});

test("idle-time presentation fails closed on malformed values and coverage", () => {
  for (const payload of [
    { ...idlePartialPayload, value_percent: 101 },
    { ...idlePartialPayload, value_percent: -1 },
    { ...idlePartialPayload, idle_time_metric_coverage_percent: 101 },
    { ...idlePartialPayload, expected_requested_vehicle_days: 0 },
    { ...idlePartialPayload, metric_valid_vehicle_days: 162 },
    { ...idlePartialPayload, request_timezone: "" },
  ]) {
    const presentation = motiveIdleTimeShareKpiPresentation(payload);
    assert.equal(presentation.status, "unavailable");
    assert.equal(presentation.value, "Unavailable");
  }
});

test("dashboard places both independent read-only KPI observations between summary and attention sections", async () => {
  const source = await readFile(new URL("../src/components/ExecutiveDashboard.jsx", import.meta.url), "utf8");
  const summaryIndex = source.indexOf('className="summary-strip"');
  const cardIndex = source.indexOf("<FleetOperationsCard");
  const attentionIndex = source.indexOf('className="dashboard-grid"');

  assert.ok(summaryIndex >= 0);
  assert.ok(cardIndex > summaryIndex);
  assert.ok(attentionIndex > cardIndex);
  assert.equal((source.match(/apiClient\.get\("\/api\/v1\/motive\/fleet\/vehicle-utilization-kpi"\)/g) || []).length, 1);
  assert.equal((source.match(/apiClient\.get\("\/api\/v1\/motive\/fleet\/vehicle-idle-time-share-kpi"\)/g) || []).length, 1);
  assert.match(source, /Promise\.allSettled\(\[loadDashboard\(\), loadUtilizationKpi\(\), loadIdleTimeShareKpi\(\)\]\)/);
  assert.match(source, /utilizationKpiRequestFailed/);
  assert.match(source, /idleTimeShareKpiRequestFailed/);
  assert.doesNotMatch(source, /apiClient\.(?:post|delete)\("\/api\/v1\/motive\//);
});

test("one Fleet Operations card contains utilization and idle-time-share current observations only", async () => {
  const source = await readFile(new URL("../src/components/ExecutiveDashboard.jsx", import.meta.url), "utf8");
  const start = source.indexOf("function FleetOperationsCard");
  const end = source.indexOf("function AddActionForm");
  const cardSource = source.slice(start, end);

  assert.match(cardSource, /FLEET \/ OPERATIONS/);
  assert.match(cardSource, /Current Observations/);
  assert.match(cardSource, /utilizationPresentation/);
  assert.match(cardSource, /idleTimeSharePresentation/);
  assert.doesNotMatch(cardSource, /severity|critical|\bhigh\b|\bmedium\b|watch|\bgood\b|target|alert|sync|verify|benchmark|waste|avoidable/i);
  assert.doesNotMatch(source, /vehicle-idle-time-share-kpi\/history/);
});

test("Fleet Operations CSS uses two neutral columns and stacks them on narrow screens", async () => {
  const css = await readFile(new URL("../src/components/MotiveUtilizationKpi.css", import.meta.url), "utf8");
  assert.match(css, /grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(css, /@media \(max-width: 760px\)/);
  assert.match(css, /grid-template-columns:\s*1fr/);
  assert.doesNotMatch(css, /#[fF]{2}0000|red|green|amber/i);
});
