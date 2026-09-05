import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
const reviewSource = await readFile(new URL("../src/components/FuelReview.jsx", import.meta.url), "utf8");
const modelSource = await readFile(new URL("../src/fuelReviewModel.js", import.meta.url), "utf8");

test("executive workspace exposes the read-only fuel review route", () => {
  assert.match(appSource, /key: "fuel-review"/);
  assert.match(appSource, /import FuelReview/);
  assert.match(appSource, /page === "fuel-review" \? <FuelReview \/>/);
});

test("fuel review uses the existing tenant-scoped reconciliation GET only", () => {
  assert.match(reviewSource, /apiClient\.get\(`\/api\/v1\/fuel\/invoices\/\$\{invoiceRunId\}\/price-reconciliation`\)/);
  assert.match(reviewSource, /read_only/);
  assert.doesNotMatch(reviewSource, /apiClient\.post/);
  assert.doesNotMatch(reviewSource, /apiClient\.delete/);
});

test("review language preserves exact price-difference and DEF policy boundaries", () => {
  assert.match(reviewSource, /no supplier rounding rule or tolerance is assumed/i);
  assert.match(reviewSource, /Receipt \+ Motive required/);
  assert.match(reviewSource, /not confirmed loss, refund, supplier liability, accounting adjustment, or payment approval/i);
  assert.match(modelSource, /OBSERVED_PRECISION_RATE_BAND = "0\.0005"/);
  assert.match(modelSource, /review_priority: isObservedPrecisionCandidate/);
});
