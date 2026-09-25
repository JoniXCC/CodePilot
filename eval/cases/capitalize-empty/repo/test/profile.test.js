const { test } = require("node:test");
const assert = require("node:assert/strict");
const { capitalize, formatDisplayName } = require("../src/strings");
const { renderProfileHeader } = require("../src/profile");

test("capitalizes words", () => {
  assert.equal(capitalize("aDA"), "Ada");
});

test("formats first and last name", () => {
  assert.equal(formatDisplayName({ firstName: "ada", lastName: "LOVELACE" }), "Ada Lovelace");
});

test("users without a last name get just the first name", () => {
  assert.equal(formatDisplayName({ firstName: "prince", lastName: "" }), "Prince");
});

test("renders the profile header", () => {
  assert.match(renderProfileHeader({ firstName: "ada", lastName: "lovelace", email: "a@b.c" }), /Ada Lovelace/);
});
