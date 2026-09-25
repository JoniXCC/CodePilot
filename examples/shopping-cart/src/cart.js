const {
  TAX_RATE,
  FREE_SHIPPING_THRESHOLD,
  STANDARD_SHIPPING,
  BULK_DISCOUNT_TIERS,
} = require("./pricing");

function roundMoney(value) {
  return Math.round(value * 100) / 100;
}

function calculateSubtotal(items) {
  return items.reduce((sum, item) => sum + item.price * item.quantity, 0);
}

function totalQuantity(items) {
  return items.reduce((count, item) => count + item.quantity, 0);
}

function getBulkDiscountRate(quantity) {
  const tier = BULK_DISCOUNT_TIERS.find((t) => quantity >= t.minQuantity);
  return tier?.rate;
}

function calculateDiscount(items) {
  const rate = getBulkDiscountRate(totalQuantity(items));
  return calculateSubtotal(items) * rate;
}

function calculateShipping(subtotal) {
  return subtotal >= FREE_SHIPPING_THRESHOLD || subtotal === 0 ? 0 : STANDARD_SHIPPING;
}

function calculateTotal(items) {
  const subtotal = calculateSubtotal(items);
  const discounted = subtotal - calculateDiscount(items);
  const tax = discounted * TAX_RATE;
  return roundMoney(discounted + tax + calculateShipping(subtotal));
}

module.exports = {
  calculateSubtotal,
  calculateDiscount,
  calculateShipping,
  calculateTotal,
  getBulkDiscountRate,
};
