"""LinkedIn crawler.

LinkedIn redirects anonymous visitors to a login page, so we drive a
real, logged-in Chromium via Playwright and crawl LinkedIn Event search results.

Run ``python -m crawler.session_login linkedin`` once to create the session.

Strategy:
1. Search the "Events" tab for each keyword (direct match)
2. Search the "All" tab and extract linkedin.com/events/ links from HTML
3. Visit each event page to scrape title, description, time
"""

import re
import time
from urllib.parse import quote_plus

from crawler._browser import DEFAULT_USER_AGENT, launch_context

# Increase cap to allow more related query variants.
MAX_KEYWORDS = 8


def guess_status(time_str):
    t = time_str.lower()
    if "ended" in t or "past" in t:
        return "COMPLETED"
    if "happening now" in t or "started" in t:
        return "LIVE"
    
    # Rất khó parse date vì LinkedIn dùng nhiều format đa ngôn ngữ,
    # nên mặc định sẽ dùng UPCOMING nếu không có keyword rõ ràng.
    return "UPCOMING"

def build_event(title, url, keyword, description="", start_time=""):
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


def _extract_event_urls_from_html(html):
    """Extract LinkedIn event URLs from raw HTML using regex.
    
    This is robust against CSS class name changes because it only looks
    at href attributes pointing to LinkedIn event pages.
    """
    urls = set()
    # Match absolute URLs
    for m in re.findall(r'href="(https?://(?:www\.)?linkedin\.com/events/[^"?#]+)', html):
        urls.add(m)
    # Match relative URLs
    for m in re.findall(r'href="(/events/[^"?#]+)', html):
        urls.add(f"https://www.linkedin.com{m}")
    return list(urls)


def _scrape_event_page(page, url, keyword):
    """Visit a single LinkedIn event page and extract its details."""
    try:
        page.goto(url, timeout=30000)
        page.wait_for_timeout(2500)
        
        # Try to auto-click "Accept" on Cookie/Privacy Wall if it appears
        try:
            accept_button = page.query_selector('button[action-type="ACCEPT"]')
            if accept_button:
                print(f"  -> Bypassing Privacy Wall...")
                accept_button.click(timeout=3000)
                page.wait_for_timeout(2000)
        except Exception:
            pass

        # --- Title ---
        title = ""
        # Try h1 first (most reliable)
        h1 = page.query_selector("h1")
        if h1:
            title = h1.inner_text().strip()
        # Fallback to page <title> tag
        if not title:
            try:
                raw_title = page.title()
                # LinkedIn titles often end with " | LinkedIn"
                title = re.sub(r'\s*\|\s*LinkedIn$', '', raw_title).strip()
            except Exception:
                pass
        if not title:
            return None

        # --- Description ---
        description = ""
        # Try various selectors for event description
        for sel in [
            "[data-testid*='description']",
            "[data-testid*='about']",
            "section p",
        ]:
            el = page.query_selector(sel)
            if el:
                description = el.inner_text().strip()
                if len(description) > 20:
                    break

        # If no description from selectors, try to grab any large text block
        if len(description) < 20:
            # Get all paragraph-like text on the page
            all_text = page.evaluate("""() => {
                const els = document.querySelectorAll('p, span');
                const texts = [];
                for (const el of els) {
                    const t = el.innerText.trim();
                    if (t.length > 50 && t.length < 2000) texts.push(t);
                }
                return texts.slice(0, 3).join('\\n');
            }""")
            if all_text:
                description = all_text[:1000]

        # --- Date/Time ---
        start_time = ""
        # Look for <time> elements
        time_el = page.query_selector("time")
        if time_el:
            start_time = time_el.get_attribute("datetime") or time_el.inner_text().strip()
        
        if not start_time:
            # Try to find date patterns in the page text
            date_text = page.evaluate("""() => {
                const els = document.querySelectorAll('span, div, p');
                for (const el of els) {
                    const t = el.innerText.trim();
                    // Look for date-like patterns
                    if (/\\d{1,2}\\s+(thg|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i.test(t) && t.length < 100) {
                        return t;
                    }
                    if (/\\d{4}-\\d{2}-\\d{2}/.test(t) && t.length < 100) {
                        return t;
                    }
                }
                return '';
            }""")
            start_time = date_text

        # --- Location ---
        location = ""
        loc_text = page.evaluate("""() => {
            const els = document.querySelectorAll('span, div');
            for (const el of els) {
                const t = el.innerText.trim().toLowerCase();
                if ((t.includes('online') || t.includes('trực tuyến') || 
                     t.includes('virtual') || t.includes('zoom') || 
                     t.includes('teams') || t.includes('webinar')) && t.length < 100) {
                    return el.innerText.trim();
                }
            }
            return '';
        }""")
        if loc_text:
            location = loc_text

        if location:
            description = f"Location: {location}\n{description}"

        safe_title = title[:80].encode('ascii', 'replace').decode('ascii')
        print(f"  -> Scraped event: {safe_title}")
        return build_event(
            title=title,
            url=url,
            keyword=keyword,
            description=description,
            start_time=start_time,
        )

    except Exception as e:
        print(f"  -> Error scraping event page {url}: {e}")
        return None


def _is_logged_out(page):
    """Check if we've been redirected to a login page."""
    curr_url = page.url.lower()
    return any(kw in curr_url for kw in ["login", "signup", "checkpoint", "authwall"])


def _search_events_tab(page, keyword, limit, seen_urls, events):
    """Strategy 1: Search LinkedIn's Events tab directly."""
    query = quote_plus(keyword)
    url = f"https://www.linkedin.com/search/results/events/?keywords={query}"
    print(f"LINKEDIN EVENTS SEARCH: {keyword}")

    try:
        page.goto(url, timeout=45000)
        page.wait_for_timeout(4000)

        # Try to auto-click "Accept" on Cookie/Privacy Wall
        try:
            accept_button = page.query_selector('button[action-type="ACCEPT"]')
            if accept_button:
                accept_button.click(timeout=3000)
                page.wait_for_timeout(2000)
        except Exception:
            pass

        if _is_logged_out(page):
            print("  LinkedIn appears logged out.")
            return False  # Signal to stop

        # Extract event URLs from the HTML (robust against CSS changes)
        html = page.content()
        event_urls = _extract_event_urls_from_html(html)
        print(f"  Found {len(event_urls)} event URLs in Events tab")

        for event_url in event_urls:
            if event_url in seen_urls or len(events) >= limit:
                continue
            seen_urls.add(event_url)
            event = _scrape_event_page(page, event_url, keyword)
            if event:
                events.append(event)

    except Exception as e:
        print(f"  Events tab error: {e}")

    return True  # OK to continue


def _search_all_tab(page, keyword, limit, seen_urls, events):
    """Strategy 2: Search LinkedIn's 'All' tab and extract event links."""
    query = quote_plus(keyword)
    url = f"https://www.linkedin.com/search/results/all/?keywords={query}"
    print(f"LINKEDIN ALL SEARCH: {keyword}")

    try:
        page.goto(url, timeout=45000)
        page.wait_for_timeout(4000)

        # Try to auto-click "Accept" on Cookie/Privacy Wall
        try:
            accept_button = page.query_selector('button[action-type="ACCEPT"]')
            if accept_button:
                accept_button.click(timeout=3000)
                page.wait_for_timeout(2000)
        except Exception:
            pass

        if _is_logged_out(page):
            return False

        # Scroll down to load more results
        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)

        # Extract event URLs from the HTML
        html = page.content()
        event_urls = _extract_event_urls_from_html(html)
        print(f"  Found {len(event_urls)} event URLs in All tab")

        for event_url in event_urls:
            if event_url in seen_urls or len(events) >= limit:
                continue
            seen_urls.add(event_url)
            event = _scrape_event_page(page, event_url, keyword)
            if event:
                events.append(event)

    except Exception as e:
        print(f"  All tab error: {e}")

    return True


def _search_content_tab(page, keyword, limit, seen_urls, events):
    """Strategy 3: Search LinkedIn posts/content for event announcements."""
    # Add event-related suffixes to find posts about events
    for suffix in ["event", "webinar", "live"]:
        if len(events) >= limit:
            break

        full_query = f"{keyword} {suffix}"
        query = quote_plus(full_query)
        url = f"https://www.linkedin.com/search/results/content/?keywords={query}"
        print(f"LINKEDIN CONTENT SEARCH: {full_query}")

        try:
            page.goto(url, timeout=45000)
            page.wait_for_timeout(4000)

            if _is_logged_out(page):
                return False

            # Scroll to load content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(1500)

            # Extract event URLs from posts
            html = page.content()
            event_urls = _extract_event_urls_from_html(html)
            print(f"  Found {len(event_urls)} event URLs in Content tab for '{full_query}'")

            for event_url in event_urls:
                if event_url in seen_urls or len(events) >= limit:
                    continue
                seen_urls.add(event_url)
                event = _scrape_event_page(page, event_url, keyword)
                if event:
                    events.append(event)

        except Exception as e:
            print(f"  Content tab error: {e}")

    return True


def _crawl_headless(keywords, limit, seen_urls, events, use_headless=True):
    """Drive a logged-in browser and scrape LinkedIn events using multiple strategies."""

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = launch_context(p, "linkedin", headless=use_headless)
        page = context.pages[0] if context.pages else context.new_page()

        # Go to feed first to warm up the session
        try:
            page.goto("https://www.linkedin.com/feed/", timeout=30000)
            page.wait_for_timeout(2000)
        except Exception:
            pass

        for keyword in keywords[:MAX_KEYWORDS]:
            if len(events) >= limit:
                break

            # Strategy 1: Direct event search
            ok = _search_events_tab(page, keyword, limit, seen_urls, events)
            if not ok:
                print("LinkedIn session lost. Stopping.")
                break

            if len(events) >= limit:
                break

            # Strategy 2: Search "All" tab for event links
            ok = _search_all_tab(page, keyword, limit, seen_urls, events)
            if not ok:
                break

            if len(events) >= limit:
                break

        # Strategy 3: If still not enough results, search content/posts
        if len(events) < limit:
            # Use only the first 3 keywords for content search to save time
            for keyword in keywords[:3]:
                if len(events) >= limit:
                    break
                ok = _search_content_tab(page, keyword, limit, seen_urls, events)
                if not ok:
                    break

        context.close()

    return events


def crawl_linkedin(keywords, limit=20, use_headless=True):
    """Search LinkedIn for event keywords and return a list of event dicts.

    Since LinkedIn blocks anonymous event search, we always use Playwright with a logged-in profile.
    
    Multi-strategy approach:
    1. Search Events tab for each keyword
    2. Search All tab and extract event links from HTML
    3. Search Content tab for posts mentioning events
    """
    events = []
    seen_urls = set()

    try:
        return _crawl_headless(keywords, limit, seen_urls, events, use_headless=use_headless)
    except Exception as e:
        print(f"LinkedIn headless error: {e}")
        return events
