const HISTORY_KPI = "observed_7_day_vehicle_utilization";
const HISTORY_DAYS = 30;
const DAY_MS = 24 * 60 * 60 * 1000;

const CHART = Object.freeze({
  width: 720,
  height: 190,
  plotLeft: 48,
  plotRight: 704,
  plotTop: 18,
  plotBottom: 136,
  unavailableY: 154,
  xLabelY: 181,
});

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0 ? value : null;
}

function parseIsoDay(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  const timestamp = Date.UTC(year, month - 1, day);
  if (!Number.isFinite(timestamp)) return null;
  const normalized = new Date(timestamp).toISOString().slice(0, 10);
  return normalized === value ? Math.trunc(timestamp / DAY_MS) : null;
}

function historyUnavailable(message) {
  return {
    status: "unavailable",
    title: "30-Day Observation History",
    message,
    summary: null,
    range: null,
    latestDetail: null,
    points: [],
    segments: [],
    xAnchors: [],
    yTicks: [],
    chart: CHART,
  };
}

function xPosition(dayNumber, startDay, endDay) {
  const span = endDay - startDay;
  if (span <= 0) return CHART.plotLeft;
  return CHART.plotLeft + ((dayNumber - startDay) / span) * (CHART.plotRight - CHART.plotLeft);
}

function yPosition(valuePercent) {
  return CHART.plotTop + ((100 - valuePercent) / 100) * (CHART.plotBottom - CHART.plotTop);
}

function coverageIsConsistent(validDays, expectedDays, coveragePercent) {
  const calculated = (validDays / expectedDays) * 100;
  return Math.abs(calculated - coveragePercent) <= 0.011;
}

function observationLabel(point) {
  const coverage = `${point.metricValidVehicleDays} / ${point.expectedRequestedVehicleDays} vehicle-days (${point.coveragePercent.toFixed(2)}%)`;
  const representative = point.fleetRepresentative
    ? "fleet representative"
    : "not fleet representative";

  if (point.kind === "available") {
    return `${point.windowEnd}: ${point.valuePercent.toFixed(2)}% utilization; ${coverage}; ${representative}.`;
  }
  return `${point.windowEnd}: Unavailable observation; ${coverage}; ${representative}.`;
}

function buildPoint(rawPoint, startDay, endDay) {
  if (!rawPoint || typeof rawPoint !== "object") return null;

  const windowStartDay = parseIsoDay(rawPoint.window_start);
  const windowEndDay = parseIsoDay(rawPoint.window_end);
  const metricValidVehicleDays = nonNegativeInteger(rawPoint.metric_valid_vehicle_days);
  const expectedRequestedVehicleDays = nonNegativeInteger(rawPoint.expected_requested_vehicle_days);
  const coveragePercent = finiteNumber(rawPoint.utilization_metric_coverage_percent);
  const fleetRepresentative = rawPoint.fleet_representative;

  if (
    windowStartDay === null ||
    windowEndDay === null ||
    windowEndDay < startDay ||
    windowEndDay > endDay ||
    windowStartDay > windowEndDay ||
    metricValidVehicleDays === null ||
    expectedRequestedVehicleDays === null ||
    expectedRequestedVehicleDays <= 0 ||
    metricValidVehicleDays > expectedRequestedVehicleDays ||
    coveragePercent === null ||
    coveragePercent < 0 ||
    coveragePercent > 100 ||
    typeof fleetRepresentative !== "boolean" ||
    fleetRepresentative !== (metricValidVehicleDays === expectedRequestedVehicleDays) ||
    !coverageIsConsistent(metricValidVehicleDays, expectedRequestedVehicleDays, coveragePercent)
  ) {
    return null;
  }

  const common = {
    windowStart: rawPoint.window_start,
    windowEnd: rawPoint.window_end,
    dayNumber: windowEndDay,
    x: xPosition(windowEndDay, startDay, endDay),
    metricValidVehicleDays,
    expectedRequestedVehicleDays,
    coveragePercent,
    fleetRepresentative,
  };

  if (rawPoint.status === "available_observed") {
    const valuePercent = finiteNumber(rawPoint.value_percent);
    if (valuePercent === null || valuePercent < 0 || valuePercent > 100) return null;
    const point = {
      ...common,
      kind: "available",
      valuePercent,
      y: yPosition(valuePercent),
    };
    return { ...point, label: observationLabel(point) };
  }

  if (rawPoint.status === "unavailable" && rawPoint.value_percent === null) {
    const point = {
      ...common,
      kind: "unavailable",
      valuePercent: null,
      y: null,
    };
    return { ...point, label: observationLabel(point) };
  }

  return null;
}

function buildSegments(points) {
  const segments = [];
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    if (
      previous.kind === "available" &&
      current.kind === "available" &&
      current.dayNumber - previous.dayNumber === 1
    ) {
      segments.push({
        x1: previous.x,
        y1: previous.y,
        x2: current.x,
        y2: current.y,
      });
    }
  }
  return segments;
}

function buildXAnchors(startDay, endDay) {
  const midpoint = startDay + Math.round((endDay - startDay) / 2);
  return [startDay, midpoint, endDay].map((dayNumber) => {
    const date = new Date(dayNumber * DAY_MS).toISOString().slice(0, 10);
    return { date, x: xPosition(dayNumber, startDay, endDay) };
  });
}

function buildYTicks() {
  return [100, 50, 0].map((value) => ({ value, y: yPosition(value) }));
}

export function motiveUtilizationHistoryPresentation(payload, options = {}) {
  const { loading = false, requestFailed = false } = options;

  if (loading) {
    return {
      ...historyUnavailable("Loading 30-day utilization history…"),
      status: "loading",
    };
  }
  if (requestFailed) return historyUnavailable("Utilization history temporarily unavailable.");

  if (
    !payload ||
    typeof payload !== "object" ||
    payload.kpi !== HISTORY_KPI ||
    payload.requested_history_days !== HISTORY_DAYS ||
    typeof payload.request_timezone !== "string" ||
    !payload.request_timezone ||
    !Array.isArray(payload.points)
  ) {
    return historyUnavailable("Utilization history temporarily unavailable.");
  }

  const startDay = parseIsoDay(payload.history_start);
  const endDay = parseIsoDay(payload.history_end);
  const snapshotCount = nonNegativeInteger(payload.snapshot_count);

  if (
    startDay === null ||
    endDay === null ||
    endDay - startDay !== HISTORY_DAYS - 1 ||
    snapshotCount === null ||
    snapshotCount !== payload.points.length
  ) {
    return historyUnavailable("Utilization history temporarily unavailable.");
  }

  const points = [];
  const observedDates = new Set();
  for (const rawPoint of payload.points) {
    const point = buildPoint(rawPoint, startDay, endDay);
    if (!point || observedDates.has(point.windowEnd)) {
      return historyUnavailable("Utilization history temporarily unavailable.");
    }
    observedDates.add(point.windowEnd);
    points.push(point);
  }
  points.sort((left, right) => left.dayNumber - right.dayNumber);

  const range = `${payload.history_start} to ${payload.history_end} · ${payload.request_timezone}`;
  if (snapshotCount === 0) {
    return {
      status: "empty",
      title: "30-Day Observation History",
      message: "30-day trend will appear after successful daily utilization snapshots are recorded.",
      summary: `0 snapshots · ${range}`,
      range,
      latestDetail: null,
      points,
      segments: [],
      xAnchors: buildXAnchors(startDay, endDay),
      yTicks: buildYTicks(),
      chart: CHART,
    };
  }

  const usableCount = points.filter((point) => point.kind === "available").length;
  const unavailableCount = points.length - usableCount;
  const latestPoint = points[points.length - 1];
  const latestDetail = latestPoint.label;
  const observationWord = usableCount === 1 ? "observation" : "observations";
  const unavailableSuffix = unavailableCount > 0
    ? ` · ${unavailableCount} unavailable ${unavailableCount === 1 ? "snapshot" : "snapshots"}`
    : "";

  return {
    status: "ready",
    title: "30-Day Observation History",
    message: null,
    summary: `${snapshotCount} ${snapshotCount === 1 ? "snapshot" : "snapshots"} · ${usableCount} usable ${observationWord}${unavailableSuffix}`,
    range,
    latestDetail,
    points,
    segments: buildSegments(points),
    xAnchors: buildXAnchors(startDay, endDay),
    yTicks: buildYTicks(),
    chart: CHART,
  };
}

export const motiveUtilizationHistoryFrontendContract = Object.freeze({
  kpi: HISTORY_KPI,
  days: HISTORY_DAYS,
  chart: CHART,
});
