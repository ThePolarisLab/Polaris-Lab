import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  hasRenderedSecret,
  motiveCallbackNotice,
  motiveConnectorPresentation,
  motiveEvidenceStatus,
  motiveSystemHealth,
  safeMotiveMetadata,
} from "../src/motiveFrontend.js";

const connectedPayload = {
  health: { status: "connected", message: "Motive OAuth credential passed limited read-only verification." },
  status: {
    authentication_method: "oauth2",
    connection_status: "connected",
    last_verified_at: "2026-08-06T05:00:00+00:00",
    granted_scopes: ["companies.read", "vehicles.read"],
    provider_company_name: "Mor Logistics",
    provider_company_id: "company-123",
    authorization_required: false,
    production_sync_enabled: false,
    production_certified: false,
    access_token: "should-not-render",
    refresh_token: "should-not-render",
    client_secret: "should-not-render",
    authorization_header: "should-not-render",
    oauth_state: "should-not-render",
  },
};

test("loads Motive status labels for safe connector states", () => {
  assert.equal(motiveConnectorPresentation(null, true).status, "Checking");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "not_configured" } }).status, "Not configured");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "authorization_required" } }).status, "Authorization required");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "configured_unverified" } }).status, "Configured, not verified");
  assert.equal(motiveConnectorPresentation(connectedPayload).status, "Connected");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "rate_limited" } }).status, "Rate limited");
  assert.equal(motiveConnectorPresentation({ status: { connection_status: "failed" } }).status, "Failed");
});

test("parses Motive callback success denied and error hash statuses", () => {
  assert.equal(motiveCallbackNotice("#executive/connectors?motive=connected_unverified").message, "Motive authorization completed. Run verification before using Motive evidence.");
  assert.equal(motiveCallbackNotice("#executive/connectors?motive=denied").message, "Motive authorization was denied or cancelled.");
  assert.equal(motiveCallbackNotice("#executive/connectors?motive=error").message, "Motive authorization could not be completed. No secrets were exposed.");
  assert.equal(motiveCallbackNotice("#executive/connectors?code=abc&state=xyz"), null);
});

test("keeps Motive metadata safe for rendering", () => {
  const metadata = safeMotiveMetadata(connectedPayload);
  assert.deepEqual(Object.keys(metadata).sort(), [
    "authentication_method",
    "authorization_required",
    "connection_status",
    "granted_scopes",
    "last_verified_at",
    "production_certified",
    "production_sync_enabled",
    "provider_company_id",
    "provider_company_name",
  ].sort());
  assert.equal(metadata.authentication_method, "oauth2");
  assert.equal(metadata.production_sync_enabled, false);
  assert.equal(metadata.production_certified, false);
  assert.equal(hasRenderedSecret(metadata), false);
});

test("maps Motive system health only after successful verification", () => {
  assert.equal(motiveSystemHealth(null, true).status, "Checking");
  assert.equal(motiveSystemHealth({ status: { connection_status: "connected" } }).status, "Degraded");
  assert.equal(motiveSystemHealth(connectedPayload).status, "Healthy");
  assert.equal(motiveSystemHealth({ status: { connection_status: "configured_unverified" } }).status, "Checking");
  assert.equal(motiveSystemHealth({ status: { connection_status: "authorization_required" } }).status, "Degraded");
  assert.equal(motiveSystemHealth({ status: { connection_status: "rate_limited" } }).status, "Degraded");
});

test("maps Motive evidence without claiming ingestion", () => {
  assert.equal(motiveEvidenceStatus({ status: { connection_status: "not_configured" } }).status, "Not configured");
  assert.equal(motiveEvidenceStatus({ status: { connection_status: "configured_unverified" } }).status, "Pending");
  const verified = motiveEvidenceStatus(connectedPayload);
  assert.equal(verified.status, "Available");
  assert.match(verified.detail, /Broad evidence ingestion remains deferred/);
});

test("uses backend-provided Motive authorization URL and actions", async () => {
  const source = await readFile(new URL("../src/components/ExecutiveViews.jsx", import.meta.url), "utf8");
  assert.match(source, /apiClient\.get\("\/api\/v1\/motive\/status"\)/);
  assert.match(source, /apiClient\.get\("\/api\/v1\/motive\/connect"\)/);
  assert.match(source, /window\.location\.assign\(payload\.authorization_url\)/);
  assert.match(source, /apiClient\.post\("\/api\/v1\/motive\/verify"\)/);
  assert.match(source, /apiClient\.post\("\/api\/v1\/motive\/disconnect"\)/);
  assert.doesNotMatch(source, /gomotive\.com\/oauth\/authorize/);
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
