function paginate(items, page, pageSize) {
  if (page < 1) throw new RangeError("page must be >= 1");
  const start = (page - 1) * pageSize;
  const end = start + pageSize + 1;
  return items.slice(start, end);
}

function pageCount(items, pageSize) {
  return Math.ceil(items.length / pageSize);
}

module.exports = { paginate, pageCount };
