"""Eventbrite crawler.

Eventbrite renders its result cards from JavaScript, but it also embeds a
``schema.org`` ``ItemList`` as ``application/ld+json`` in the page HTML. We parse
that structured data (robust) and fall back to scraping ``/e/`` anchors.
"""

import json

import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def build_event(title, url, keyword, description="", start_time=""):
    return {
        "title": title,
        "platform": "Eventbrite",
        "url": url,
        "description": description,
        "keyword": keyword,
        "status": "UPCOMING",
        "start_time": start_time,
        "scheduled_start_time": start_time,
        "actual_start_time": "",
        "actual_end_time": "",
    }


def _clean_url(url):
    return (url or "").split("?")[0]


def _events_from_ldjson(soup, keyword, seen_urls):
    events = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        for entry in data.get("itemListElement") or []:
            item = entry.get("item") if isinstance(entry, dict) else None
            if not isinstance(item, dict):
                continue

            url = _clean_url(item.get("url"))
            name = item.get("name") or ""
            if not url or not name or url in seen_urls:
                continue

            seen_urls.add(url)
            events.append(
                build_event(
                    title=name,
                    url=url,
                    keyword=keyword,
                    description=item.get("description") or "",
                    start_time=item.get("startDate") or "",
                )
            )

    return events


def _events_from_anchors(soup, keyword, seen_urls):
    events = []

    for card in soup.find_all("a", href=True):
        href = _clean_url(card.get("href"))
        if "/e/" not in href or href in seen_urls:
            continue

        title = card.get_text(" ", strip=True)
        if not title or len(title) < 10:
            continue

        seen_urls.add(href)
        events.append(build_event(title=title, url=href, keyword=keyword))

    return events


def crawl_eventbrite(keywords, limit=20):
    events = []
    seen_urls = set()

    for keyword in keywords:
        print(f"EVENTBRITE SEARCH: {keyword}")

        url = (
            "https://www.eventbrite.com/d/online/"
            f"{keyword.replace(' ', '-')}/"
        )

        try:
            response = requests.get(url, headers=headers, timeout=15)
        except Exception as e:
            print(f"Eventbrite Error: {e}")
            continue

        if response.status_code != 200:
            print(f"Eventbrite Error {response.status_code}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        found = _events_from_ldjson(soup, keyword, seen_urls)
        if not found:
            found = _events_from_anchors(soup, keyword, seen_urls)

        for event in found:
            events.append(event)
            if len(events) >= limit:
                return events

    return events
