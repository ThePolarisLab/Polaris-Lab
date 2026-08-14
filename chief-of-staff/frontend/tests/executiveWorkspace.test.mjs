import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const dashboardSource = await readFile(
  new URL("../src/components/ExecutiveDashboard.jsx", import.meta.url),
  "utf8"
);

test("Executive Dashboard uses the centralized API client", () => {
  assert.match(dashboardSource, /import \{ apiClient \} from "\.\.\/apiClient"/);
  assert.doesNotMatch(dashboardSource, /\bfetch\s*\(/);
  assert.doesNotMatch(dashboardSource, /http:\/\/127\.0\.0\.1:8000/);
});

test("Executive Dashboard derives user and organization from runtime context", () => {
  assert.match(dashboardSource, /runtimeConfig\.workspace/);
  assert.doesNotMatch(dashboardSource, /user_name=Surinder/);
  assert.doesNotMatch(dashboardSource, /author:\s*"Surinder"/);
});

test("Executive Dashboard can link ACE attention into the ACE workspace", () => {
  assert.match(dashboardSource, /dashboard-item-link/);
  assert.match(dashboardSource, /Open in ACE/);
  assert.match(dashboardSource, /item\.entity_id\.startsWith\("#"\)/);
});
