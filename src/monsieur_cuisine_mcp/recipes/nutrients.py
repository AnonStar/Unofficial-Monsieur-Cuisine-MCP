"""Nutrient payload helpers (build and merge whole-number nutrient amounts)."""


def _build_nutrients(calories, protein, carbohydrate, fat) -> list[dict]:
    specs = [
        ("calories", calories, "kCal"),
        ("protein", protein, "g"),
        ("carbohydrate", carbohydrate, "g"),
        ("fat", fat, "g"),
    ]
    # The API requires whole-number nutrient amounts, so round to the nearest
    # integer (the web form only accepts integers in these fields).
    return [{"name": n, "amount": round(v), "unit": u} for n, v, u in specs if v is not None]


_NUTRIENT_UNITS = {"calories": "kCal", "protein": "g", "carbohydrate": "g", "fat": "g"}


def _merge_nutrients(existing: list[dict] | None, calories, protein, carbohydrate, fat) -> list[dict]:
    """Overlay any supplied nutrient values onto the recipe's existing ones,
    keeping the others intact. Amounts are rounded to whole numbers (the API
    rejects fractional nutrient amounts)."""
    by_name = {n.get("name"): dict(n) for n in (existing or [])}
    for name, value in (
        ("calories", calories), ("protein", protein),
        ("carbohydrate", carbohydrate), ("fat", fat),
    ):
        if value is not None:
            by_name[name] = {"name": name, "amount": round(value), "unit": _NUTRIENT_UNITS[name]}
    return list(by_name.values())
