"""One-time interactive login for crawlers that require an authenticated session.

Run this once per platform on a machine with a display:

    python -m crawler.session_login x
    python -m crawler.session_login tiktok

A real Chromium window opens at the platform login page. Log in manually, then
press Enter in the terminal. The session is stored in the persistent profile
(see ``crawler/_browser.py``) and reused by the crawlers afterwards.
"""

import sys

from playwright.sync_api import sync_playwright

from crawler._browser import launch_context

LOGIN_URLS = {
    "x": "https://x.com/login",
    "tiktok": "https://www.tiktok.com/login",
}


def login(platform: str):
    platform = platform.lower()

    if platform not in LOGIN_URLS:
        raise SystemExit(
            f"Unknown platform '{platform}'. Choose one of: "
            f"{', '.join(LOGIN_URLS)}"
        )

    with sync_playwright() as p:
        context = launch_context(p, platform, headless=False)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto(LOGIN_URLS[platform], timeout=60000)
        except Exception:
            pass

        print(
            f"\nLog in to {platform} in the opened browser window, "
            "then press Enter here to save the session..."
        )
        input()

        # The session is persisted to the profile dir as you browse; closing may
        # raise if you already closed the window, which is harmless.
        try:
            context.close()
        except Exception:
            pass

        print("Session saved.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m crawler.session_login <x|tiktok>")

    login(sys.argv[1])
