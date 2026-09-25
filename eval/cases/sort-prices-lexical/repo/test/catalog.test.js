const { test } = require("node:test");
const assert = require("node:assert/strict");
const { sortByPrice, cheapest } = require("../src/catalog");

const products = [
  { name: "Lamp", price: 2500 },
  { name: "Desk", price: 10000 },
  { name: "Mug", price: 900 },
];

test("sorts numerically by price", () => {
  assert.deepEqual(sortByPrice(products).map((p) => p.name), ["Mug", "Lamp", "Desk"]);
});

test("can sort descending", () => {
  assert.equal(sortByPrice(products, "desc")[0].name, "Desk");
});

test("does not mutate the input", () => {
  const copy = [...products];
  sortByPrice(products);
  assert.deepEqual(products, copy);
});

test("finds the cheapest product", () => {
  assert.equal(cheapest(products).name, "Mug");
});
