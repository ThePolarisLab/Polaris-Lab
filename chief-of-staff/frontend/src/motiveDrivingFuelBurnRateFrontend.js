const TITLE = "Observed 7-Day Driving Fuel Burn Rate";
const DESCRIPTION = "Observed driving fuel volume per observed driving hour.";
const KPI_NAME = "observed_7_day_driving_fuel_burn_rate";

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0 ? value : null;
}

function unavailable(detail) {
  return {
    status: "unavailable",
    title: TITLE,
    description: DESCRIPTION,
    value: "Unavailable",
    coverage: null,
    completeness: detail,
    window: null,
  };
}

export function motiveDrivingFuelBurnRateKpiPresentation(payload, options = {}) {
  const { loading = false, requestFailed = false } = options;

  if (loading) {
    return {
      status: "loading",
      title: TITLE,
      description: DESCRIPTION,
      value: "Loading…",
      coverage: null,
      completeness: "Loading driving fuel burn-rate reporting…",
      window: null,
    };
  }

  if (requestFailed) return unavailable("Driving fuel burn-rate reporting temporarily unavailable.");
  if (payload?.status !== "available_observed") {
    return unavailable("No certified driving fuel burn-rate metric is available for the latest reconciled window.");
  }

  const value = finiteNumber(payload?.value_gallons_per_driving_hour);
  const metricValidVehicleDays = nonNegativeInteger(payload?.metric_valid_vehicle_days);
  const expectedRequestedVehicleDays = nonNegativeInteger(payload?.expected_requested_vehicle_days);
  const coveragePercent = finiteNumber(payload?.driving_fuel_burn_rate_metric_coverage_percent);
  const windowStart = typeof payload?.window_start === "string" ? payload.window_start : "";
  const windowEnd = typeof payload?.window_end === "string" ? payload.window_end : "";
  const requestTimezone = typeof payload?.request_timezone === "string" ? payload.request_timezone : "";

  if (
    payload?.kpi !== KPI_NAME ||
    payload?.secrets_exposed !== false ||
    value === null ||
    value < 0 ||
    metricValidVehicleDays === null ||
    expectedRequestedVehicleDays === null ||
    expectedRequestedVehicleDays <= 0 ||
    metricValidVehicleDays > expectedRequestedVehicleDays ||
    coveragePercent === null ||
    coveragePercent < 0 ||
    coveragePercent > 100 ||
    payload?.fuel_unit !== "gallons" ||
    payload?.driving_time_unit !== "seconds" ||
    payload?.rate_unit !== "gallons_per_driving_hour" ||
    payload?.unit_request_mode !== "imperial" ||
    requestTimezone !== "America/Chicago" ||
    !windowStart ||
    !windowEnd
  ) {
    return unavailable("No certified driving fuel burn-rate metric is available for the latest reconciled window.");
  }

  return {
    status: "available_observed",
    title: TITLE,
    description: DESCRIPTION,
    value: `${value.toFixed(2)} gal/driving-hr`,
    coverage: `${metricValidVehicleDays} / ${expectedRequestedVehicleDays} vehicle-days (${coveragePercent.toFixed(2)}%)`,
    completeness: payload?.fleet_representative === true
      ? "Full vehicle-day coverage"
      : "Partial observation — not fleet representative",
    window: `${windowStart} to ${windowEnd} · ${requestTimezone}`,
  };
}
