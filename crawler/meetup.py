"""
crawler/meetup.py — Meetup Events Crawler
==========================================
Scrapes Meetup search results for upcoming local and online events.
"""

import time
import requests
from datetime import datetime, timezone, timedelta
# pyrefly: ignore [missing-import]
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def crawl_meetup(keywords: list, limit: int = 20) -> list:
    events = []
    seen_urls = set()
    now = datetime.now(timezone.utc)

    for keyword in keywords:
        print(f"\nMEETUP SEARCH: {keyword}")
        url = f"https://www.meetup.com/find/?keywords={keyword}"

        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code != 200:
                print(f"Meetup Error {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            event_cards = soup.find_all("a", {"data-event-label": "Event Card"})

            for card in event_cards:
                try:
                    title_tag = card.find("h3")
                    title = title_tag.text.strip() if title_tag else "Unknown Event"
                    event_url = card.get("href", "")

                    if not event_url or event_url in seen_urls:
                        continue
                    seen_urls.add(event_url)

                    time_tag = card.find("time")
                    event_time = time_tag.text.strip() if time_tag else ""
                    datetime_str = time_tag.get("datetime", "") if time_tag else ""

                    if datetime_str:
                        try:
                            event_dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
                            if event_dt < (now - timedelta(days=1)):
                                continue
                        except Exception:
                            pass

                    org_tag = card.find("div", class_="flex-shrink min-w-0 truncate")
                    organizer = org_tag.text.replace("by", "").strip() if org_tag else ""
                    att_tag = card.find(lambda t: t.name == "span" and "attendees" in t.text.lower())
                    attendees = att_tag.text.strip() if att_tag else ""

                    events.append({
                        "title": title,
                        "platform": "Meetup",
                        "url": event_url,
                        "description": f"Organizer: {organizer}\nAttendees: {attendees}".strip(),
                        "keyword": keyword,
                        "status": "UPCOMING",
                        "start_time": event_time,
                        "scheduled_start_time": event_time,
                        "actual_start_time": "",
                        "actual_end_time": "",
                    })

                    if len(events) >= limit:
                        return events

                except Exception as e:
                    print(f"Meetup Parse Error: {e}")

            time.sleep(1)

        except Exception as e:
            print(f"Meetup Request Error: {e}")

    return events
