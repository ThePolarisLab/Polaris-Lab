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
