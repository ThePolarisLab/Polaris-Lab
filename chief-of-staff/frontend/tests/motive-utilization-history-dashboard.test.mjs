import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  motiveUtilizationHistoryFrontendContract,
  motiveUtilizationHistoryPresentation,
} from "../src/motiveUtilizationHistoryFrontend.js";

const productionSnapshotPayload = {
  kpi: "observed_7_day_vehicle_utilization",
  requested_history_days: 30,
  history_start: "2026-07-24",
  history_end: "2026-08-22",
  request_timezone: "America/Chicago",
  snapshot_count: 1,
  secrets_exposed: false,
  points: [
    {
      window_start: "2026-08-16",
      window_end: "2026-08-22",
      status: "available_observed",
      value_percent: 44.99,
      utilization_metric_coverage_percent: 43.48,
      metric_valid_vehicle_days: 70,
      expected_requested_vehicle_days: 161,
      fleet_representative: false,
    },
  ],
};

function point(windowEnd, valuePercent, options = {}) {
  const {
    windowStart = windowEnd,
    validDays = 7,
    expectedDays = 7,
    coveragePercent = 100,
    representative = true,
    status = "available_observed",
  } = options;
  return {
    window_start: windowStart,
    window_end: windowEnd,
    status,
    value_percent: valuePercent,
    utilization_metric_coverage_percent: coveragePercent,
    metric_valid_vehicle_days: validDays,
    expected_requested_vehicle_days: expectedDays,
    fleet_representative: representative,
  };
}

function history(points) {
  return {
    kpi: "observed_7_day_vehicle_utilization",
    requested_history_days: 30,
    history_start: "2026-07-24",
    history_end: "2026-08-22",
    request_timezone: "America/Chicago",
    snapshot_count: points.length,
    secrets_exposed: false,
    points,
  };
}

test("presents the first production snapshot as one point with no directional line", () => {
  const presentation = motiveUtilizationHistoryPresentation(productionSnapshotPayload);
  assert.equal(presentation.status, "ready");
  assert.equal(presentation.summary, "1 snapshot · 1 usable observation");
  assert.equal(presentation.points.length, 1);
  assert.equal(presentation.segments.length, 0);
  assert.equal(presentation.points[0].valuePercent, 44.99);
  assert.equal(presentation.points[0].coveragePercent, 43.48);
  assert.equal(presentation.points[0].x, motiveUtilizationHistoryFrontendContract.chart.plotRight);
  assert.match(presentation.points[0].label, /70 \/ 161 vehicle-days \(43\.48%\)/);
  assert.match(presentation.points[0].label, /not fleet representative/i);
  assert.equal(presentation.range, "2026-07-24 to 2026-08-22 · America/Chicago");
});

test("zero snapshots render a neutral prospective accumulation state", () => {
  const presentation = motiveUtilizationHistoryPresentation(history([]));
  assert.equal(presentation.status, "empty");
  assert.equal(presentation.points.length, 0);
  assert.equal(presentation.segments.length, 0);
  assert.match(presentation.message, /trend will appear after successful daily utilization snapshots/i);
});

test("valid zero utilization is retained at the zero-percent chart position", () => {
  const presentation = motiveUtilizationHistoryPresentation(history([
    point("2026-08-22", 0),
  ]));
  assert.equal(presentation.status, "ready");
  assert.equal(presentation.points[0].kind, "available");
  assert.equal(presentation.points[0].valuePercent, 0);
  assert.equal(presentation.points[0].y, motiveUtilizationHistoryFrontendContract.chart.plotBottom);
});

test("explicit unavailable snapshot remains non-numeric and breaks line continuity", () => {
  const presentation = motiveUtilizationHistoryPresentation(history([
    point("2026-08-20", 40),
    point("2026-08-21", null, { status: "unavailable" }),
    point("2026-08-22", 45),
  ]));
  assert.equal(presentation.status, "ready");
  assert.equal(presentation.points[1].kind, "unavailable");
  assert.equal(presentation.points[1].y, null);
  assert.equal(presentation.segments.length, 0);
  assert.match(presentation.points[1].label, /Unavailable observation/);
});

test("missing calendar dates remain structural gaps instead of interpolation", () => {
  const presentation = motiveUtilizationHistoryPresentation(history([
    point("2026-08-20", 40),
    point("2026-08-22", 45),
  ]));
  assert.equal(presentation.status, "ready");
  assert.equal(presentation.segments.length, 0);
  assert.ok(presentation.points[1].x > presentation.points[0].x);
});

test("only consecutive available calendar observations receive a straight segment", () => {
  const presentation = motiveUtilizationHistoryPresentation(history([
    point("2026-08-21", 40),
    point("2026-08-22", 45),
  ]));
  assert.equal(presentation.status, "ready");
  assert.equal(presentation.segments.length, 1);
  assert.equal(presentation.segments[0].y1, presentation.points[0].y);
  assert.equal(presentation.segments[0].y2, presentation.points[1].y);
});

test("malformed history fails closed to a neutral unavailable state", () => {
  for (const payload of [
    { ...productionSnapshotPayload, snapshot_count: 2 },
    { ...productionSnapshotPayload, requested_history_days: 31 },
    { ...productionSnapshotPayload, history_start: "2026-07-25" },
    { ...productionSnapshotPayload, points: [{ ...productionSnapshotPayload.points[0], value_percent: 101 }] },
    { ...productionSnapshotPayload, points: [{ ...productionSnapshotPayload.points[0], metric_valid_vehicle_days: 162 }] },
    { ...productionSnapshotPayload, points: [{ ...productionSnapshotPayload.points[0], utilization_metric_coverage_percent: 10 }] },
  ]) {
    const presentation = motiveUtilizationHistoryPresentation(payload);
    assert.equal(presentation.status, "unavailable");
    assert.equal(presentation.points.length, 0);
    assert.match(presentation.message, /temporarily unavailable/i);
  }
});

test("loading and request failure are trend-only neutral states", () => {
  assert.equal(
    motiveUtilizationHistoryPresentation(null, { loading: true }).status,
    "loading"
  );
  const failed = motiveUtilizationHistoryPresentation(null, { requestFailed: true });
  assert.equal(failed.status, "unavailable");
  assert.equal(failed.message, "Utilization history temporarily unavailable.");
});

test("history component uses one fixed authenticated GET and no Motive write/action route", async () => {
  const source = await readFile(new URL("../src/components/MotiveUtilizationHistory.jsx", import.meta.url), "utf8");
  assert.equal((source.match(/\/api\/v1\/motive\/fleet\/vehicle-utilization-kpi\/history\?days=30/g) || []).length, 1);
  assert.match(source, /apiClient\.get\(HISTORY_PATH\)/);
  assert.match(source, /refreshSequence/);
  assert.match(source, /requestFailed/);
  assert.match(source, /Gaps indicate dates with no snapshot/);
  assert.doesNotMatch(source, /apiClient\.(?:post|delete)|\bsync\b|verify|reconcile|scheduler|ingestion/i);
  assert.doesNotMatch(source, /improving|worsening|target|critical|\bwatch\b|\bgood\b|\bbad\b/i);
});

test("Dashboard Refresh advances history once while current Motive reads remain independently settled", async () => {
  const source = await readFile(new URL("../src/components/ExecutiveDashboard.jsx", import.meta.url), "utf8");
  assert.match(source, /setHistoryRefreshSequence\(\(current\) => current \+ 1\)/);
  assert.match(source, /<MotiveUtilizationHistory refreshSequence=\{historyRefreshSequence\} \/>/);
  assert.match(source, /Promise\.allSettled\(\[loadDashboard\(\), loadUtilizationKpi\(\), loadIdleTimeShareKpi\(\), loadIdleFuelShareKpi\(\), loadIdleFuelBurnRateKpi\(\)\]\)/);
});

test("trend styling is responsive and neutral, and no chart dependency is added", async () => {
  const css = await readFile(new URL("../src/components/MotiveUtilizationKpi.css", import.meta.url), "utf8");
  const packageJson = await readFile(new URL("../package.json", import.meta.url), "utf8");
  assert.match(css, /\.utilization-history-chart\s*\{[^}]*width:\s*100%/s);
  assert.match(css, /\.utilization-history-segments line/);
  assert.match(css, /@media \(max-width: 760px\)/);
  assert.doesNotMatch(css, /red|green|amber/i);
  assert.doesNotMatch(packageJson, /recharts|chart\.js|d3|plotly/i);
});
