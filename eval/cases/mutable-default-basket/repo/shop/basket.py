class Basket:
    def __init__(self, items: list[str] = []) -> None:
        self.items = items

    def add(self, item: str) -> None:
        self.items.append(item)

    def total_items(self) -> int:
        return len(self.items)
