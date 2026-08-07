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

function connectionStatus(payload) {
  return payload?.status?.connection_status || payload?.health?.details?.connection_status || payload?.health?.status || "not_configured";
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
    return { status: "Available", detail: "Available after successful API-key connection verification. Broad evidence ingestion remains deferred." };
  }
  if (statusKey === "configured_unverified") {
    return { status: "Pending", detail: "Configured by administrator, verification pending. Production data ingestion remains deferred." };
  }
  return { status: "Not configured", detail: "Motive Company API Key verification only; production data ingestion remains deferred." };
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
  ];
  const result = {};
  for (const key of safeKeys) {
    if (!["authorization_required", "configured_by_administrator", "key_present"].includes(key) && SECRET_KEY_PATTERN.test(key)) continue;
    if (Object.prototype.hasOwnProperty.call(details, key)) result[key] = details[key];
  }
  result.production_sync_enabled = Boolean(result.production_sync_enabled);
  result.production_certified = Boolean(result.production_certified);
  return result;
}

export function hasRenderedSecret(value) {
  const text = JSON.stringify(value || {}).toLowerCase();
  return ["access_token", "refresh_token", "client_secret", "authorization header", "oauth_state", " state secret", "motive_api_key", "x-api-key"].some((marker) => text.includes(marker));
}

export const motiveFrontendContract = Object.freeze({
  statusLabels: STATUS_LABELS,
});
