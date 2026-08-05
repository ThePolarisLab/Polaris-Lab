import assert from "node:assert/strict";
import test from "node:test";

import { money } from "../src/formatters.js";

test("money renders nullish KPI values as unavailable dash", () => {
  assert.equal(money(null), "—");
  assert.equal(money(undefined), "—");
});

test("money still renders numeric zero as currency", () => {
  assert.equal(money(0), "$0");
  assert.equal(money("0"), "$0");
});
