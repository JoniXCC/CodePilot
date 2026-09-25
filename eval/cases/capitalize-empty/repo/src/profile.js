const { formatDisplayName } = require("./strings");

function renderProfileHeader(user) {
  return `<h1>${formatDisplayName(user)}</h1><p>${user.email}</p>`;
}

module.exports = { renderProfileHeader };
