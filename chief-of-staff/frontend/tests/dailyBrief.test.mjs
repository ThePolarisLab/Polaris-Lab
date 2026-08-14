import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
const briefSource = await readFile(new URL("../src/components/DailyBrief.jsx", import.meta.url), "utf8");

test("Daily Brief route renders the dedicated morning brief component", () => {
  assert.match(appSource, /import DailyBrief from "\.\/components\/DailyBrief"/);
  assert.match(appSource, /page === "daily-brief" \? <DailyBrief \/>/);
});

test("Daily Brief uses the existing executive dashboard API contract", () => {
  assert.match(briefSource, /\/dashboard\/executive\?user_name=/);
  assert.match(briefSource, /dashboard\?\.daily_brief/);
  assert.doesNotMatch(briefSource, /\bfetch\s*\(/);
});

test("Daily Brief exposes V1 executive sections without operational flood language", () => {
  for (const label of [
    "Today's Priority",
    "Needs Attention",
    "ACE / Bond Control",
    "Carry Forward",
    "Waiting On",
    "System / Data Health",
  ]) {
    assert.match(briefSource, new RegExp(label.replace("/", "\\/")));
  }
  assert.match(briefSource, /No actionable feed or connector issues/);
  assert.match(briefSource, /Open in ACE/);
  assert.doesNotMatch(briefSource, /raw workbook/i);
});
