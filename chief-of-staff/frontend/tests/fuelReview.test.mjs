import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const appSource = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
const reviewSource = await readFile(new URL("../src/components/FuelReview.jsx", import.meta.url), "utf8");
const modelSource = await readFile(new URL("../src/fuelReviewModel.js", import.meta.url), "utf8");

test("executive workspace exposes the fuel review route", () => {
  assert.match(appSource, /key: "fuel-review"/);
  assert.match(appSource, /import FuelReview/);
  assert.match(appSource, /page === "fuel-review" \? <FuelReview \/>/);
});

test("fuel review keeps evidence GET separate from bounded review disposition writes", () => {
  assert.match(reviewSource, /apiClient\.get\(`\/api\/v1\/fuel\/invoices\/\$\{runId\}\/price-reconciliation`\)/);
  assert.match(reviewSource, /evidence_read_only/);
  assert.match(reviewSource, /price-reconciliation\/\$\{line\.invoice_line_id\}\/approve/);
  assert.match(reviewSource, /price-reconciliation\/approve-precision/);
  assert.match(reviewSource, /price-reconciliation\/\$\{line\.invoice_line_id\}\/reopen/);
  assert.doesNotMatch(reviewSource, /apiClient\.delete/);
});

test("approval controls preserve technical discrepancy and accounting boundaries", () => {
  assert.match(reviewSource, /Approve discrepancy/);
  assert.match(reviewSource, /Approve all precision/);
  assert.match(reviewSource, /Approved — no action/);
  assert.match(reviewSource, /previous approval remains in audit history/i);
  assert.match(reviewSource, /reason is required to approve a material discrepancy/i);
  assert.match(reviewSource, /does not convert them to matches/i);
  assert.match(reviewSource, /no supplier rounding rule or tolerance is assumed/i);
  assert.match(reviewSource, /does not adjust, pay, contact a supplier, post to accounting/i);
  assert.match(reviewSource, /not confirmed loss, refund, supplier liability, accounting adjustment, or payment approval/i);
  assert.match(modelSource, /OBSERVED_PRECISION_RATE_BAND = "0\.0005"/);
  assert.match(modelSource, /review_disposition/);
  assert.match(modelSource, /approvedDifferences/);
});

test("DEF evidence gate remains separate", () => {
  assert.match(reviewSource, /Receipt \+ Motive required/);
  assert.match(reviewSource, /pending until both required evidence classes are verified/i);
});
