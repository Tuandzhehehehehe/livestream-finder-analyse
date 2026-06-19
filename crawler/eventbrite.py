
import requests
from bs4 import BeautifulSoup


headers = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64)"
    )
}


def crawl_eventbrite(
    keywords,
    limit=20
):

    events = []

    seen_urls = set()

    for keyword in keywords:

        print(
            f"EVENTBRITE SEARCH: {keyword}"
        )

        url = (
            "https://www.eventbrite.com/d/"
            "online/"
            f"{keyword.replace(' ', '-')}/"
        )

        try:

            response = requests.get(
                url,
                headers=headers,
                timeout=15
            )

            if response.status_code != 200:
                continue

            soup = BeautifulSoup(
                response.text,
                "html.parser"
            )

            cards = soup.find_all(
                "a",
                href=True
            )

            for card in cards:

                href = card.get(
                    "href",
                    ""
                )

                if (
                    "/e/"
                    not in href
                ):
                    continue

                if href in seen_urls:
                    continue

                seen_urls.add(
                    href
                )

                title = (
                    card.get_text(
                        " ",
                        strip=True
                    )
                )

                if (
                    not title
                    or len(title) < 10
                ):
                    continue

                events.append(
                    {
                        "title": title,

                        "platform": "Eventbrite",

                        "url": href,

                        "description": "",

                        "keyword": keyword,

                        "status": "UPCOMING",

                        "start_time": "",

                        "scheduled_start_time": "",

                        "actual_start_time": "",

                        "actual_end_time": "",
                    }
                )

                if (
                    len(events)
                    >= limit
                ):
                    return events

        except Exception as e:

            print(
                f"Eventbrite Error: {e}"
            )

    return events

