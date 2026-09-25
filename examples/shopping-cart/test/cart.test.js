const { test } = require("node:test");
const assert = require("node:assert/strict");

const { calculateSubtotal, calculateTotal, calculateShipping } = require("../src/cart");
const { formatPrice } = require("../src/format");

const book = { name: "Book", price: 12.5, quantity: 2 };
const pen = { name: "Pen", price: 1.2, quantity: 10 };

test("subtotal multiplies price by quantity", () => {
  assert.equal(calculateSubtotal([book, pen]), 37);
});

test("total adds tax and shipping for a small order", () => {
  // 25.00 + 20% tax + 4.99 shipping
  assert.equal(calculateTotal([book]), 34.99);
});

test("bulk discount applies from 10 items", () => {
  // subtotal 37, 12 items -> 5% off = 35.15, + 20% tax = 42.18, + shipping 4.99
  assert.equal(calculateTotal([book, pen]), 47.17);
});

test("orders over the threshold ship free", () => {
  assert.equal(calculateShipping(60), 0);
});

test("empty cart total is zero", () => {
  assert.equal(calculateTotal([]), 0);
});

test("prices are formatted in pounds", () => {
  assert.equal(formatPrice(3.5), "£3.50");
});
