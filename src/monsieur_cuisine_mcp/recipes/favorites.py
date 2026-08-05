"""The logged-in user's favorite (bookmarked) recipes."""
import logging

from ..config import MC_API_DEFAULT_LANGUAGE
from .client import _call_proxy_api

logger = logging.getLogger(__name__)


async def list_favorite_recipes(
    page: int = 1,
    page_size: int = 12,
    sort_field: str = "date",
    sort_direction: str = "DESC",
    language: str = MC_API_DEFAULT_LANGUAGE,
) -> dict:
    """List the logged-in user's favorite (bookmarked) recipes, with full
    recipe details, via the site's authenticated `/proxy-api` endpoint.

    Requires a saved login session (run `uv run monsieur-cuisine-mcp-login`
    once beforehand) - raises auth.NotLoggedInError if none is found. Unlike
    search_recipes/get_recipe, this cannot use the public mc-api.tecpal.com
    API directly: favorites are user-specific and only exposed through the
    web app's own session-authenticated proxy.

    Args:
        page: 1-based page number.
        page_size: Number of favorites per page.
        sort_field: Field to sort by, e.g. "date".
        sort_direction: "ASC" or "DESC".
        language: Result language/locale, e.g. "pl-PL", "en-US".
    """
    endpoint = (
        f"api/v2/bookmarks/recipe/details/page/{page}/size/{page_size}"
        f"?sortBy[0][field]={sort_field}&sortBy[0][direction]={sort_direction}"
    )
    data = await _call_proxy_api(endpoint, method="GET", language=language)

    result_data = data.get("data", {})
    logger.debug(
        "Fetched %d/%d favorite recipes (page %d/%s)",
        len(result_data.get("bookmarks", [])),
        result_data.get("total"),
        result_data.get("currentPage", page),
        result_data.get("totalPage"),
    )
    return data


async def add_favorite_recipe(translation_id: int, language: str = MC_API_DEFAULT_LANGUAGE) -> dict:
    """Add a recipe to the logged-in user's favorites (bookmarks).

    Requires a saved login session (run `uv run monsieur-cuisine-mcp-login`
    once beforehand) - raises auth.NotLoggedInError if none is found.

    `translation_id` is the recipe's *translationId* (from a
    search_recipes/get_recipe result's `translationId` field) - this is NOT
    the same as the numeric recipe `id` used by get_recipe/search_recipes.
    """
    payload = {"bookmarkItem": [{"translationId": translation_id}]}
    data = await _call_proxy_api("api/v2/bookmarks/recipe", method="POST", language=language, payload=payload)
    logger.debug("Added favorite recipe translationId=%s: %s", translation_id, data.get("message"))
    return data


async def remove_favorite_recipe(translation_id: int, language: str = MC_API_DEFAULT_LANGUAGE) -> dict:
    """Remove a recipe from the logged-in user's favorites (bookmarks).

    Requires a saved login session (run `uv run monsieur-cuisine-mcp-login`
    once beforehand) - raises auth.NotLoggedInError if none is found.

    `translation_id` is the bookmark/recipe *translationId* (from a
    list_favorite_recipes result's `translationId` field, or a recipe's
    `translationId` field) - this is NOT the same as the numeric recipe `id`
    used by get_recipe/search_recipes.
    """
    payload = {"bookmarkItem": [{"translationId": translation_id, "isActive": False, "forceDelete": True}]}
    data = await _call_proxy_api("api/v2/bookmarks/recipe", method="PUT", language=language, payload=payload)
    logger.debug("Removed favorite recipe translationId=%s: %s", translation_id, data.get("message"))
    return data
