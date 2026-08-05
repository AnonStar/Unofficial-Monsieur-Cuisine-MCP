import argparse
import asyncio
import json
import logging

from playwright.async_api import async_playwright

from .config import (
    MC_AUTHENTICATION_SSO_DOMAIN,
    MC_AUTHENTICATION_TIMEOUT_SECONDS,
    MC_DOMAIN,
    MC_LOGIN_ENTRY_URL,
    STATE_DIR,
    STORAGE_STATE_PATH,
)
from .logging_config import setup_logging

logger = logging.getLogger(__name__)


class NotLoggedInError(RuntimeError):
    """Raised when an authenticated call is made without a saved session."""

    def __init__(self) -> None:
        super().__init__(
            "No saved Monsieur Cuisine session found. Run `uv run "
            "monsieur-cuisine-mcp-login` to log in once, then retry."
        )


async def login_interactive(headless: bool = False) -> None:
    """Open a real browser window and wait for the user to log in manually.

    No credentials are handled by this code: the user completes the Lidl
    login (including any CAPTCHA/2FA) themselves in the opened window.
    Success is detected by watching the actual domain round trip (mc ->
    accounts.lidl.com -> mc) rather than matching URL paths, since the
    require-login page uses locale-specific slugs (e.g. "wymagane-logowanie"
    for pl) that don't all contain the substring "login". Once the round
    trip completes, the resulting session (cookies + storage) is persisted
    to STORAGE_STATE_PATH for reuse by the MCP server.
    """
    logger.debug("Session state directory: %s", STATE_DIR)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        logger.debug("Launching Chromium (headless=%s)", headless)
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        logger.debug("Navigating to %s", MC_LOGIN_ENTRY_URL)
        await page.goto(MC_LOGIN_ENTRY_URL, wait_until="domcontentloaded", timeout=45000)
        logger.debug("Page loaded, current URL: %s", page.url)

        logger.info(
            "Click 'Log in' and log in manually (including any CAPTCHA/2FA). "
            "Waiting for %s to open...",
            MC_AUTHENTICATION_SSO_DOMAIN,
        )
        await page.wait_for_url(
            lambda url: MC_AUTHENTICATION_SSO_DOMAIN in url,
            timeout=MC_AUTHENTICATION_TIMEOUT_SECONDS * 1000,
        )
        logger.debug("Detected SSO domain %s, current URL: %s", MC_AUTHENTICATION_SSO_DOMAIN, page.url)

        logger.info(
            "Now on %s — finish logging in in the browser window. Waiting for the "
            "redirect back to %s...",
            MC_AUTHENTICATION_SSO_DOMAIN,
            MC_DOMAIN,
        )
        await page.wait_for_url(
            lambda url: MC_DOMAIN in url and MC_AUTHENTICATION_SSO_DOMAIN not in url,
            timeout=MC_AUTHENTICATION_TIMEOUT_SECONDS * 1000,
        )
        logger.debug("Detected return to %s, current URL: %s", MC_DOMAIN, page.url)

        cookies = await context.cookies()
        logger.debug("Session contains %d cookies (count only, no values logged)", len(cookies))

        await context.storage_state(path=str(STORAGE_STATE_PATH))
        logger.info("Logged in. Session saved to %s", STORAGE_STATE_PATH)

        await browser.close()
        logger.debug("Browser closed")


def has_saved_session() -> bool:
    exists = STORAGE_STATE_PATH.exists()
    logger.debug("Checking saved session %s -> %s", STORAGE_STATE_PATH, exists)
    return exists


def load_session_cookies() -> dict[str, str]:
    """Load the Monsieur Cuisine session cookies saved by login_interactive.

    Only cookies scoped to MC_DOMAIN are returned, since those are what the
    site's own `/proxy-api` endpoint (used for authenticated calls like
    favorite recipes) checks - the accounts.lidl.com/SSO cookies saved
    alongside them are not needed for it.

    Raises NotLoggedInError if no session has been saved yet.
    """
    if not has_saved_session():
        raise NotLoggedInError()

    state = json.loads(STORAGE_STATE_PATH.read_text())
    cookies = {
        cookie["name"]: cookie["value"]
        for cookie in state.get("cookies", [])
        if cookie["domain"].lstrip(".").endswith(MC_DOMAIN)
    }
    logger.debug("Loaded %d session cookies scoped to %s", len(cookies), MC_DOMAIN)
    return cookies


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive login to Monsieur Cuisine")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose event logging (DEBUG level)",
    )
    args = parser.parse_args()
    setup_logging(logging.DEBUG if args.debug else None)
    asyncio.run(login_interactive())


if __name__ == "__main__":
    main()
