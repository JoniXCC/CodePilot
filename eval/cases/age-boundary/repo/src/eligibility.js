const MINIMUM_AGE = 18;

function ageOn(birthDate, today) {
  const years = today.getFullYear() - birthDate.getFullYear();
  const hadBirthdayThisYear =
    today.getMonth() > birthDate.getMonth() ||
    (today.getMonth() === birthDate.getMonth() && today.getDate() >= birthDate.getDate());
  return hadBirthdayThisYear ? years : years - 1;
}

function canRegister(birthDate, today = new Date()) {
  return ageOn(birthDate, today) > MINIMUM_AGE;
}

module.exports = { ageOn, canRegister, MINIMUM_AGE };
