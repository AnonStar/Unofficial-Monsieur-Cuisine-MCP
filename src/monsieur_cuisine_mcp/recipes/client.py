"""Session-authenticated proxy-api client and error handling.

Everything user-specific (favorites, own recipes) goes through the site's
same-origin `/proxy-api`, which forwards to mc-api.tecpal.com with the logged-in
browser session. This module owns that call and its error translation.
"""
import logging
import uuid

import httpx

from .. import auth
from ..config import (
    MC_API_REQUEST_TIMEOUT_SECONDS,
    MC_BASE_URL,
    MC_BROWSER_USER_AGENT,
    MC_PROXY_API_URL,
)

logger = logging.getLogger(__name__)


def _language_path_prefix(language: str) -> str:
    """Map a locale (e.g. "pl-PL") to the site's URL path prefix (e.g. "pl").

    The WordPress create-recipe pages and the guide's admin-ajax endpoint
    determine their language from this path prefix, not from a parameter.
    """
    return language.split("-")[0].lower()


async def _call_proxy_api(
    endpoint: str,
    method: str,
    language: str,
    payload: dict | None = None,
    timeout: float = MC_API_REQUEST_TIMEOUT_SECONDS,
) -> dict:
    """Call the site's own session-authenticated `/proxy-api` endpoint, which
    forwards {"endpoint", "lang", "method", "payload"} to the underlying
    mc-api.tecpal.com API on behalf of the logged-in user. Used for endpoints
    that are user-specific (e.g. favorites, own recipes) and not reachable
    through the public mc-api.tecpal.com API directly.

    Requires a saved login session (run `uv run monsieur-cuisine-mcp-login`
    once beforehand) - raises auth.NotLoggedInError if none is found.
    """
    cookies = auth.load_session_cookies()

    body: dict = {"endpoint": endpoint, "lang": language, "method": method}
    if payload is not None:
        body["payload"] = payload
    # Mirror the headers a same-origin fetch from the web app sends. The site's
    # Akamai bot protection returns 403 on write requests that lack a real
    # browser fingerprint (User-Agent / Origin / Referer / Accept), so these are
    # sent on every call, not just the writes.
    prefix = _language_path_prefix(language)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": language,
        "Content-Type": "application/json",
        "device-type": "web",
        "x-request-id": str(uuid.uuid4()),
        "User-Agent": MC_BROWSER_USER_AGENT,
        "Origin": MC_BASE_URL,
        "Referer": f"{MC_BASE_URL}/{prefix}/",
    }
    logger.debug("Calling proxy-api: endpoint=%s method=%s language=%s", endpoint, method, language)

    async with httpx.AsyncClient(cookies=cookies, timeout=timeout) as client:
        response = await client.post(MC_PROXY_API_URL, json=body, headers=headers)
    _raise_for_mc_status(response, f"{method} {endpoint}")
    return response.json()


class MCRequestError(RuntimeError):
    """A Monsieur Cuisine proxy-api request failed with an actionable reason."""


def _api_error_message(response: "httpx.Response") -> str | None:
    """Return the mc-api's own error message from a JSON body, if present.

    The mc-api (Express backend) reports business errors as JSON like
    {"code":40008,"message":"Invalid category"} - even under HTTP 403. Surfacing
    that message is far more useful than guessing, so pull it out when available.
    """
    ctype = response.headers.get("content-type", "")
    if "json" not in ctype.lower():
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict) and body.get("message"):
        api_code = body.get("code")
        suffix = f" (code {api_code})" if api_code not in (None, 0) else ""
        return f"{body['message']}{suffix}"
    return None


def _raise_for_mc_status(response: "httpx.Response", context: str) -> None:
    """Raise a clear, actionable error for a failed proxy-api response.

    The mc-api often returns HTTP 403 for plain business errors (e.g.
    {"code":40008,"message":"Invalid category"}), NOT only for auth/bot blocks -
    so always surface the API's own message when there is one, and fall back to
    the session/bot-protection guidance only when the body is opaque.
    """
    code = response.status_code
    if code < 400:
        return
    api_message = _api_error_message(response)
    if api_message:
        raise MCRequestError(f"{context} failed ({code}): {api_message}")
    if code in (401, 403):
        raise MCRequestError(
            f"{context} was rejected ({code}) with no API message. This usually means "
            "the saved login session expired - run `uv run monsieur-cuisine-mcp-login` "
            "again - or automated requests are being blocked; wait a bit and retry."
        )
    if code == 429:
        raise MCRequestError(f"{context} was rate-limited (429). Wait a bit and retry, spacing calls out.")
    if code >= 500:
        raise MCRequestError(
            f"{context} hit a transient server/gateway error ({code}). Retry shortly. "
            "Note: a create call may have still succeeded server-side, so check before recreating."
        )
    raise MCRequestError(f"{context} failed ({code}): {response.text[:300]}")
