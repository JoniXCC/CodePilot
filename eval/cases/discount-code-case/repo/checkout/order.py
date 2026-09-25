from checkout.discounts import apply_discount


def order_total(prices: list[float], code: str | None = None) -> float:
    return apply_discount(sum(prices), code)
