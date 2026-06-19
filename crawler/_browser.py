"""Shared Playwright helpers for crawlers that need a real, logged-in browser.

X and TikTok block search for anonymous visitors (X redirects to /login,
TikTok renders empty skeleton cards). To get results we drive a real Chromium
through Playwright and reuse a **persistent browser profile** so a one-time
manual login keeps working across runs.

The profile directory can be overridden with the ``BROWSER_PROFILE_DIR`` env
var; otherwise it lives at ``<repo>/data/browser_profile``.
"""

import os

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def profile_dir(name: str) -> str:
    """Return the persistent browser profile directory for ``name``.

    Each platform gets its own profile so different logins don't clash and so
    crawlers can run in parallel without fighting over the same user-data-dir.
    """

    base = os.getenv("BROWSER_PROFILE_DIR")

    if not base:
        base = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "browser_profile",
        )

    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=True)

    return path


def launch_context(playwright, name, headless=True):
    """Launch a persistent Chromium context that reuses ``name``'s profile."""

    return playwright.chromium.launch_persistent_context(
        user_data_dir=profile_dir(name),
        headless=headless,
        user_agent=DEFAULT_USER_AGENT,
        locale="en-US",
        viewport={"width": 1280, "height": 900},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
