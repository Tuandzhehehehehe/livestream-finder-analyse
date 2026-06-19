"""X (Twitter) crawler.

X redirects anonymous visitors away from search to a login page, so we drive a
real, logged-in Chromium via Playwright and read the JSON that X's own
``SearchTimeline`` GraphQL endpoint returns instead of scraping HTML.

Run ``python -m crawler.session_login x`` once to create the session.
"""

import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from crawler._browser import DEFAULT_USER_AGENT, launch_context

headers = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
}

# Browser-based crawling is slow; cap how many query variants we visit per run.
MAX_KEYWORDS = 4


def build_event(title, url, keyword, description="", create_time=""):
    return {
        "title": title,
        "platform": "X",
        "url": url,
        "description": description,
        "keyword": keyword,
        "status": "LIVE",
        "start_time": create_time,
        "scheduled_start_time": create_time,
        "actual_start_time": create_time,
        "actual_end_time": "",
    }


def _find_tweets(node, found):
    """Recursively collect tweet ``result`` objects from a GraphQL JSON tree."""

    if isinstance(node, dict):
        typename = node.get("__typename")
        if typename in ("Tweet", "TweetWithVisibilityResults"):
            tweet = node.get("tweet", node)
            if isinstance(tweet, dict) and tweet.get("legacy"):
                found.append(tweet)
        for value in node.values():
            _find_tweets(value, found)
    elif isinstance(node, list):
        for value in node:
            _find_tweets(value, found)


def _screen_name(tweet):
    core = tweet.get("core") or {}
    user = core.get("user_results") or {}
    result = user.get("result") or {}
    legacy = result.get("legacy") or {}
    return (
        legacy.get("screen_name")
        or (result.get("core") or {}).get("screen_name")
        or ""
    )


def _normalize_tweet(tweet, keyword):
    legacy = tweet.get("legacy") or {}
    tweet_id = tweet.get("rest_id") or legacy.get("id_str")
    screen_name = _screen_name(tweet)

    if not tweet_id or not screen_name:
        return None

    text = legacy.get("full_text") or legacy.get("text") or ""
    url = f"https://x.com/{screen_name}/status/{tweet_id}"
    create_time = legacy.get("created_at") or ""

    return build_event(
        title=text or f"Post by @{screen_name}",
        url=url,
        keyword=keyword,
        description=text,
        create_time=create_time,
    )


def _looks_logged_out(page):
    url = page.url.lower()
    if "/login" in url or "/i/flow/login" in url or "onboarding" in url:
        return True
    try:
        body = page.inner_text("body").lower()
    except Exception:
        return False
    return "see what's happening" in body and "log in" in body


def _crawl_headless(keywords, limit, seen_urls, events):
    """Drive a logged-in browser and read X's SearchTimeline JSON responses."""

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = launch_context(p, "x", headless=True)
        page = context.pages[0] if context.pages else context.new_page()

        payloads = []

        def on_response(response):
            if "SearchTimeline" not in response.url:
                return
            try:
                payloads.append(response.json())
            except Exception:
                pass

        page.on("response", on_response)

        # Browser crawling is slow, so cap how many query variants we visit.
        for keyword in keywords[:MAX_KEYWORDS]:
            query = quote_plus(f"{keyword} live")
            url = f"https://x.com/search?q={query}&src=typed_query&f=live"
            print(f"X SEARCH: {keyword}")
            payloads.clear()

            try:
                page.goto(url, timeout=45000)
                page.wait_for_timeout(3500)
                for _ in range(2):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(1500)
            except Exception as e:
                print(f"X navigation error: {e}")
                continue

            if not payloads and _looks_logged_out(page):
                print(
                    "X appears logged out. Run "
                    "'python -m crawler.session_login x' once to create a "
                    "session."
                )
                context.close()
                return events

            tweets = []
            for payload in payloads:
                _find_tweets(payload, tweets)

            for tweet in tweets:
                event = _normalize_tweet(tweet, keyword)
                if not event or event["url"] in seen_urls:
                    continue
                seen_urls.add(event["url"])
                events.append(event)
                if len(events) >= limit:
                    context.close()
                    return events

        context.close()

    return events


def normalize_url(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://x.com{href}"
    return href


def _crawl_requests(keywords, limit, seen_urls, events):
    """Best-effort HTML fallback (usually blocked by the login wall)."""

    for keyword in keywords:
        query = quote_plus(f"{keyword} live")
        url = f"https://x.com/search?q={query}&src=typed_query"
        print(f"X SEARCH (requests): {keyword}")

        try:
            response = requests.get(url, headers=headers, timeout=15)
        except Exception as e:
            print(f"X Request Error: {e}")
            continue

        if response.status_code != 200:
            time.sleep(1)
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for article in soup.find_all("article"):
            link = article.find("a", href=True)
            if not link:
                continue
            event_url = normalize_url(link.get("href"))
            if not event_url or event_url in seen_urls:
                continue
            text = article.get_text(" ", strip=True)
            if not text:
                continue
            seen_urls.add(event_url)
            events.append(build_event(text, event_url, keyword))
            if len(events) >= limit:
                return events

        time.sleep(1)

    return events


def crawl_x_live(keywords, limit=20, use_headless=True):
    """Search X for ``keywords`` and return a list of event dicts.

    ``use_headless`` drives a real (logged-in) browser via Playwright, which is
    required because X blocks anonymous search. When False, a best-effort HTTP
    fallback is used (usually returns nothing while logged out).
    """

    events = []
    seen_urls = set()

    if use_headless:
        try:
            return _crawl_headless(keywords, limit, seen_urls, events)
        except Exception as e:
            print(f"X headless error: {e}. Falling back to requests.")

    return _crawl_requests(keywords, limit, seen_urls, events)
