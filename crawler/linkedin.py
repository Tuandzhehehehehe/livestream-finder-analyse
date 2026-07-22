"""
crawler/linkedin.py — LinkedIn Events Crawler
===============================================
Drives a logged-in Playwright session to search LinkedIn Events, All, and Content tabs.
"""

import re
from urllib.parse import quote_plus
from crawler._browser import launch_context

MAX_KEYWORDS = 8


def guess_status(time_str: str) -> str:
    t = time_str.lower()
    if "ended" in t or "past" in t:
        return "COMPLETED"
    if "happening now" in t or "started" in t:
        return "LIVE"
    return "UPCOMING"


def build_event(title: str, url: str, keyword: str, description: str = "", start_time: str = "") -> dict:
    status = guess_status(start_time)
    return {
        "title": title,
        "platform": "LinkedIn",
        "url": url,
        "description": description,
        "keyword": keyword,
        "status": "UPCOMING",
        "start_time": start_time,
        "scheduled_start_time": start_time,
        "actual_start_time": start_time if status == "LIVE" else "",
        "actual_end_time": start_time if status == "COMPLETED" else "",
    }


def _extract_event_urls_from_html(html: str) -> list:
    urls = set()
    for m in re.findall(r'href="(https?://(?:www\.)?linkedin\.com/events/[^"?#]+)', html):
        urls.add(m)
    for m in re.findall(r'href="(/events/[^"?#]+)', html):
        urls.add(f"https://www.linkedin.com{m}")
    return list(urls)


def _scrape_event_page(page, url: str, keyword: str) -> dict:
    try:
        page.goto(url, timeout=30000)
        page.wait_for_timeout(2000)

        title = ""
        h1 = page.query_selector("h1")
        if h1:
            title = h1.inner_text().strip()
        if not title:
            try:
                title = re.sub(r'\s*\|\s*LinkedIn$', '', page.title()).strip()
            except Exception:
                pass
        if not title:
            return None

        description = ""
        for sel in ["[data-testid*='description']", "[data-testid*='about']", "section p"]:
            el = page.query_selector(sel)
            if el and len(el.inner_text().strip()) > 20:
                description = el.inner_text().strip()
                break

        time_el = page.query_selector("time")
        start_time = time_el.get_attribute("datetime") or time_el.inner_text().strip() if time_el else ""

        print(f"  -> Scraped: {title[:60]}")
        return build_event(title=title, url=url, keyword=keyword, description=description, start_time=start_time)
    except Exception as e:
        print(f"  -> Error scraping event {url}: {e}")
        return None


def _is_logged_out(page) -> bool:
    curr_url = page.url.lower()
    return any(kw in curr_url for kw in ["login", "signup", "checkpoint", "authwall"])


def crawl_linkedin(keywords: list, limit: int = 20, use_headless: bool = True) -> list:
    events = []
    seen_urls = set()

    # pyrefly: ignore [missing-import]
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            context = launch_context(p, "linkedin", headless=use_headless)
            page = context.pages[0] if context.pages else context.new_page()

            for keyword in keywords[:MAX_KEYWORDS]:
                if len(events) >= limit:
                    break

                for tab, tab_url in [
                    ("Events", f"https://www.linkedin.com/search/results/events/?keywords={quote_plus(keyword)}"),
                    ("All", f"https://www.linkedin.com/search/results/all/?keywords={quote_plus(keyword)}"),
                ]:
                    if len(events) >= limit:
                        break

                    try:
                        page.goto(tab_url, timeout=40000)
                        page.wait_for_timeout(3000)

                        if _is_logged_out(page):
                            print("  LinkedIn session logged out.")
                            context.close()
                            return events

                        event_urls = _extract_event_urls_from_html(page.content())
                        for e_url in event_urls:
                            if e_url in seen_urls or len(events) >= limit:
                                continue
                            seen_urls.add(e_url)
                            item = _scrape_event_page(page, e_url, keyword)
                            if item:
                                events.append(item)
                    except Exception as e:
                        print(f"  LinkedIn {tab} error for '{keyword}': {e}")

            context.close()
    except Exception as e:
        print(f"LinkedIn crawl error: {e}")

    return events
