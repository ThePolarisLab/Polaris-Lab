import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
const certification = await readFile(
  new URL("../../../docs/reports/PGE-008.5-executive-workspace-certification.md", import.meta.url),
  "utf8",
);

const requiredRoutes = [
  "daily-brief",
  "evidence",
  "decisions",
  "connectors",
  "system-health",
];

test("Mission 003 executive routes remain present", () => {
  for (const route of requiredRoutes) assert.match(app, new RegExp(route));
});

test("Executive and Builder workspaces remain separated", () => {
  assert.match(app, /ExecutiveWorkspace/);
  assert.match(app, /BuilderConsole/);
  assert.match(app, /Observer mode/i);
});

test("certification preserves production connector boundaries", () => {
  assert.match(certification, /#61/);
  assert.match(certification, /#62/);
  assert.match(certification, /observer\/advisory/i);
  assert.match(certification, /Certified/);
});