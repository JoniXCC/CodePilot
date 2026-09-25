from shop.basket import Basket

PRICES = {"apple": 30, "bread": 120, "milk": 90}


def basket_total(basket: Basket) -> int:
    return sum(PRICES.get(item, 0) for item in basket.items)
