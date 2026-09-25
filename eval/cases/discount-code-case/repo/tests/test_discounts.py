from checkout.discounts import apply_discount, discount_rate
from checkout.order import order_total


def test_known_code():
    assert discount_rate("SAVE10") == 0.10


def test_codes_are_case_insensitive():
    assert apply_discount(50.0, "save10") == 45.0


def test_unknown_code():
    assert apply_discount(50.0, "BOGUS") == 50.0


def test_order_total_without_code():
    assert order_total([10.0, 5.5]) == 15.5
