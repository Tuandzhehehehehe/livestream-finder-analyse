# Lead Discovery

Find high-potential livestreams, webinars, and events.

Features:

- Crawl livestream/event data
- AI classification
- Opportunity scoring
- Engagement suggestions

## X & TikTok crawling

X and TikTok block search for anonymous visitors, so their crawlers drive a real
Chromium (Playwright) and reuse a persistent, logged-in browser profile. Set it
up once per platform on a machine with a display:

```bash
python -m playwright install chromium
python -m crawler.session_login x
python -m crawler.session_login tiktok
```

A browser window opens at the login page — log in, then press Enter to save the
session. The crawlers read the structured JSON the sites fetch from their own
search APIs. The login profile lives in `data/browser_profile/` (override with
the `BROWSER_PROFILE_DIR` env var).
