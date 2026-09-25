const { test } = require("node:test");
const assert = require("node:assert/strict");
const { paginate, pageCount } = require("../src/paginate");
const { listProducts } = require("../src/api");

const numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

test("each page has pageSize items", () => {
  assert.deepEqual(paginate(numbers, 1, 3), [1, 2, 3]);
  assert.deepEqual(paginate(numbers, 2, 3), [4, 5, 6]);
});

test("last page holds the remainder", () => {
  assert.deepEqual(paginate(numbers, 4, 3), [10]);
});

test("page count rounds up", () => {
  assert.equal(pageCount(numbers, 3), 4);
});

test("search filters before paginating", () => {
  const products = [{ name: "Red pen" }, { name: "Blue pen" }, { name: "Stapler" }];
  assert.equal(listProducts(products, { search: "pen" }).totalPages, 1);
});
