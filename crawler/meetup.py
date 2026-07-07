
import time
import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def crawl_meetup(
    keywords,
    limit=20
):

    events = []

    seen_urls = set()

    for keyword in keywords:

        print(
            f"\nMEETUP SEARCH: {keyword}"
        )

        url = (
            f"https://www.meetup.com/find/?keywords={keyword}"
        )

        try:

            response = requests.get(
                url,
                headers=headers,
                timeout=15
            )

            if response.status_code != 200:

                print(
                    f"Meetup Error {response.status_code}"
                )

                continue

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            event_cards = soup.find_all(
                "a",
                {
                    "data-event-label":
                    "Event Card"
                }
            )

            for event in event_cards:

                try:

                    title_tag = event.find(
                        "h3"
                    )

                    title = (
                        title_tag.text.strip()
                        if title_tag
                        else "Unknown Event"
                    )

                    event_url = event.get(
                        "href",
                        ""
                    )

                    if (
                        not event_url
                        or event_url in seen_urls
                    ):
                        continue

                    seen_urls.add(
                        event_url
                    )

                    time_tag = event.find(
                        "time"
                    )

                    event_time = ""
                    event_datetime_str = ""
                    if time_tag:
                        event_time = time_tag.text.strip()
                        # Lấy attribute datetime để parse chính xác
                        event_datetime_str = time_tag.get("datetime", "")

                    # Lọc sự kiện đã qua
                    if event_datetime_str:
                        try:
                            from datetime import datetime, timezone, timedelta
                            event_dt = datetime.fromisoformat(
                                event_datetime_str.replace("Z", "+00:00")
                            )
                            now = datetime.now(timezone.utc)
                            # Bỏ qua sự kiện đã kết thúc hơn 1 ngày trước
                            if event_dt < (now - timedelta(days=1)):
                                continue
                        except Exception:
                            pass

                    organizer_tag = event.find(
                        "div",
                        class_="flex-shrink min-w-0 truncate"
                    )

                    organizer = (
                        organizer_tag.text.replace(
                            "by",
                            ""
                        ).strip()
                        if organizer_tag
                        else ""
                    )

                    attendees_tag = event.find(
                        lambda tag:
                        tag.name == "span"
                        and "attendees" in tag.text.lower()
                    )

                    attendees = (
                        attendees_tag.text.strip()
                        if attendees_tag
                        else ""
                    )

                    description = (
                        f"Organizer: {organizer}\n"
                        f"Attendees: {attendees}"
                    )

                    events.append(
                        {
                            "title": title,

                            "platform": "Meetup",

                            "url": event_url,

                            "description": description,

                            "keyword": keyword,

                            "status": "UPCOMING",

                            "start_time": event_time,

                            "scheduled_start_time": event_time,

                            "actual_start_time": "",

                            "actual_end_time": "",
                        }
                    )

                    if len(events) >= limit:
                        return events

                except Exception as e:

                    print(
                        f"Meetup Parse Error: {e}"
                    )

            time.sleep(1)

        except Exception as e:

            print(
                f"Meetup Request Error: {e}"
            )

    return events
