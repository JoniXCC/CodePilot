const { test } = require("node:test");
const assert = require("node:assert/strict");
const { ageOn, canRegister } = require("../src/eligibility");

const today = new Date(2026, 5, 15); // 15 June 2026

test("computes age before and after the birthday", () => {
  assert.equal(ageOn(new Date(2000, 5, 16), today), 25);
  assert.equal(ageOn(new Date(2000, 5, 15), today), 26);
});

test("users who turn 18 today can register", () => {
  assert.equal(canRegister(new Date(2008, 5, 15), today), true);
});

test("17 year olds cannot register", () => {
  assert.equal(canRegister(new Date(2008, 5, 16), today), false);
});
