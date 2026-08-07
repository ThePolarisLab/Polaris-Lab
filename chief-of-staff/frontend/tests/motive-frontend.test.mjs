import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  hasRenderedSecret,
  motiveConnectorPresentation,
  motiveEvidenceStatus,
  motiveSystemHealth,
  safeMotiveMetadata,
} from "../src/motiveFrontend.js";

const connectedPayload = {
  health: { status: "connected", message: "Motive Company API Key passed limited read-only verification." },
  status: {
    authentication_method: "company_api_key",
    credential_source: "render_environment",
    configured_by_administrator: true,
    key_present: true,
    connection_status: "connected",
    last_verified_at: "2026-08-06T05:00:00+00:00",
    records_read: 1,
    authorization_required: false,
    production_sync_enabled: false,
    broad_sync_enabled: false,
    production_certified: false,
    vehicle_sync_enabled: true,
    last_vehicle_sync_at: "2026-08-07T05:00:00+00:00",
    last_vehicle_sync_status: "success",
    vehicle_records_stored: 17,
    last_vehicle_records_read: 17,
    last_vehicle_pages_read: 1,
    vehicle_ingestion_certified: true,
    user_sync_enabled: true,
    last_user_sync_at: "2026-08-07T06:00:00+00:00",
    last_user_sync_status: "success",
    user_records_stored: 9,
    last_user_records_read: 9,
    last_user_pages_read: 1,
    user_ingestion_certified: true,
    driver_classification_certified: false,
    users: [{ id: "provider-data-should-not-render" }],
    vehicles: [{ id: "provider-data-should-not-render" }],
    access_token: "should-not-render",
    refresh_token: "should-not-render",
    client_secret: "should-not-render",
    authorization_header: "should-not-render",
    motive_api_key: "should-not-render",
    x_api_key: "should-not-render",
  },
};

test("loads Motive API-key status labels for safe connector states", () => {
  assert.equal(motiveConnectorPresentation(null, true).status, "Checking");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "not_configured" } }).status, "Not configured");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "authorization_required" } }).status, "Authorization required");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "configured_unverified" } }).status, "Configured, verification pending");
  assert.equal(motiveConnectorPresentation(connectedPayload).status, "Connected");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "rate_limited" } }).status, "Rate limited");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "failed" } }).status, "Provider unavailable");
});

test("keeps Motive API-key, vehicle, and user metadata safe for rendering", () => {
  const metadata = safeMotiveMetadata(connectedPayload);
  assert.deepEqual(Object.keys(metadata).sort(), [
    "authentication_method",
    "authorization_required",
    "broad_sync_enabled",
    "configured_by_administrator",
    "connection_status",
    "credential_source",
    "driver_classification_certified",
    "key_present",
    "last_user_pages_read",
    "last_user_records_read",
    "last_user_sync_at",
    "last_user_sync_status",
    "last_vehicle_pages_read",
    "last_vehicle_records_read",
    "last_vehicle_sync_at",
    "last_vehicle_sync_status",
    "last_verified_at",
    "production_certified",
    "production_sync_enabled",
    "records_read",
    "user_ingestion_certified",
    "user_records_stored",
    "user_sync_enabled",
    "vehicle_ingestion_certified",
    "vehicle_records_stored",
    "vehicle_sync_enabled",
  ].sort());
  assert.equal(metadata.authentication_method, "company_api_key");
  assert.equal(metadata.credential_source, "render_environment");
  assert.equal(metadata.configured_by_administrator, true);
  assert.equal(metadata.production_sync_enabled, false);
  assert.equal(metadata.production_certified, false);
  assert.equal(metadata.vehicle_sync_enabled, true);
  assert.equal(metadata.vehicle_records_stored, 17);
  assert.equal(metadata.last_vehicle_sync_status, "success");
  assert.equal(metadata.user_sync_enabled, true);
  assert.equal(metadata.user_records_stored, 9);
  assert.equal(metadata.last_user_sync_status, "success");
  assert.equal(metadata.driver_classification_certified, false);
  assert.equal(hasRenderedSecret(metadata), false);
  assert.equal(JSON.stringify(metadata).includes("provider-data"), false);
});

test("maps Motive system health only after successful API-key verification", () => {
  assert.equal(motiveSystemHealth(null, true).status, "Checking");
  assert.equal(motiveSystemHealth({ status: { connection_status: "connected" } }).status, "Degraded");
  assert.equal(motiveSystemHealth(connectedPayload).status, "Healthy");
  assert.equal(motiveSystemHealth({ status: { connection_status: "configured_unverified" } }).status, "Checking");
  assert.equal(motiveSystemHealth({ status: { connection_status: "authorization_required" } }).status, "Degraded");
  assert.equal(motiveSystemHealth({ status: { connection_status: "rate_limited" } }).status, "Degraded");
});

test("maps Motive evidence without claiming broad ingestion", () => {
  assert.equal(motiveEvidenceStatus({ status: { connection_status: "not_configured" } }).status, "Not configured");
  assert.equal(motiveEvidenceStatus({ status: { connection_status: "configured_unverified" } }).status, "Pending");
  const verified = motiveEvidenceStatus(connectedPayload);
  assert.equal(verified.status, "Available");
  assert.match(verified.detail, /broad evidence ingestion remains deferred/i);
});

test("uses backend API-key status verification, vehicle sync, and user sync actions without OAuth connect", async () => {
  const source = await readFile(new URL("../src/components/ExecutiveViews.jsx", import.meta.url), "utf8");
  assert.match(source, /apiClient\.get\("\/api\/v1\/motive\/status"\)/);
  assert.doesNotMatch(source, /apiClient\.get\("\/api\/v1\/motive\/connect"\)/);
  assert.doesNotMatch(source, /motiveCallbackNotice/);
  assert.match(source, /apiClient\.post\("\/api\/v1\/motive\/verify"\)/);
  assert.match(source, /apiClient\.post\("\/api\/v1\/motive\/sync\/vehicles"\)/);
  assert.match(source, /apiClient\.post\("\/api\/v1\/motive\/sync\/users"\)/);
  assert.match(source, /apiClient\.post\("\/api\/v1\/motive\/disconnect"\)/);
  assert.match(source, /Configured by administrator/);
  assert.match(source, /Sync Vehicles/);
  assert.match(source, /Sync Users/);
  assert.match(source, /Vehicle records stored/);
  assert.match(source, /User records stored/);
  assert.match(source, /Driver classification: \{motiveDetails\.driver_classification_certified \? "Certified" : "Not certified"\}/);
  assert.doesNotMatch(source, /gomotive\.com\/oauth\/authorize/);
});

test("does not expose Motive provider data or secrets in frontend view code", async () => {
  const source = await readFile(new URL("../src/components/ExecutiveViews.jsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /access_token|refresh_token|client_secret|oauth_state|authorization_header/i);
  assert.doesNotMatch(source, /MOTIVE_API_KEY|X-API-Key|x-api-key|motive_api_key/i);
  assert.doesNotMatch(source, /vehicles\s*\.map|users\s*\.map|provider_payload/i);
  assert.doesNotMatch(source, /Driver records stored|Driver count|Drivers:/i);
});

test("keeps QuickBooks and Outlook connector consumers unchanged", async () => {
  const source = await readFile(new URL("../src/components/ExecutiveViews.jsx", import.meta.url), "utf8");
  assert.match(source, /apiClient\.get\("\/api\/v1\/connectors\/quickbooks"\)/);
  assert.match(source, /apiClient\.get\("\/api\/v1\/connectors\/quickbooks\/oauth\/authorize-url"\)/);
  assert.match(source, /apiClient\.delete\("\/api\/v1\/connectors\/quickbooks\/oauth\/connection"\)/);
  assert.match(source, /apiClient\.get\("\/api\/v1\/outlook\/status"\)/);
  assert.match(source, /apiClient\.get\("\/api\/v1\/outlook\/connect"\)/);
  assert.match(source, /apiClient\.post\("\/api\/v1\/outlook\/disconnect"\)/);
});