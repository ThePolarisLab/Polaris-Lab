import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");

test("executive workspace exposes the planned Mission 003 navigation", () => {
  for (const route of [
    "dashboard",
    "daily-brief",
    "evidence",
    "decisions",
    "connectors",
    "system-health",
  ]) {
    assert.match(appSource, new RegExp(`key: "${route}"`));
  }
});

test("executive workspace preserves the governed Builder Console boundary", () => {
  assert.match(appSource, /href="#builder"/);
  assert.match(appSource, /BuilderConsole/);
  assert.match(appSource, /Observer mode/);
});

test("workspace identity comes from centralized runtime configuration", () => {
  assert.match(appSource, /runtimeConfig\.workspace\.organizationName/);
  assert.match(appSource, /runtimeConfig\.workspace\.workspaceName/);
  assert.match(appSource, /runtimeConfig\.workspace\.userName/);
  assert.doesNotMatch(appSource, /http:\/\/127\.0\.0\.1:8000/);
});
