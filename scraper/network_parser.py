import json
from typing import Any


def walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def json_candidates(text: str) -> list[Any]:
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return []
    return [item for item in walk(value) if isinstance(item, dict)]


def product_candidates(items: list[Any]) -> list[dict]:
    keys = {"price", "priceAmount", "salePrice", "compare_at_price", "compareAtPrice"}
    return [x for item in items for x in walk(item) if isinstance(x, dict) and keys.intersection(x)]

