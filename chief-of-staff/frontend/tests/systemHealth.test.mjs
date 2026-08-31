import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
const systemHealth = await readFile(new URL("../src/components/SystemHealth.jsx", import.meta.url), "utf8");

test("System Health uses the dedicated passive health component", () => {
  assert.match(app, /import SystemHealth from "\.\/components\/SystemHealth"/);
  assert.match(app, /page === "system-health" \? <SystemHealth \/>/);
});

test("System Health reads runtime, connector, and freshness state without provider actions", () => {
  const expectedReads = [
    "/api/v1/system/health",
    "/api/v1/connectors/quickbooks",
    "/api/v1/outlook/status",
    "/api/v1/motive/status",
    "/api/v1/torqueai/status",
    "/api/v1/system/connector-freshness",
  ];

  for (const path of expectedReads) assert.match(systemHealth, new RegExp(path.replaceAll("/", "\\/")));
  assert.doesNotMatch(systemHealth, /apiClient\.post/);
  assert.doesNotMatch(systemHealth, /\/sync/);
  assert.doesNotMatch(systemHealth, /\/verify/);
  assert.doesNotMatch(systemHealth, /quickbooks\.api\.intuit\.com|graph\.microsoft\.com|api\.gomotive\.com/i);
});

test("System Health distinguishes scheduled freshness from manual connector age", () => {
  assert.match(systemHealth, /TorqueAI dispatch ingestion/);
  assert.match(systemHealth, /Motive vehicle utilization scheduler/);
  assert.match(systemHealth, /Freshness:/);
  assert.match(systemHealth, /cadence: hourly scheduled/);
  assert.match(systemHealth, /Cadence: manual\/operator/);
  assert.match(systemHealth, /manual connectors show age without inventing a stale threshold/);
  assert.match(systemHealth, /Recovery:/);
});

test("System Health keeps provider boundaries explicit", () => {
  assert.match(systemHealth, /Status reads do not verify or synchronize providers/);
  assert.match(systemHealth, /governed Polaris scheduler contracts, not provider SLAs/);
  assert.match(systemHealth, /provider verification or synchronization was triggered/);
});
