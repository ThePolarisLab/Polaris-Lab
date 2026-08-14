import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const ace = await readFile(new URL("../src/components/AceControl.jsx", import.meta.url), "utf8");

test("ACE workspace exposes manual daily report import without manifest automation", () => {
  assert.match(ace, /Import Latest ACE Report/);
  assert.match(ace, /\/ace\/import\/outlook-latest/);
  assert.match(ace, /No report found/);
  assert.match(ace, /Source contract error/);
  assert.match(ace, /ACE DAILY FEED/);
  assert.match(ace, /\/ace\/feed-health/);
  assert.match(ace, /Manifest is a separate source not connected yet/);
  assert.doesNotMatch(ace, /automatic import/i);
});

test("ACE workspace treats missing penalty indicator as unreported", () => {
  assert.match(ace, /Unreported/);
});

test("ACE movement table stacks create and arrival dates and gives exceptions a dedicated column", () => {
  assert.match(ace, /Create \/ Arrive Date/);
  assert.match(ace, /movementDate\(item\.create_date\)/);
  assert.match(ace, /movementDate\(item\.arrival_date\)/);
  assert.match(ace, /ace-col-exception/);
  assert.doesNotMatch(ace, /<th>Shipper → Consignee<\/th>/);
});
test("ACE KPI cards drive focused movement filters", () => {
  assert.match(ace, /counter_filter: counterFilter/);
  assert.match(ace, /setCounterFilter\("exceptions"\)/);
  assert.match(ace, /setCounterFilter\("unauthorized"\)/);
  assert.match(ace, /setActiveOnly\(true\)/);
  assert.match(ace, /<button type="button" key=\{label\} onClick=\{\(\) => applyCounterFilter\(label\)\}/);
});
