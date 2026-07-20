"""
crawler/web_search.py — Google Web Search Crawler
==================================================
Searches Google for targeted event links (Luma, Eventbrite, Zoom, Meetup, YouTube).
"""

import re
import urllib.parse
from datetime import datetime
# pyrefly: ignore [missing-import]
from playwright.sync_api import sync_playwright
from crawler._browser import launch_context

ALLOWED_DOMAINS = [
    "lu.ma", "eventbrite.com", "zoom.us", "youtube.com",
    "twitch.tv", "vimeo.com", "meetup.com", "linkedin.com/events"
]


def crawl_web(keywords: list, limit: int = 20, **kwargs) -> list:
    events = []
    seen_urls = set()
    current_year = datetime.now().year

    with sync_playwright() as p:
        context = launch_context(p, "google_search", headless=True)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            for keyword in keywords[:5]:
                if len(events) >= limit:
                    break

                query = f'"{keyword}" (site:lu.ma OR site:eventbrite.com OR site:zoom.us OR site:youtube.com OR site:twitch.tv OR site:vimeo.com OR site:meetup.com) (livestream OR webinar OR event)'
                url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
                print(f"[Web Search] Query: {keyword}")

                try:
                    page.goto(url, timeout=30000)
                    page.wait_for_timeout(2000)

                    if "sorry/index" in page.url or "consent.google.com" in page.url:
                        print("[Web Search] Captcha/Consent detected")

                    for h3 in page.query_selector_all("h3"):
                        a = h3.evaluate_handle('node => node.closest("a")')
                        if not a:
                            continue
                        href = a.get_attribute("href") or ""
                        if not href.startswith("http") or "google.com" in href or href in seen_urls:
                            continue

                        if not any(d in href for d in ALLOWED_DOMAINS):
                            continue
                        seen_urls.add(href)

                        title = h3.inner_text().strip()
                        if not title:
                            continue

                        snippet = "Google Web Search event result."
                        try:
                            container = h3.evaluate_handle('node => { let el = node; while(el && !el.classList.contains("g") && el.tagName !== "BODY") { el = el.parentElement; } return el.tagName !== "BODY" ? el : node.parentElement.parentElement; }')
                            if container:
                                snippet = container.inner_text().replace('\n', ' ')
                        except Exception:
                            pass

                        years_found = [int(y) for y in re.findall(r'\b(20\d{2})\b', title + ' ' + snippet)]
                        if years_found and (min(years_found) < current_year or min(years_found) > current_year + 1):
                            continue

                        events.append({
                            "platform": "Web",
                            "keyword": keyword,
                            "title": title,
                            "url": href,
                            "start_time": "",
                            "status": "UPCOMING",
                            "description": snippet,
                        })

                        if len(events) >= limit:
                            break
                except Exception as e:
                    print(f"[Web Search] Error for '{keyword}': {e}")
        finally:
            try:
                context.close()
            except Exception:
                pass

    return events
