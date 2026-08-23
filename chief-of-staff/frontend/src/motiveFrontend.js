const SECRET_KEY_PATTERN = /(token|secret|authorization|oauth_state|state|code|header|api_key|x-api-key)/i;

const STATUS_LABELS = Object.freeze({
  not_configured: "Not configured",
  authorization_required: "Authorization required",
  configured_unverified: "Configured, verification pending",
  connected: "Connected",
  rate_limited: "Rate limited",
  failed: "Provider unavailable",
  running: "Checking",
  checking: "Checking",
});

const STATUS_DETAILS = Object.freeze({
  not_configured: "Motive Company API Key is not configured in the backend environment.",
  authorization_required: "Motive rejected the Company API Key or the key lacks required read access.",
  configured_unverified: "Motive Company API Key is configured by an administrator and awaiting limited read-only verification.",
  connected: "Motive Company API Key passed limited read-only vehicle verification.",
  rate_limited: "Motive returned a rate-limit response; Retry-After is honored when present.",
  failed: "Motive provider verification failed with a sanitized error.",
  running: "Checking Motive Company API Key status.",
  checking: "Checking Motive Company API Key status.",
});

const UTILIZATION_KPI_TITLE = "Observed 7-Day Vehicle Utilization";
const IDLE_TIME_SHARE_KPI_TITLE = "Observed 7-Day Vehicle Idle-Time Share";
const IDLE_TIME_SHARE_KPI_DESCRIPTION = "Share of observed idle + driving time reported as idle.";

function connectionStatus(payload) {
  return payload?.status?.connection_status || payload?.health?.details?.connection_status || payload?.health?.status || "not_configured";
}

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nonNegativeInteger(value) {
  return Number.isInteger(value) && value >= 0 ? value : null;
}

function utilizationUnavailable(detail) {
  return {
    status: "unavailable",
    title: UTILIZATION_KPI_TITLE,
    value: "Unavailable",
    coverage: null,
    completeness: detail,
    window: null,
  };
}

function idleTimeShareUnavailable(detail) {
  return {
    status: "unavailable",
    title: IDLE_TIME_SHARE_KPI_TITLE,
    description: IDLE_TIME_SHARE_KPI_DESCRIPTION,
    value: "Unavailable",
    coverage: null,
    completeness: detail,
    window: null,
  };
}

export function motiveConnectorPresentation(payload, loading = false) {
  if (loading) return { status: "Checking", detail: STATUS_DETAILS.checking, statusKey: "checking" };
  const statusKey = connectionStatus(payload);
  return {
    status: STATUS_LABELS[statusKey] || STATUS_LABELS.failed,
    detail: payload?.health?.message || STATUS_DETAILS[statusKey] || STATUS_DETAILS.failed,
    statusKey,
  };
}

export function motiveSystemHealth(payload, loading = false) {
  if (loading) return { status: "Checking", detail: STATUS_DETAILS.checking };
  const statusKey = connectionStatus(payload);
  if (statusKey === "connected" && Boolean(payload?.status?.last_verified_at || payload?.health?.details?.last_verified_at)) {
    return { status: "Healthy", detail: "Motive Company API Key verification has succeeded." };
  }
  if (statusKey === "not_configured") return { status: "Not configured", detail: STATUS_DETAILS.not_configured };
  if (statusKey === "configured_unverified") return { status: "Checking", detail: STATUS_DETAILS.configured_unverified };
  if (statusKey === "rate_limited") return { status: "Degraded", detail: STATUS_DETAILS.rate_limited };
  if (statusKey === "authorization_required") return { status: "Degraded", detail: STATUS_DETAILS.authorization_required };
  return { status: "Degraded", detail: STATUS_DETAILS[statusKey] || STATUS_DETAILS.failed };
}

export function motiveEvidenceStatus(payload, loading = false) {
  if (loading) return { status: "Checking", detail: "Checking Motive Company API Key verification status." };
  const statusKey = connectionStatus(payload);
  if (statusKey === "connected" && Boolean(payload?.status?.last_verified_at || payload?.health?.details?.last_verified_at)) {
    return { status: "Available", detail: "Available after successful API-key connection verification. Vehicle and user sync metadata may be available, but broad evidence ingestion remains deferred." };
  }
  if (statusKey === "configured_unverified") {
    return { status: "Pending", detail: "Configured by administrator, verification pending. Production data ingestion remains deferred." };
  }
  return { status: "Not configured", detail: "Motive Company API Key verification only; production data ingestion remains deferred." };
}

export function motiveUtilizationKpiPresentation(payload, options = {}) {
  const { loading = false, requestFailed = false } = options;

  if (loading) {
    return {
      status: "loading",
      title: UTILIZATION_KPI_TITLE,
      value: "Loading…",
      coverage: null,
      completeness: "Loading utilization reporting…",
      window: null,
    };
  }

  if (requestFailed) return utilizationUnavailable("Utilization reporting temporarily unavailable.");
  if (payload?.status !== "available_observed") {
    return utilizationUnavailable("No certified utilization metric is available for the latest reconciled window.");
  }

  const valuePercent = finiteNumber(payload?.value_percent);
  const metricValidVehicleDays = nonNegativeInteger(payload?.metric_valid_vehicle_days);
  const expectedRequestedVehicleDays = nonNegativeInteger(payload?.expected_requested_vehicle_days);
  const coveragePercent = finiteNumber(payload?.utilization_metric_coverage_percent);
  const windowStart = typeof payload?.window_start === "string" ? payload.window_start : "";
  const windowEnd = typeof payload?.window_end === "string" ? payload.window_end : "";
  const requestTimezone = typeof payload?.request_timezone === "string" ? payload.request_timezone : "";

  if (
    valuePercent === null ||
    metricValidVehicleDays === null ||
    expectedRequestedVehicleDays === null ||
    expectedRequestedVehicleDays <= 0 ||
    coveragePercent === null ||
    coveragePercent < 0 ||
    coveragePercent > 100 ||
    !windowStart ||
    !windowEnd ||
    !requestTimezone
  ) {
    return utilizationUnavailable("No certified utilization metric is available for the latest reconciled window.");
  }

  return {
    status: "available_observed",
    title: UTILIZATION_KPI_TITLE,
    value: `${valuePercent.toFixed(2)}%`,
    coverage: `${metricValidVehicleDays} / ${expectedRequestedVehicleDays} vehicle-days (${coveragePercent.toFixed(2)}%)`,
    completeness: payload?.fleet_representative === true
      ? "Full vehicle-day coverage"
      : "Partial observation — not fleet representative",
    window: `${windowStart} to ${windowEnd} · ${requestTimezone}`,
  };
}

export function motiveIdleTimeShareKpiPresentation(payload, options = {}) {
  const { loading = false, requestFailed = false } = options;

  if (loading) {
    return {
      status: "loading",
      title: IDLE_TIME_SHARE_KPI_TITLE,
      description: IDLE_TIME_SHARE_KPI_DESCRIPTION,
      value: "Loading…",
      coverage: null,
      completeness: "Loading idle-time-share reporting…",
      window: null,
    };
  }

  if (requestFailed) return idleTimeShareUnavailable("Idle-time-share reporting temporarily unavailable.");
  if (payload?.status !== "available_observed") {
    return idleTimeShareUnavailable("No certified idle-time-share metric is available for the latest reconciled window.");
  }

  const valuePercent = finiteNumber(payload?.value_percent);
  const metricValidVehicleDays = nonNegativeInteger(payload?.metric_valid_vehicle_days);
  const expectedRequestedVehicleDays = nonNegativeInteger(payload?.expected_requested_vehicle_days);
  const coveragePercent = finiteNumber(payload?.idle_time_metric_coverage_percent);
  const windowStart = typeof payload?.window_start === "string" ? payload.window_start : "";
  const windowEnd = typeof payload?.window_end === "string" ? payload.window_end : "";
  const requestTimezone = typeof payload?.request_timezone === "string" ? payload.request_timezone : "";

  if (
    valuePercent === null ||
    valuePercent < 0 ||
    valuePercent > 100 ||
    metricValidVehicleDays === null ||
    expectedRequestedVehicleDays === null ||
    expectedRequestedVehicleDays <= 0 ||
    metricValidVehicleDays > expectedRequestedVehicleDays ||
    coveragePercent === null ||
    coveragePercent < 0 ||
    coveragePercent > 100 ||
    !windowStart ||
    !windowEnd ||
    !requestTimezone
  ) {
    return idleTimeShareUnavailable("No certified idle-time-share metric is available for the latest reconciled window.");
  }

  return {
    status: "available_observed",
    title: IDLE_TIME_SHARE_KPI_TITLE,
    description: IDLE_TIME_SHARE_KPI_DESCRIPTION,
    value: `${valuePercent.toFixed(2)}%`,
    coverage: `${metricValidVehicleDays} / ${expectedRequestedVehicleDays} vehicle-days (${coveragePercent.toFixed(2)}%)`,
    completeness: payload?.fleet_representative === true
      ? "Full vehicle-day coverage"
      : "Partial observation — not fleet representative",
    window: `${windowStart} to ${windowEnd} · ${requestTimezone}`,
  };
}

export function safeMotiveMetadata(payload) {
  const details = payload?.status || payload?.health?.details || {};
  const safeKeys = [
    "authentication_method",
    "credential_source",
    "configured_by_administrator",
    "key_present",
    "connection_status",
    "last_verified_at",
    "records_read",
    "authorization_required",
    "production_sync_enabled",
    "broad_sync_enabled",
    "production_certified",
    "vehicle_sync_enabled",
    "last_vehicle_sync_at",
    "last_vehicle_sync_status",
    "vehicle_records_stored",
    "last_vehicle_records_read",
    "last_vehicle_pages_read",
    "vehicle_ingestion_certified",
    "user_sync_enabled",
    "last_user_sync_at",
    "last_user_sync_status",
    "user_records_stored",
    "last_user_records_read",
    "last_user_pages_read",
    "user_ingestion_certified",
    "driver_classification_certified",
  ];
  const result = {};
  for (const key of safeKeys) {
    if (!["authorization_required", "configured_by_administrator", "key_present"].includes(key) && SECRET_KEY_PATTERN.test(key)) continue;
    if (Object.prototype.hasOwnProperty.call(details, key)) result[key] = details[key];
  }
  result.production_sync_enabled = Boolean(result.production_sync_enabled);
  result.production_certified = Boolean(result.production_certified);
  result.vehicle_sync_enabled = Boolean(result.vehicle_sync_enabled);
  result.vehicle_ingestion_certified = Boolean(result.vehicle_ingestion_certified);
  result.user_sync_enabled = Boolean(result.user_sync_enabled);
  result.user_ingestion_certified = Boolean(result.user_ingestion_certified);
  result.driver_classification_certified = Boolean(result.driver_classification_certified);
  return result;
}

export function hasRenderedSecret(value) {
  const text = JSON.stringify(value || {}).toLowerCase();
  return ["access_token", "refresh_token", "client_secret", "authorization header", "oauth_state", " state secret", "motive_api_key", "x-api-key"].some((marker) => text.includes(marker));
}

export const motiveFrontendContract = Object.freeze({
  statusLabels: STATUS_LABELS,
  utilizationKpiTitle: UTILIZATION_KPI_TITLE,
  idleTimeShareKpiTitle: IDLE_TIME_SHARE_KPI_TITLE,
});