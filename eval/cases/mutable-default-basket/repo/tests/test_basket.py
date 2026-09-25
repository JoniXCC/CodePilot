from shop.basket import Basket
from shop.checkout import basket_total


def test_add_items():
    basket = Basket()
    basket.add("apple")
    basket.add("milk")
    assert basket.total_items() == 2


def test_new_baskets_are_independent():
    first = Basket()
    first.add("bread")
    second = Basket()
    assert second.items == []


def test_basket_can_start_with_items():
    assert Basket(["apple"]).total_items() == 1


def test_total():
    basket = Basket(["apple", "bread"])
    assert basket_total(basket) == 150
