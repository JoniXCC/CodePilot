const { paginate, pageCount } = require("./paginate");

function listProducts(products, { page = 1, pageSize = 3, search = "" } = {}) {
  const matching = products.filter((p) => p.name.toLowerCase().includes(search.toLowerCase()));
  return {
    items: paginate(matching, page, pageSize),
    page,
    totalPages: pageCount(matching, pageSize),
  };
}

module.exports = { listProducts };
