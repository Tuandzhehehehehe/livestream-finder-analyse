import json
import re
import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def build_event(title, url, keyword, description=""):
    return {
        "title": title,
        "platform": "X",
        "url": url,
        "description": description,
        "keyword": keyword,
        "status": "LIVE",
        "start_time": "",
        "scheduled_start_time": "",
        "actual_start_time": "",
        "actual_end_time": "",
    }


def normalize_url(href):
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://x.com{href}"
    return href


def extract_text(article):
    text_node = article.find("div", {"lang": True})
    if text_node:
        return text_node.get_text(" ", strip=True)

    spans = article.find_all("span")
    text = " ".join(
        span.get_text(" ", strip=True)
        for span in spans
        if span.get_text(strip=True)
    )
    return re.sub(r"\s+", " ", text).strip()


def _fetch_html(url, use_headless=False):
    if use_headless:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                html = page.content()
                try:
                    browser.close()
                except Exception:
                    pass
                return html
        except Exception as e:
            print(f"Playwright unavailable or error: {e}. Falling back to requests.")

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        print(f"Requests fetch error: {e}")

    return ""


def crawl_x_live(keywords, limit=20, use_headless=False):
    events = []
    seen_urls = set()

    for keyword in keywords:
        # try a range of query variants to increase hit rate on X
        variants = [
            keyword,
            f"{keyword} live",
            f"{keyword} livestream",
            f"{keyword} stream",
            f"{keyword} webinar",
            f"{keyword} workshop",
            f"{keyword} online event",
            f"{keyword} talk",
            f"{keyword} panel",
            f"{keyword} ama",
            f"{keyword} networking",
        ]

        for q in variants:
            query = quote_plus(q)
            url = f"https://x.com/search?q={query}&src=typed_query"

            print(f"X SEARCH: {q}")

            try:
                html = _fetch_html(url, use_headless=use_headless)
                if not html:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                # try to find tweet/article elements
                articles = soup.find_all("article") or soup.find_all("div", attrs={"data-testid": "tweet"})

                for article in articles:
                    # attempt to find any anchor with href inside the article
                    link = None
                    for a in article.find_all("a", href=True):
                        href = a.get("href")
                        if href and ("/status/" in href or href.startswith("/")):
                            link = a
                            break

                    if not link:
                        # fallback: first anchor
                        link = article.find("a", href=True)

                    if not link:
                        continue

                    event_url = normalize_url(link["href"])

                    if not event_url or event_url in seen_urls:
                        continue

                    title = extract_text(article)

                    if not title:
                        continue

                    seen_urls.add(event_url)

                    events.append(
                        build_event(
                            title,
                            event_url,
                            keyword,
                            description="",
                        )
                    )

                    if len(events) >= limit:
                        return events

            except Exception as e:
                print(f"X Request Error: {e}")

            time.sleep(1)

    return events
