import assert from "node:assert/strict";
import test from "node:test";

import { money, moneyExact } from "../src/formatters.js";

test("money renders nullish KPI values as unavailable dash", () => {
  assert.equal(money(null), "—");
  assert.equal(money(undefined), "—");
});

test("money still renders numeric zero as currency", () => {
  assert.equal(money(0), "$0");
  assert.equal(money("0"), "$0");
});

test("moneyExact preserves cents for financial reconciliation", () => {
  assert.equal(moneyExact("86284.11"), "$86,284.11");
  assert.equal(moneyExact(0), "$0.00");
  assert.equal(moneyExact(null), "—");
});
