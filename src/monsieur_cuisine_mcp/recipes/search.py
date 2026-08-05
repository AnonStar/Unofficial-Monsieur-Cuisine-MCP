"""Public recipe search and detail reads (mc-api.tecpal.com).

Search and filters use the public API with no auth. get_recipe reads public
recipes the same way, but falls back to the authenticated own-recipe endpoint
for the caller's own draft/private recipes (which the public API won't serve).
"""
import logging

import httpx

from .. import auth
from ..config import (
    MC_API_BASE_URL,
    MC_API_DEFAULT_LANGUAGE,
    MC_API_REQUEST_TIMEOUT_SECONDS,
)
from .client import MCRequestError, _call_proxy_api

logger = logging.getLogger(__name__)


# Only the Monsieur Cuisine Smart (MC3.0) is supported, so the search device
# filter accepts just that.
VALID_DEVICE_TYPES = {"MC3.0"}
VALID_MEDIA = {"video"}
VALID_SOURCES = {"official", "member"}


def _build_search_params(
    query: str | None,
    device_type: str | None,
    categories: list[str] | None,
    ingredient_categories: list[str] | None,
    complexity: str | None,
    duration_min: int | None,
    duration_max: int | None,
    rating_min: float | None,
    rating_max: float | None,
    media: str | None,
    source: str | None,
    calories_min: float | None,
    calories_max: float | None,
    protein_min: float | None,
    protein_max: float | None,
    carbohydrate_min: float | None,
    carbohydrate_max: float | None,
    fat_min: float | None,
    fat_max: float | None,
    sort_field: str,
    sort_direction: str,
) -> httpx.QueryParams:
    params: list[tuple[str, str]] = []
    if query:
        params.append(("q", query))
    if device_type:
        params.append(("filters[deviceType]", device_type))
    for category in categories or []:
        params.append(("filters[category][]", category))
    for ingredient_category in ingredient_categories or []:
        params.append(("filters[ingredientCategory][]", ingredient_category))
    if complexity:
        params.append(("filters[complexity]", complexity))
    if duration_min is not None:
        params.append(("filters[duration][from]", str(duration_min)))
    if duration_max is not None:
        params.append(("filters[duration][to]", str(duration_max)))
    if rating_min is not None:
        params.append(("filters[rating][from]", str(rating_min)))
    if rating_max is not None:
        params.append(("filters[rating][to]", str(rating_max)))
    if media:
        params.append(("filters[media]", media))
    if source:
        params.append(("filters[source]", source))
    if calories_min is not None:
        params.append(("filters[nutrientsCalories][from]", str(calories_min)))
    if calories_max is not None:
        params.append(("filters[nutrientsCalories][to]", str(calories_max)))
    if protein_min is not None:
        params.append(("filters[nutrientsProtein][from]", str(protein_min)))
    if protein_max is not None:
        params.append(("filters[nutrientsProtein][to]", str(protein_max)))
    if carbohydrate_min is not None:
        params.append(("filters[nutrientsCarbohydrate][from]", str(carbohydrate_min)))
    if carbohydrate_max is not None:
        params.append(("filters[nutrientsCarbohydrate][to]", str(carbohydrate_max)))
    if fat_min is not None:
        params.append(("filters[nutrientsFat][from]", str(fat_min)))
    if fat_max is not None:
        params.append(("filters[nutrientsFat][to]", str(fat_max)))
    params.append(("sortBy[0][field]", sort_field))
    params.append(("sortBy[0][direction]", sort_direction))
    return httpx.QueryParams(tuple(params))


async def search_recipes(
    query: str | None = None,
    device_type: str | None = None,
    categories: list[str] | None = None,
    ingredient_categories: list[str] | None = None,
    complexity: str | None = None,
    duration_min: int | None = None,
    duration_max: int | None = None,
    rating_min: float | None = None,
    rating_max: float | None = None,
    media: str | None = None,
    source: str | None = None,
    calories_min: float | None = None,
    calories_max: float | None = None,
    protein_min: float | None = None,
    protein_max: float | None = None,
    carbohydrate_min: float | None = None,
    carbohydrate_max: float | None = None,
    fat_min: float | None = None,
    fat_max: float | None = None,
    sort_field: str = "lastUpdated",
    sort_direction: str = "DESC",
    page: int = 1,
    language: str = MC_API_DEFAULT_LANGUAGE,
) -> dict:
    """Search Monsieur Cuisine recipes via the public mc-api.tecpal.com search
    endpoint. No authentication is required for this call.

    `categories`, `ingredient_categories` and `complexity` are all
    language-dependent: their valid identifiers differ per `language` (e.g.
    category IDs and complexity labels for "pl-PL" are entirely different
    from "en-US"). Always fetch valid values via get_recipe_filters(language)
    using the *same* language before calling this function.

    `source`, and the nutrient range filters (calories/protein/carbohydrate/
    fat), are not part of get_recipe_filters()'s response - they are an
    "extra" set of filters the web UI unlocks separately, discovered by
    inspecting live search requests rather than the filters endpoint.
    """
    if device_type is not None and device_type not in VALID_DEVICE_TYPES:
        raise ValueError(f"Invalid device_type {device_type!r}, expected one of {sorted(VALID_DEVICE_TYPES)}")
    if media is not None and media not in VALID_MEDIA:
        raise ValueError(f"Invalid media {media!r}, expected one of {sorted(VALID_MEDIA)}")
    if source is not None and source not in VALID_SOURCES:
        raise ValueError(f"Invalid source {source!r}, expected one of {sorted(VALID_SOURCES)}")

    params = _build_search_params(
        query=query,
        device_type=device_type,
        categories=categories,
        ingredient_categories=ingredient_categories,
        complexity=complexity,
        duration_min=duration_min,
        duration_max=duration_max,
        rating_min=rating_min,
        rating_max=rating_max,
        media=media,
        source=source,
        calories_min=calories_min,
        calories_max=calories_max,
        protein_min=protein_min,
        protein_max=protein_max,
        carbohydrate_min=carbohydrate_min,
        carbohydrate_max=carbohydrate_max,
        fat_min=fat_min,
        fat_max=fat_max,
        sort_field=sort_field,
        sort_direction=sort_direction,
    )
    url = f"{MC_API_BASE_URL}/api/v1/recipes/search/page/{page}"
    logger.debug("Searching recipes: url=%s params=%s language=%s", url, params, language)

    async with httpx.AsyncClient(timeout=MC_API_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(url, params=params, headers={"Accept-Language": language})
    response.raise_for_status()
    data = response.json()

    result_data = data.get("data", {})
    logger.debug(
        "Search returned %d/%d recipes (page %d/%s)",
        len(result_data.get("recipes", [])),
        result_data.get("total"),
        result_data.get("currentPage", page),
        result_data.get("totalPage"),
    )
    return data


async def get_recipe_filters(language: str = MC_API_DEFAULT_LANGUAGE) -> dict:
    """Fetch the available recipe search filters (and their valid option
    identifiers) for a given language, via the public mc-api.tecpal.com API.
    No authentication is required for this call.

    The `category`, `ingredientCategory` and `complexity` option identifiers
    returned here are specific to `language` and must be requested again
    (with the matching language) whenever the search language changes.

    Note: this does not include `source` or the nutrient range filters
    (calories/protein/carbohydrate/fat) supported by search_recipes - those
    are an "extra" set of filters not listed by this endpoint.
    """
    url = f"{MC_API_BASE_URL}/api/v1/recipes/filters"
    logger.debug("Fetching recipe filters: url=%s language=%s", url, language)

    async with httpx.AsyncClient(timeout=MC_API_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(url, headers={"Accept-Language": language})
    response.raise_for_status()
    data = response.json()

    filters = data.get("data", {}).get("filters", [])
    logger.debug("Fetched %d filter groups: %s", len(filters), [f.get("identifier") for f in filters])
    return data


async def get_recipe(recipe_id: str, language: str = MC_API_DEFAULT_LANGUAGE) -> dict:
    """Fetch full details for a single recipe by numeric id.

    `recipe_id` is the numeric recipe id (the `id` field from search_recipes /
    list_my_recipes results), not the URL slug. The response includes
    ingredients, step-by-step instructions per serving size, and top-level
    `nutrients` for the default serving size.

    Published recipes are read from the public mc-api.tecpal.com API (no auth).
    The public API refuses unpublished recipes ("Recipe is not published"), so
    for the caller's OWN draft/private-publish recipes this transparently falls
    back to the authenticated own-recipe endpoint, which requires a saved login
    session. (The two sources return slightly different recipe shapes.)
    """
    url = f"{MC_API_BASE_URL}/api/v2/recipes/{recipe_id}"
    logger.debug("Fetching recipe detail: url=%s language=%s", url, language)

    async with httpx.AsyncClient(timeout=MC_API_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(url, headers={"Accept-Language": language})

    if response.status_code < 400:
        data = response.json()
        recipe = data.get("data", {}).get("recipe", {})
        logger.debug("Fetched public recipe %s: %r", recipe_id, recipe.get("name"))
        return data

    # The public endpoint only serves published recipes (409 "Recipe is not
    # published" for a user's own draft/private one). Retry via the authenticated
    # own-recipe endpoint so callers can still read their own recipes by id.
    if response.status_code not in (401, 403, 404, 409):
        response.raise_for_status()

    try:
        data = await _call_proxy_api(
            f"api/v3/auth/user/recipes/{recipe_id}", method="GET", language=language
        )
    except auth.NotLoggedInError:
        raise MCRequestError(
            f"Recipe {recipe_id} is not publicly available ({response.status_code}). "
            "If it is your own draft/private recipe, log in first "
            "(`uv run monsieur-cuisine-mcp-login`) so it can be read."
        ) from None

    recipe = (data.get("data") or {}).get("recipe") or {}
    if not recipe:
        raise MCRequestError(
            f"Recipe {recipe_id} is not published and is not one of your own "
            "recipes (or the id is wrong). Public recipes are readable by id; "
            "your own drafts/private recipes are readable when logged in."
        )
    logger.debug("Fetched own recipe %s via authenticated endpoint: %r", recipe_id, recipe.get("title"))
    return data
