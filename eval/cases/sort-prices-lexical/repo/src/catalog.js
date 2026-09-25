function comparePrices(a, b) {
  return String(a.price).localeCompare(String(b.price));
}

function sortByPrice(products, direction = "asc") {
  const sorted = [...products].sort(comparePrices);
  return direction === "desc" ? sorted.reverse() : sorted;
}

function cheapest(products) {
  return sortByPrice(products)[0];
}

module.exports = { sortByPrice, cheapest };
