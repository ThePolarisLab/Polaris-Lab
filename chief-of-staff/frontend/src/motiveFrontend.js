const SECRET_KEY_PATTERN = /(token|secret|authorization|oauth_state|state|code|header)/i;

const STATUS_LABELS = Object.freeze({
  not_configured: "Not configured",
  authorization_required: "Authorization required",
  configured_unverified: "Configured, not verified",
  connected: "Connected",
  rate_limited: "Rate limited",
  failed: "Failed",
  running: "Checking",
  checking: "Checking",
});

const STATUS_DETAILS = Object.freeze({
  not_configured: "Motive OAuth has not been configured for this organization.",
  authorization_required: "Motive authorization is required before verification can run.",
  configured_unverified: "Motive OAuth is connected and awaiting limited read-only verification.",
  connected: "Motive OAuth passed limited read-only connection verification.",
  rate_limited: "Motive returned a rate-limit response; retry timing is not assumed.",
  failed: "Motive verification failed with a sanitized provider error.",
  running: "Checking Motive OAuth status.",
  checking: "Checking Motive OAuth status.",
});

const CALLBACK_MESSAGES = Object.freeze({
  connected_unverified: {
    tone: "success",
    message: "Motive authorization completed. Run verification before using Motive evidence.",
  },
  denied: {
    tone: "warning",
    message: "Motive authorization was denied or cancelled.",
  },
  error: {
    tone: "warning",
    message: "Motive authorization could not be completed. No secrets were exposed.",
  },
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
    return { status: "Healthy", detail: "Motive OAuth connection verification has succeeded." };
  }
  if (statusKey === "not_configured") return { status: "Not configured", detail: STATUS_DETAILS.not_configured };
  if (statusKey === "configured_unverified") return { status: "Checking", detail: STATUS_DETAILS.configured_unverified };
  if (statusKey === "rate_limited") return { status: "Degraded", detail: STATUS_DETAILS.rate_limited };
  if (statusKey === "authorization_required") return { status: "Degraded", detail: STATUS_DETAILS.authorization_required };
  return { status: "Degraded", detail: STATUS_DETAILS[statusKey] || STATUS_DETAILS.failed };
}

export function motiveEvidenceStatus(payload, loading = false) {
  if (loading) return { status: "Checking", detail: "Checking Motive OAuth verification status." };
  const statusKey = connectionStatus(payload);
  if (statusKey === "connected" && Boolean(payload?.status?.last_verified_at || payload?.health?.details?.last_verified_at)) {
    return { status: "Available", detail: "Available after successful OAuth connection verification. Broad evidence ingestion remains deferred." };
  }
  if (statusKey === "configured_unverified") {
    return { status: "Pending", detail: "Connected, verification pending. Production data ingestion remains deferred." };
  }
  return { status: "Not configured", detail: "Motive OAuth foundation and connection verification only; production data ingestion remains deferred." };
}

export function motiveCallbackNotice(hash) {
  const rawHash = String(hash || "").replace(/^#\/?/, "");
  const [, query = ""] = rawHash.split("?");
  const status = new URLSearchParams(query).get("motive");
  return CALLBACK_MESSAGES[status] ? { status, ...CALLBACK_MESSAGES[status] } : null;
}

export function safeMotiveMetadata(payload) {
  const details = payload?.status || payload?.health?.details || {};
  const safeKeys = [
    "authentication_method",
    "connection_status",
    "last_verified_at",
    "granted_scopes",
    "provider_company_name",
    "provider_company_id",
    "authorization_required",
    "production_sync_enabled",
    "broad_sync_enabled",
    "production_certified",
  ];
  const result = {};
  for (const key of safeKeys) {
    if (SECRET_KEY_PATTERN.test(key)) continue;
    if (Object.prototype.hasOwnProperty.call(details, key)) result[key] = details[key];
  }
  result.production_sync_enabled = Boolean(result.production_sync_enabled);
  result.production_certified = Boolean(result.production_certified);
  return result;
}

export function hasRenderedSecret(value) {
  const text = JSON.stringify(value || {}).toLowerCase();
  return ["access_token", "refresh_token", "client_secret", "authorization header", "oauth_state", " state secret"].some((marker) => text.includes(marker));
}

export const motiveFrontendContract = Object.freeze({
  statusLabels: STATUS_LABELS,
  callbackMessages: CALLBACK_MESSAGES,
});
