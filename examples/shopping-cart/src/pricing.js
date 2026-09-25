// Store-wide pricing rules.

const TAX_RATE = 0.2;

const FREE_SHIPPING_THRESHOLD = 50;
const STANDARD_SHIPPING = 4.99;

// Bulk discount tiers, based on the total number of items in the cart.
const BULK_DISCOUNT_TIERS = [
  { minQuantity: 50, rate: 0.1 },
  { minQuantity: 10, rate: 0.05 },
  { minQuantity: 1, rate: 0 },
];

module.exports = {
  TAX_RATE,
  FREE_SHIPPING_THRESHOLD,
  STANDARD_SHIPPING,
  BULK_DISCOUNT_TIERS,
};
