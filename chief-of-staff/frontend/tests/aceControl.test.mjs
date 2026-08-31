import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const ace = await readFile(new URL("../src/components/AceControl.jsx", import.meta.url), "utf8");
const reviewDrawer = await readFile(new URL("../src/components/AceReviewDrawer.jsx", import.meta.url), "utf8");

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

test("ACE review drawer treats missing penalty indicator as unreported", () => {
  assert.match(reviewDrawer, /Unreported/);
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
  assert.match(ace, /onClick=\{\(\) => applyCounterFilter\(label\)\}/);
});

test("ACE movement opens the readable review and resolution drawer", () => {
  assert.match(ace, /AceReviewDrawer/);
  assert.match(ace, /onChanged=\{refreshMovement\}/);
  assert.match(reviewDrawer, /ACE source — read only/);
  assert.match(reviewDrawer, /ACE movement evidence/);
  assert.match(reviewDrawer, /Review & Resolution/);
  assert.match(reviewDrawer, /Why Polaris flagged this movement/);
});

test("ACE review drawer edits only MOR review evidence and preserves provider ACE status", () => {
  assert.match(reviewDrawer, /Authorization decision/);
  assert.match(reviewDrawer, /AUTHORIZED - THIRD PARTY/);
  assert.match(reviewDrawer, /UNAUTHORIZED - NO MOR PERMISSION/);
  assert.match(reviewDrawer, /Authorization \/ investigation notes/);
  assert.match(reviewDrawer, /Evidence reference/);
  assert.match(reviewDrawer, /Resolution notes/);
  assert.match(reviewDrawer, /method: "PATCH"/);
  assert.match(reviewDrawer, /\/ace\/movements\/\$\{movement\.id\}\/authorization/);
  assert.match(reviewDrawer, /\/ace\/movements\/\$\{movement\.id\}\/resolve/);
  assert.match(reviewDrawer, /\/ace\/movements\/\$\{movement\.id\}\/reopen/);
  assert.match(reviewDrawer, /ACE source status was not changed/);
  assert.doesNotMatch(reviewDrawer, /setRecordStatus/);
});

test("resolved ACE reviews must be reopened before internal evidence is edited", () => {
  assert.match(reviewDrawer, /const resolved = Boolean\(movement\.resolved_at\)/);
  assert.match(reviewDrawer, /disabled=\{resolved \|\| saving\}/);
  assert.match(reviewDrawer, /Reopen this review before changing the authorization decision/);
  assert.match(reviewDrawer, /Reopen Review/);
});
