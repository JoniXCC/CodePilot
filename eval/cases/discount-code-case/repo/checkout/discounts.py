DISCOUNT_CODES = {"SAVE10": 0.10, "WELCOME5": 0.05}


def discount_rate(code: str) -> float:
    return DISCOUNT_CODES.get(code.strip(), 0.0)


def apply_discount(total: float, code: str | None) -> float:
    if not code:
        return total
    return round(total * (1 - discount_rate(code)), 2)
