import assert from "node:assert/strict";
import test from "node:test";

import {
  OBSERVED_PRECISION_RATE_BAND,
  buildFuelReview,
  compareAbsoluteDecimals,
  isObservedPrecisionCandidate,
  sumDecimalStrings,
} from "../src/fuelReviewModel.js";

const difference = (overrides = {}) => ({
  status: "price_difference",
  category: "TRUCK_FUEL",
  product_code: "ULSD",
  line_number: 1,
  rate_difference: "0.0001",
  analytical_impact: "0.01000",
  ...overrides,
});

test("observed precision cue includes both signs at the 0.0005 boundary without changing status", () => {
  for (const rate_difference of ["0.0005", "-0.0005", "0.0001", "-0.0001"]) {
    const line = difference({ rate_difference });
    assert.equal(isObservedPrecisionCandidate(line), true);
    assert.equal(line.status, "price_difference");
  }
  assert.equal(OBSERVED_PRECISION_RATE_BAND, "0.0005");
});

test("line 66 sized delta stays in investigate and sorts ahead of tiny differences", () => {
  const line66 = difference({
    line_number: 66,
    category: "REEFER_FUEL",
    product_code: "ULSR",
    rate_difference: "0.1635",
    analytical_impact: "1.70040",
  });
  const small = difference({ line_number: 90, rate_difference: "-0.0005", analytical_impact: "-0.07475" });
  const review = buildFuelReview({ lines: [small, line66] });
  assert.deepEqual(review.investigate.map((line) => line.line_number), [66]);
  assert.deepEqual(review.precisionCandidates.map((line) => line.line_number), [90]);
  assert.equal(review.priceDifferences[0].line_number, 66);
  assert.equal(review.netAnalyticalImpact, "1.62565");
  assert.equal(review.openAnalyticalImpact, "1.62565");
});

test("approved-no-action remains a technical discrepancy but leaves open queues", () => {
  const approved = difference({
    line_number: 90,
    rate_difference: "-0.0005",
    analytical_impact: "-0.07475",
    review: { disposition: "approved_no_action", approved: true },
  });
  const open = difference({
    line_number: 66,
    rate_difference: "0.1635",
    analytical_impact: "1.70040",
    review: { disposition: "not_reviewed", approved: false },
  });
  const review = buildFuelReview({ lines: [approved, open] });
  assert.equal(review.priceDifferences.length, 2);
  assert.deepEqual(review.openPriceDifferences.map((line) => line.line_number), [66]);
  assert.deepEqual(review.approvedDifferences.map((line) => line.line_number), [90]);
  assert.equal(review.approvedDifferences[0].status, "price_difference");
  assert.equal(review.openAnalyticalImpact, "1.70040");
  assert.equal(review.approvedAnalyticalImpact, "-0.07475");
  assert.equal(review.netAnalyticalImpact, "1.62565");
});

test("DEF quantity review is separate from supplier price differences", () => {
  const def = {
    status: "not_applicable",
    category: "DEF",
    product_code: "DEFD",
    quantity_verification_status: "pending_receipt_and_motive",
  };
  const review = buildFuelReview({ lines: [difference(), def] });
  assert.equal(review.priceDifferences.length, 1);
  assert.equal(review.defPending.length, 1);
});

test("decimal helpers preserve exact signed source arithmetic", () => {
  assert.equal(sumDecimalStrings(["-0.37269", "1.66573"]), "1.29304");
  assert.equal(sumDecimalStrings(["1.70040", "-0.40736"]), "1.29304");
  assert.equal(compareAbsoluteDecimals("-0.0005", "0.0005"), 0);
  assert.equal(compareAbsoluteDecimals("0.1635", "0.0005"), 1);
});
