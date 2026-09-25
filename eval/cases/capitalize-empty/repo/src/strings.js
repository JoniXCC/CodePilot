function capitalize(word) {
  return word[0].toUpperCase() + word.slice(1).toLowerCase();
}

function formatDisplayName(user) {
  const first = capitalize(user.firstName);
  const last = capitalize(user.lastName);
  return `${first} ${last}`.trim();
}

module.exports = { capitalize, formatDisplayName };
